import pytest

from yanxi.core.config import AppConfig, ProviderConfig
from yanxi.core.provider_state import is_configured, is_local_service
from yanxi.adapters.gui.providers import provider_status


@pytest.mark.parametrize("url,local", [
    ("http://localhost:11434/v1", True), ("http://127.0.0.1:11434/v1", True),
    ("http://[::1]:11434/v1", True), ("http://127.5.1.2/v1", True),
    ("https://localhost.example.com/v1", False), ("https://example.com/localhost", False),
    ("https://127.0.0.1.example.com/v1", False), ("https://example.com", False),
])
def test_local_service_detection_uses_host_not_substring(url, local):
    config = ProviderConfig(name="custom", base_url=url, api_key="")
    assert is_local_service(config) is local
    assert is_configured(config) is local


def test_configuration_status_does_not_claim_connectivity():
    config = AppConfig()
    assert provider_status(config.providers["microsoft"]) == "免配置"
    cloud = config.providers["deepseek"]
    cloud.api_key = "  "
    assert provider_status(cloud) == "未配置密钥"
    assert not is_configured(cloud)
    cloud.api_key = "test-key"
    assert provider_status(cloud) == "已配置密钥"
    local = config.providers["custom"]
    local.api_key = ""
    assert provider_status(local) == "本地服务"


@pytest.mark.parametrize("entry", ["popup", "tray"])
def test_unconfigured_provider_opens_its_settings_without_switching(controller, monkeypatch, entry):
    controller.config.providers["deepseek"].api_key = ""
    controller.tray.refresh_providers()
    module = __import__("yanxi.main", fromlist=["create_translator"])
    monkeypatch.setattr(module, "create_translator", lambda config: pytest.fail("should not recreate translator"))
    if entry == "popup":
        menu = controller.popup._create_provider_menu()
        action = next(action for action in menu.actions() if "DeepSeek" in action.text())
    else:
        action = controller.tray.provider_actions["deepseek"]
    assert "未配置密钥" in action.text()
    action.trigger()
    assert controller.config.default_provider == "microsoft"
    assert controller.popup._current_provider == "microsoft"
    assert controller._settings_dialog.current_provider_name == "deepseek"
    assert controller._settings_dialog.provider_combo.currentData() == "deepseek"
    assert controller._settings_dialog.tab_widget.currentIndex() == 0
    controller._settings_dialog.reject()
    if entry == "popup":
        menu.deleteLater()


def test_saved_key_refreshes_menus_and_preserves_provider_codes(controller):
    controller.open_provider_settings("deepseek")
    dialog = controller._settings_dialog
    dialog.key_edit.setText("test-key")
    dialog.default_check.click()
    dialog._on_save_clicked()
    assert controller.config.default_provider == "deepseek"
    assert controller.config.providers["deepseek"].api_key == "test-key"
    assert controller.popup.provider_btn.text() == "DeepSeek"
    action = controller.tray.provider_actions["deepseek"]
    assert "已配置密钥" in action.text()
    assert action.isChecked()


def test_missing_key_cannot_be_set_as_default(controller):
    controller.config.providers["deepseek"].api_key = ""
    controller.open_provider_settings("deepseek")
    dialog = controller._settings_dialog
    dialog.default_check.click()
    assert dialog.working_config.default_provider == "microsoft"
    assert not dialog.default_check.isChecked()
    assert "请先填写" in dialog.test_status_label.text()
    dialog.reject()
