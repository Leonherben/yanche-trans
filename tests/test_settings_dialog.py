"""偏好设置中心 SettingsDialog 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from yanxi.core.config import AppConfig
from yanxi.adapters.gui.settings_dialog import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_settings_dialog_init(qapp, tmp_path):
    cfg_file = tmp_path / "config.json"
    config = AppConfig()
    config.save(cfg_file)

    saved_configs = []
    dialog = SettingsDialog(
        config=config,
        on_save=lambda cfg: saved_configs.append(cfg),
    )

    assert dialog.tab_widget.count() == 3
    assert dialog.provider_combo.count() >= 5
    assert dialog.provider_combo.currentText() == "microsoft"
    assert dialog.default_check.isChecked()

    # 验证快捷键 Tab 预填
    assert dialog.main_hotkey_edit.text() == "<alt>+d"
    assert dialog.mouse_side_check.isChecked()

    dialog.close()


def test_settings_dialog_modify_and_save(qapp, tmp_path):
    cfg_file = tmp_path / "config.json"
    config = AppConfig()
    config.save(cfg_file)

    saved_configs = []
    dialog = SettingsDialog(
        config=config,
        on_save=lambda cfg: saved_configs.append(cfg),
    )

    # 1. 切换为 deepseek 并修改 API Key 和模型
    dialog.provider_combo.setCurrentText("deepseek")
    dialog.key_edit.setText("sk-test-deepseek-key-123")
    dialog.model_edit.setText("deepseek-coder")
    dialog.default_check.click()  # 设为默认

    # 2. 修改快捷键 Tab
    dialog.main_hotkey_edit.setText("<alt>+f")
    dialog.new_hotkey_edit.setText("ctrl+alt+w")
    dialog.add_hotkey_btn.click()
    assert dialog.extra_hotkeys_list.count() == 1
    assert dialog.extra_hotkeys_list.item(0).text() == "<ctrl>+<alt>+<w>"

    # 3. 修改外观 Tab
    dialog.opacity_slider.setValue(80)
    dialog.auto_hide_spin.setValue(12)

    # 4. 点击保存
    dialog._on_save_clicked()

    assert len(saved_configs) == 1
    saved = saved_configs[0]
    assert saved.default_provider == "deepseek"
    assert saved.providers["deepseek"].api_key == "sk-test-deepseek-key-123"
    assert saved.providers["deepseek"].model == "deepseek-coder"
    assert saved.selection.hotkey == "<alt>+f"
    assert saved.selection.extra_hotkeys == ["<ctrl>+<alt>+<w>"]
    assert saved.ui.window_opacity == 0.8
    assert saved.ui.auto_hide_seconds == 12

    dialog.close()


def test_settings_dialog_toggle_key_echo(qapp):
    config = AppConfig()
    dialog = SettingsDialog(config=config)

    assert dialog.eye_btn.text() == "👁"
    dialog._toggle_key_echo()
    assert dialog.eye_btn.text() == "🔒"
    dialog._toggle_key_echo()
    assert dialog.eye_btn.text() == "👁"

    dialog.close()


def test_settings_dialog_test_connection_callback(qapp):
    config = AppConfig()
    dialog = SettingsDialog(config=config)

    dialog._on_test_finished(True, "测试连通成功 (100ms)")
    assert "✔" in dialog.test_status_label.text()

    dialog._on_test_finished(False, "网络超时")
    assert "✖" in dialog.test_status_label.text()

    dialog.close()
