"""验证菜单可发现性、配置持久化和窄窗口布局。"""

import pytest

from yanxi.adapters.gui.popup import PopupBubble
from yanxi.adapters.gui.tray import 言蹊翻译Tray
from yanxi.core.config import AppConfig, UIConfig


def test_popup_language_menu_has_source_detection_and_target_choices(qapp):
    popup = PopupBubble(UIConfig())
    menu = popup._create_language_menu()
    source, target = [action.menu() for action in menu.actions()]
    assert source.title() == "源语言"
    assert target.title() == "目标语言"
    assert source.actions()[0].text() == "自动检测"
    assert source.actions()[0].isChecked()
    assert all(action.text() != "自动检测" for action in target.actions())
    next(action for action in target.actions() if action.text() == "日本語").trigger()
    assert popup.direction_btn.text() == "自动检测 → 日本語 ▾"
    assert not popup.isVisible()
    menu.deleteLater()
    popup.close()


def test_custom_language_codes_survive_settings_and_show_current_choice(controller):
    config = controller.config
    config.default_source_lang = "fr"
    config.default_target_lang = "de"
    controller.on_settings_saved(config)
    assert controller.popup.direction_btn.text() == "fr → de ▾"
    assert controller.tray.source_lang_actions["fr"].isChecked()
    assert controller.tray.lang_actions["de"].isChecked()
    assert not controller.tray.lang_actions["de"].isEnabled()
    controller.set_target_lang("en")
    assert "de" not in controller.tray.lang_actions
    assert controller.config.default_source_lang == "fr"


def test_tray_actions_persist_direction_without_controller(qapp):
    config = AppConfig()
    tray = 言蹊翻译Tray(config)
    tray.source_lang_actions["en"].trigger()
    tray.lang_actions["ja"].trigger()
    saved = AppConfig.load()
    assert (saved.default_source_lang, saved.default_target_lang) == ("en", "ja")
    assert tray.source_lang_menu.title() == "源语言：English"
    assert tray.target_lang_menu.title() == "目标语言：日本語"
    tray.hide()


@pytest.mark.parametrize("width", [360, 450])
def test_direction_and_mode_fit_narrow_header(qapp, width):
    popup = PopupBubble(UIConfig())
    popup.resize(width, 320)
    popup.show()
    qapp.processEvents()
    assert popup.width() == width
    assert popup.direction_btn.geometry().right() < popup.mode_btn.geometry().left()
    assert popup.direction_btn.width() >= popup.direction_btn.sizeHint().width()
    assert popup.mode_btn.width() >= popup.mode_btn.sizeHint().width()
    assert popup.direction_btn.y() > popup.provider_btn.y()
    popup.close()
