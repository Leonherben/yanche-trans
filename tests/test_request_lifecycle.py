"""控制网络完成顺序和 Qt 信号入队顺序，验证收起及旧结果隔离。"""

import importlib
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCursor, QKeyEvent

from yanxi.core.config import SelectionMode
from yanxi.core.models import TranslationResult
from yanxi.core.request_tracker import RequestTracker


def test_invalidated_request_cannot_become_current_again():
    tracker = RequestTracker()
    first = tracker.begin()
    tracker.invalidate()
    second = tracker.begin()
    assert second > first
    assert not tracker.is_current(first)
    assert tracker.is_current(second)


@pytest.fixture
def pending(controller, qapp, monkeypatch):
    module = importlib.import_module("yanxi.main")
    controller.config.enable_cache = False
    for config in controller.config.providers.values():
        config.api_key = "test-only-key"
    controller.tray.refresh_providers()
    gates = {}
    calls = Queue()
    workers = []

    class ControlledTranslator:
        def __init__(self, provider="microsoft"):
            self.provider = provider

        def translate(self, request):
            gate = gates.setdefault(request.text, Event())
            calls.put(request)
            if not gate.wait(3):
                raise RuntimeError("test request was not released")
            return TranslationResult(
                request.text, f"result:{request.text}",
                request.source_lang, request.target_lang, self.provider,
            )

    def record_thread(*args, **kwargs):
        worker = Thread(*args, **kwargs)
        workers.append((kwargs["args"][0].request.text, worker))
        return worker

    def wait_for_call(text):
        request = calls.get(timeout=2)
        assert request.text == text
        return request

    def finish(text, deliver=True):
        gates[text].set()
        for worker_text, worker in workers:
            if worker_text == text:
                worker.join(2)
                assert not worker.is_alive()
        if deliver:
            qapp.processEvents()

    controller.translator = ControlledTranslator()
    monkeypatch.setattr(module, "create_translator", lambda config: ControlledTranslator(config.name))
    monkeypatch.setattr(module, "threading", SimpleNamespace(Thread=record_thread))
    yield SimpleNamespace(app=controller, calls=calls, workers=workers,
                          wait_for_call=wait_for_call, finish=finish)
    for gate in list(gates.values()):
        gate.set()
    for _, worker in workers:
        worker.join(2)


@pytest.mark.parametrize("dismiss", ["button", "escape", "outside", "timer"])
def test_dismiss_while_translating_does_not_reopen(pending, dismiss):
    app = pending.app
    app.set_selection_mode(SelectionMode.AUTOMATIC)
    app.retranslate_text("A")
    pending.wait_for_call("A")
    assert app.popup.isVisible()
    assert "收起" in app.popup.close_btn.toolTip()
    if dismiss == "button":
        app.popup.close_btn.click()
    elif dismiss == "escape":
        app.popup.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                         Qt.KeyboardModifier.NoModifier))
    elif dismiss == "outside":
        QCursor.setPos(10000, 10000)
        app.popup.dismiss_if_outside()
    else:
        app.popup._on_auto_hide()
    assert not app.popup.isVisible()
    pending.finish("A")
    assert not app.popup.isVisible()
    assert app.popup._current_result is None


def test_newer_request_wins_when_old_network_response_arrives_last(pending):
    app = pending.app
    app.retranslate_text("A")
    pending.wait_for_call("A")
    app.retranslate_text("B")
    pending.wait_for_call("B")
    pending.finish("B")
    assert app.popup._current_result.original_text == "B"
    pending.finish("A")
    assert app.popup._current_result.original_text == "B"
    assert app.popup.original_edit.toPlainText() == "B"


def test_already_queued_result_is_ignored_after_dismiss(pending, qapp):
    app = pending.app
    app.retranslate_text("A")
    pending.wait_for_call("A")
    pending.finish("A", deliver=False)
    app.popup.close_btn.click()
    qapp.processEvents()
    assert not app.popup.isVisible()
    assert app.popup._current_result is None


