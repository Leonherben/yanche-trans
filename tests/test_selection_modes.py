"""旧配置兼容、模式切换和多个 UI 入口的联动回归测试。"""

import json

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QMenu

from yanxi.core.config import AppConfig, SelectionConfig, SelectionMode, UIConfig
from yanxi.adapters.gui.popup import PopupBubble
from yanxi.adapters.gui.selection_modes import MODE_LABELS, add_mode_actions
from yanxi.adapters.gui.settings_dialog import SettingsDialog


@pytest.mark.parametrize("auto,visible,expected", [
    (False, False, SelectionMode.MANUAL),
    (False, True, SelectionMode.MANUAL),
    (True, False, SelectionMode.AUTOMATIC),
    (True, True, SelectionMode.COMPANION),
])
def test_legacy_modes_round_trip(tmp_path, auto, visible, expected):
    config = AppConfig(selection=SelectionConfig(
        auto_popup_on_selection=auto, auto_popup_only_when_visible=visible,
    ))
    assert config.selection.get_mode() == expected
    path = tmp_path / "legacy.json"
    config.save(path)
    assert AppConfig.load(path).selection.get_mode() == expected
    assert "mode" not in json.loads(path.read_text(encoding="utf-8"))["selection"]


def test_invalid_mode_does_not_change_configuration():
    config = SelectionConfig()
    before = config.model_dump()
    with pytest.raises(ValueError):
        config.set_mode("unknown")
    assert config.model_dump() == before


def test_mode_menu_is_exclusive_and_routes_selected_mode(qapp):
    selected = []
    menu = QMenu()
    actions = add_mode_actions(menu, SelectionMode.COMPANION, selected.append)
    actions[SelectionMode.MANUAL].trigger()
    assert selected == [SelectionMode.MANUAL]
    assert [mode for mode, action in actions.items() if action.isChecked()] == [SelectionMode.MANUAL]
    assert all(action.toolTip() for action in actions.values())


def test_companion_mode_survives_mouse_leave_and_unpin(qapp):
    popup = PopupBubble(UIConfig(is_pinned=False), selection_config=SelectionConfig())
    popup.show()
    popup.leaveEvent(QEvent(QEvent.Type.Leave))
    assert not popup.auto_hide_timer.isActive()
    popup._toggle_pin()
    popup._toggle_pin()
    assert not popup.auto_hide_timer.isActive()
    popup._set_selection_mode(SelectionMode.AUTOMATIC)
    assert popup.auto_hide_timer.isActive()
    popup.hide()
    popup._set_selection_mode(SelectionMode.MANUAL)
    assert not popup.isVisible()
    popup.close()


def test_settings_cancel_keeps_current_mode(qapp):
    config = AppConfig()
    dialog = SettingsDialog(config)
    dialog.selection_mode_combo.setCurrentIndex(
        dialog.selection_mode_combo.findData(SelectionMode.MANUAL)
    )
    assert "不自动翻译" in dialog.selection_mode_hint.text()
    dialog.reject()
    assert config.selection.get_mode() == SelectionMode.COMPANION


@pytest.mark.parametrize("mode", list(SelectionMode))
def test_tray_mode_updates_popup_listeners_and_saved_config(controller, mode):
    controller.tray.mode_actions[mode].trigger()
    assert controller.config.selection.get_mode() == mode
    assert MODE_LABELS[mode] in controller.popup.mode_btn.text()
    assert controller.tray.mode_actions[mode].isChecked()
    selection_listener = next(item for item in controller.listeners if "auto_popup" in item.options)
    assert selection_listener.options["auto_popup"] == (mode != SelectionMode.MANUAL)
    assert selection_listener.options["auto_popup_only_when_visible"] == (mode == SelectionMode.COMPANION)
    saved = json.loads(controller.config.get_default_config_path().read_text(encoding="utf-8"))
    assert SelectionConfig.model_validate(saved["selection"]).get_mode() == mode
    assert not controller.popup.isVisible()


def test_changing_mode_does_not_resume_paused_listeners(controller):
    controller.tray._handle_toggle()
    assert not controller._listener_enabled
    controller.popup._set_selection_mode(SelectionMode.AUTOMATIC)
    assert all(not listener.running for listener in controller.listeners)
    assert "已暂停" in controller.popup.mode_btn.text()
    assert controller.tray.mode_actions[SelectionMode.AUTOMATIC].isChecked()
    controller.tray._handle_toggle()
    assert all(listener.running for listener in controller.listeners)
    assert "划选即翻译" in controller.popup.mode_btn.text()


def test_settings_apply_updates_popup_references_and_tray(controller):
    previous_selection = controller.popup.selection_config
    dialog = SettingsDialog(controller.config, on_save=controller.on_settings_saved)
    dialog.selection_mode_combo.setCurrentIndex(
        dialog.selection_mode_combo.findData(SelectionMode.MANUAL)
    )
    dialog._on_save_clicked()
    assert controller.popup.selection_config is controller.config.selection
    assert controller.popup.selection_config is not previous_selection
    assert controller.popup.config is controller.config.ui
    assert "快捷键翻译" in controller.popup.mode_btn.text()
    assert controller.tray.mode_actions[SelectionMode.MANUAL].isChecked()
