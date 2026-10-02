"""设置中心 SettingsDialog 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from yanxi.core.config import AppConfig, SelectionMode
from yanxi.adapters.gui.settings_dialog import SettingsDialog


def test_settings_dialog_init(qapp, tmp_path):
    cfg_file = tmp_path / "config.json"
    config = AppConfig()
    config.save(cfg_file)

    saved_configs = []
    dialog = SettingsDialog(
        config=config,
        on_save=lambda cfg: saved_configs.append(cfg),
    )

    assert dialog.tab_widget.count() == 4
    assert dialog.provider_combo.count() >= 5
    assert dialog.provider_combo.currentData() == "microsoft"
    assert "微软翻译" in dialog.provider_combo.currentText()
    assert dialog.default_check.isChecked()

    # 验证快捷键 Tab 预填
    assert dialog.main_hotkey_edit.text() == "<alt>+d"
    assert dialog.mouse_side_check.isChecked()
    assert dialog.selection_mode_combo.currentData() == SelectionMode.COMPANION
    assert "仅浮窗打开时" in dialog.selection_mode_hint.text()
    assert dialog.windowTitle() == "言蹊翻译 - 设置"

    # 验证选项卡切换与更新 Tab
    dialog.switch_to_tab(3)
    assert dialog.tab_widget.currentIndex() == 3
    assert dialog.check_update_btn is not None
    assert dialog.auto_update_check.isChecked()

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
    dialog.select_provider("deepseek")
    dialog.key_edit.setText("sk-test-deepseek-key-123")
    dialog.model_edit.setText("deepseek-coder")
    dialog.default_check.click()  # 设为默认

    # 2. 修改快捷键 Tab
    dialog.main_hotkey_edit.setText("<alt>+f")
    dialog.new_hotkey_edit.setText("ctrl+alt+w")
    dialog.add_hotkey_btn.click()
    dialog.selection_mode_combo.setCurrentIndex(
        dialog.selection_mode_combo.findData(SelectionMode.AUTOMATIC)
    )
    assert dialog.extra_hotkeys_list.count() == 1
    assert dialog.extra_hotkeys_list.item(0).text() == "<ctrl>+<alt>+<w>"

    # 3. 修改外观 Tab
    dialog.opacity_slider.setValue(80)
    dialog.auto_hide_spin.setValue(12)
    assert dialog.open_on_startup_check.isChecked() is True
    dialog.open_on_startup_check.setChecked(False)

    # 4. 点击保存
    dialog._on_save_clicked()

    assert len(saved_configs) == 1
    saved = saved_configs[0]
    assert saved.default_provider == "deepseek"
    assert saved.providers["deepseek"].api_key == "sk-test-deepseek-key-123"
    assert saved.providers["deepseek"].model == "deepseek-coder"
    assert saved.selection.hotkey == "<alt>+f"
    assert saved.selection.extra_hotkeys == ["<ctrl>+<alt>+<w>"]
    assert saved.selection.auto_popup_only_when_visible is False
    assert saved.ui.window_opacity == 0.8
    assert saved.ui.auto_hide_seconds == 12
    assert saved.ui.open_on_startup is False

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


def test_settings_dialog_update_callbacks(qapp):
    from yanxi.core.updater import UpdateInfo
    config = AppConfig()
    dialog = SettingsDialog(config=config)

    # 模拟检查发现新版本
    info_new = UpdateInfo(
        current_version="0.1.0",
        latest_version="0.2.0",
        has_update=True,
        release_notes="修复图标与更新机制",
        published_at="2026-10-02",
        release_url="https://github.com/Leonherben/yanxi-trans/releases/tag/v0.2.0",
    )
    dialog._on_update_result(info_new)
    assert "发现新版本" in dialog.update_status_label.text()
    assert dialog.download_btn.isEnabled()
    assert "修复图标" in dialog.release_notes_edit.toPlainText()

    # 模拟已经是最新版本
    info_latest = UpdateInfo(
        current_version="0.2.0",
        latest_version="0.2.0",
        has_update=False,
    )
    dialog._on_update_result(info_latest)
    assert "已是最新版本" in dialog.update_status_label.text()
    assert not dialog.download_btn.isEnabled()

    dialog.close()

