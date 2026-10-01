"""AppConfig 配置管理模块单元测试"""

from pathlib import Path
from yanxi.core.config import AppConfig


def test_default_config():
    config = AppConfig()
    assert config.default_provider == "microsoft"
    assert config.default_source_lang == "auto"
    assert config.default_target_lang == "zh-CN"
    assert "microsoft" in config.providers
    assert "deepseek" in config.providers
    assert "openai" in config.providers
    assert "zhipu" in config.providers
    assert "custom" in config.providers

    active_provider = config.get_active_provider()
    assert active_provider.name == "microsoft"
    assert active_provider.model == "bing-web"


def test_config_save_and_load(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    config = AppConfig()
    config.default_provider = "openai"
    config.default_target_lang = "ja"
    config.providers["openai"].api_key = "sk-test-custom-key"
    config.save(cfg_file)

    assert cfg_file.exists()

    loaded = AppConfig.load(cfg_file)
    assert loaded.default_provider == "openai"
    assert loaded.default_target_lang == "ja"
    assert loaded.providers["openai"].api_key == "sk-test-custom-key"
    assert loaded.get_active_provider().name == "openai"


def test_config_corrupted_fallback(tmp_path: Path):
    cfg_file = tmp_path / "bad_config.json"
    cfg_file.write_text("{ this is bad json: invalid }", encoding="utf-8")

    # 遇到损坏文件应安全回退为默认配置，不引发致命崩溃
    fallback_config = AppConfig.load(cfg_file)
    assert fallback_config.default_provider == "microsoft"
    assert fallback_config.default_target_lang == "zh-CN"


def test_selection_config_defaults():
    config = AppConfig()
    assert config.selection.hotkey == "<alt>+d"
    assert config.selection.extra_hotkeys == []
    assert config.selection.enable_mouse_side_button is True
    assert config.selection.auto_popup_on_selection is False


def test_selection_config_multiple_hotkeys():
    config = AppConfig()
    assert config.selection.get_all_hotkeys() == ["<alt>+d"]

    # 设置多个快捷键，包含重复项
    config.selection.set_all_hotkeys(["<alt>+d", "<ctrl>+<alt>+t", "<alt>+d", "<f2>"])
    assert config.selection.hotkey == "<alt>+d"
    assert config.selection.extra_hotkeys == ["<ctrl>+<alt>+t", "<f2>"]
    assert config.selection.get_all_hotkeys() == ["<alt>+d", "<ctrl>+<alt>+t", "<f2>"]

    # 清空时回退为默认
    config.selection.set_all_hotkeys([])
    assert config.selection.hotkey == "<alt>+d"
    assert config.selection.extra_hotkeys == []