def test_queued_selection_loading_is_ignored_after_dismiss(pending, qapp):
    app = pending.app
    app.popup.show()
    sender = Thread(target=app.on_text_selected, args=("A", (10, 10)))
    sender.start()
    sender.join(2)
    assert not sender.is_alive()
    app.popup.hide()
    qapp.processEvents()
    assert not app.popup.isVisible()
    assert pending.workers == []


@pytest.mark.parametrize("action", ["clear", "edit", "new_input", "settings"])
def test_query_change_invalidates_pending_result(pending, action):
    app = pending.app
    app.retranslate_text("A")
    pending.wait_for_call("A")
    if action == "clear":
        app.popup._clear_input()
    elif action == "edit":
        app.popup.original_edit.setPlainText("draft")
    elif action == "new_input":
        app.popup.open_for_input()
    else:
        app.on_settings_saved(app.config)
    pending.finish("A")
    assert app.popup._current_result is None
    if action == "edit":
        assert app.popup.original_edit.toPlainText() == "draft"


def test_dismiss_stops_pending_input_debounce(pending):
    app = pending.app
    app.popup.open_for_input()
    app.popup.original_edit.setPlainText("draft")
    assert app.popup._input_debounce_timer.isActive()
    app.popup.close_btn.click()
    assert not app.popup._input_debounce_timer.isActive()
    assert not app.popup.auto_hide_timer.isActive()
    assert pending.workers == []


def test_user_can_start_new_query_after_dismiss(pending):
    app = pending.app
    app.retranslate_text("A")
    pending.wait_for_call("A")
    app.popup.hide()
    app.on_text_selected("B", (20, 20))
    pending.wait_for_call("B")
    pending.finish("B")
    pending.finish("A")
    assert app.popup.isVisible()
    assert app.popup._current_result.original_text == "B"


def test_cached_result_queued_before_dismiss_cannot_reopen(pending, qapp):
    app = pending.app
    app.config.enable_cache = True
    result = TranslationResult("A", "cached", "auto", "zh-CN", "microsoft", from_cache=True)
    app.cache = SimpleNamespace(get=lambda *args: result)
    app.retranslate_text("A")
    pending.workers[-1][1].join(2)
    assert not pending.workers[-1][1].is_alive()
    app.popup.hide()
    qapp.processEvents()
    assert not app.popup.isVisible()
    assert app.popup._current_result is None
    assert pending.calls.empty()


def test_no_selection_shortcut_opens_input_on_gui_thread(controller, qapp):
    hotkey = next(listener for listener in controller.listeners if "on_no_selection" in listener.options)
    sender = Thread(target=hotkey.options["on_no_selection"])
    sender.start()
    sender.join(2)
    qapp.processEvents()
    assert controller.popup.isVisible()
    assert controller.popup.original_edit.toPlainText() == ""


@pytest.mark.parametrize("entry", ["popup", "tray"])
@pytest.mark.parametrize("preference,value", [("provider", "deepseek"), ("source", "en"), ("target", "ja")])
def test_switch_retranslates_current_draft_and_discards_old_response(pending, entry, preference, value):
    app = pending.app
    app.retranslate_text("old")
    pending.wait_for_call("old")
    app.popup.original_edit.setPlainText("draft")
    assert app.popup._input_debounce_timer.isActive()
    callbacks = {
        "popup": {"provider": app.popup._handle_provider_switch,
                  "source": app.popup._handle_source_lang_change,
                  "target": app.popup._handle_target_lang_change},
        "tray": {"provider": app.tray._handle_provider_changed,
                 "source": app.tray._handle_source_lang_changed,
                 "target": app.tray._handle_lang_changed},
    }
    callbacks[entry][preference](value)
    request = pending.wait_for_call("draft")
    assert request.source_lang == ("en" if preference == "source" else "auto")
    assert request.target_lang == ("ja" if preference == "target" else "zh-CN")
    assert not app.popup._input_debounce_timer.isActive()
    assert app.popup._source_lang == app.config.default_source_lang
    assert app.popup._target_lang == app.config.default_target_lang
    assert app.tray.source_lang_actions[request.source_lang].isChecked()
    assert app.tray.lang_actions[request.target_lang].isChecked()
    expected_provider = "deepseek" if preference == "provider" else "microsoft"
    assert app.popup._current_provider == expected_provider
    assert app.tray.provider_actions[expected_provider].isChecked()
    pending.finish("draft")
    pending.finish("old")
    assert app.popup._current_result.original_text == "draft"
    assert app.popup._current_result.provider == expected_provider
    assert app.popup._current_result.target_lang == request.target_lang
    assert app.popup._current_result.source_lang == request.source_lang
    assert len(pending.workers) == 2


