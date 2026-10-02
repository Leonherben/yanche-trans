import pyperclip
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from yanxi.adapters.gui.popup import PopupBubble
from yanxi.adapters.gui.settings_dialog import SettingsDialog
from yanxi.core.config import AppConfig, UIConfig
from yanxi.core.models import TranslationResult


def test_manual_input_can_require_enter_and_keep_shift_enter_as_newline(qapp):
    calls = []
    popup = PopupBubble(UIConfig(auto_translate_input=False), on_retranslate=calls.append)
    popup.open_for_input()
    popup.original_edit.setPlainText("draft")
    assert not popup._input_debounce_timer.isActive()
    assert calls == []
    popup.original_edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                              Qt.KeyboardModifier.ShiftModifier))
    assert calls == []
    assert "\n" in popup.original_edit.toPlainText()
    popup.original_edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                              Qt.KeyboardModifier.NoModifier))
    assert calls == ["draft"]
    popup.close()


@pytest.mark.parametrize("automatic", [True, False])
def test_edit_clears_copy_source_and_marks_pending(qapp, automatic):
    popup = PopupBubble(UIConfig(auto_translate_input=automatic))
    popup.display_result(TranslationResult("old", "old translation", "auto", "zh-CN", "microsoft"))
    pyperclip.copy("untouched")
    popup.original_edit.setPlainText("edited")
    assert popup._current_result is None
    assert popup.text_browser.toPlainText() == ""
    assert "待重新翻译" in popup.status_msg.text()
    assert popup._input_debounce_timer.isActive() is automatic
    popup._copy_result()
    assert pyperclip.paste() == "untouched"
    assert not popup.copy_btn.isEnabled()
    popup._clear_input()
    assert popup.status_msg.text() == ""
    assert not popup._input_debounce_timer.isActive()
    popup.close()


def test_reverting_to_previous_query_restarts_debounce(qapp):
    popup = PopupBubble(UIConfig())
    popup.display_loading("old", 0, 0)
    popup.original_edit.setPlainText("draft")
    popup.original_edit.setPlainText("old")
    assert popup._input_debounce_timer.isActive()
    popup.close()


def test_error_offers_retry_and_correct_provider_settings_and_is_not_copied(qapp):
    calls, settings = [], []
    popup = PopupBubble(UIConfig(), on_retranslate=calls.append, on_configure_provider=settings.append)
    popup.display_result(TranslationResult("query", "[Error] 请求超时 <server>", "auto", "zh-CN", "deepseek"))
    assert popup.text_browser.toPlainText() == "请求超时 <server>"
    assert popup.retry_btn.isVisible()
    assert popup.error_settings_btn.isVisible()
    pyperclip.copy("untouched")
    popup._copy_result()
    assert pyperclip.paste() == "untouched"
    popup.retry_btn.click()
    popup.error_settings_btn.click()
    assert calls == ["query"]
    assert settings == ["deepseek"]
    popup.display_loading("query", 0, 0)
    assert not popup.recovery_bar.isVisible()
    popup.display_result(TranslationResult("query", "success", "auto", "zh-CN", "deepseek"))
    assert popup.copy_btn.isEnabled()
    assert not popup.recovery_bar.isVisible()
    popup.close()


def test_open_new_input_removes_error_recovery_controls(qapp):
    popup = PopupBubble(UIConfig(), on_open_settings=lambda: None)
    popup.display_result(TranslationResult("query", "[Error] 网络异常", "auto", "zh-CN", "microsoft"))
    popup.open_for_input()
    assert not popup.recovery_bar.isVisible()
    assert not popup.copy_btn.isEnabled()
    popup.close()


def test_input_setting_defaults_preserve_old_behavior_and_cancel_does_not_apply(qapp):
    config = AppConfig.model_validate({"ui": {}})
    assert config.ui.auto_translate_input
    dialog = SettingsDialog(config)
    dialog.auto_translate_input_check.setChecked(False)
    dialog.reject()
    assert config.ui.auto_translate_input
    dialog = SettingsDialog(config)
    dialog.auto_translate_input_check.setChecked(False)
    dialog._on_save_clicked()
    assert not config.ui.auto_translate_input
    assert not AppConfig.load().ui.auto_translate_input