@pytest.mark.parametrize("state", ["hidden", "empty"])
def test_preference_changes_do_not_resurrect_previous_query(pending, state):
    app = pending.app
    app.retranslate_text("old")
    pending.wait_for_call("old")
    if state == "hidden":
        app.popup.hide()
    else:
        app.popup._clear_input()
    app.tray._handle_provider_changed("deepseek")
    app.tray._handle_source_lang_changed("en")
    app.tray._handle_lang_changed("ja")
    pending.finish("old")
    assert len(pending.workers) == 1
    assert app.popup._current_result is None
    assert app.popup.isVisible() == (state == "empty")
    assert app.popup.direction_btn.text() in ("英 ⇄ 日", "English → 日本語")
    assert app.config.default_provider == "deepseek"


def test_selecting_active_values_does_not_cancel_or_duplicate_request(pending):
    app = pending.app
    app.retranslate_text("query")
    pending.wait_for_call("query")
    app.popup._handle_provider_switch("microsoft")
    app.popup._handle_source_lang_change("auto")
    app.popup._handle_target_lang_change("zh-CN")
    app.tray._handle_provider_changed("microsoft")
    app.tray._handle_source_lang_changed("auto")
    app.tray._handle_lang_changed("zh-CN")
    pending.finish("query")
    assert len(pending.workers) == 1
    assert app.popup._current_result.original_text == "query"


def test_loading_after_switch_cannot_copy_previous_translation(pending):
    import pyperclip
    app = pending.app
    app.retranslate_text("query")
    pending.wait_for_call("query")
    pending.finish("query")
    app.popup._copy_result()
    assert pyperclip.paste() == "result:query"
    pyperclip.copy("untouched")
    app.popup.original_edit.setPlainText("new query")
    app.set_target_lang("ja")
    pending.wait_for_call("new query")
    app.popup._copy_result()
    assert pyperclip.paste() == "untouched"
    pending.finish("new query")


def test_changed_direction_is_used_for_cache_lookup(pending):
    app = pending.app
    lookups = []
    app.config.enable_cache = True
    app.cache = SimpleNamespace(get=lambda *args: lookups.append(args), put=lambda result: None)
    app.popup.open_for_input()
    app.popup.original_edit.setText("query")
    app.set_source_lang("en")
    pending.wait_for_call("query")
    pending.finish("query")
    app.set_target_lang("ja")
    pending.wait_for_call("query")
    pending.finish("query")
    assert lookups == [("query", "en", "zh-CN", "microsoft"), ("query", "en", "ja", "microsoft")]


def test_settings_save_during_request_leaves_pending_state_not_permanent_loading(pending):
    app = pending.app
    app.retranslate_text("query")
    pending.wait_for_call("query")
    app.on_settings_saved(app.config)
    pending.finish("query")
    assert "待重新翻译" in app.popup.status_msg.text()
    assert "正在翻译" not in app.popup.text_browser.toPlainText()
    assert len(pending.workers) == 1
    assert not app.popup._input_debounce_timer.isActive()
