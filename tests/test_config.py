"""AppConfig 配置管理模块单元测试"""

from pathlib import Path
from yanche.core.config import AppConfig


def test_default_config():
    config = AppConfig()
    assert config.default_provider == "deepseek"
    assert config.default_source_lang == "auto"
    assert config.default_target_lang == "zh-CN"
    assert "deepseek" in config.providers
    assert "openai" in config.providers
    assert "zhipu" in config.providers
    assert "custom" in config.providers

    active_provider = config.get_active_provider()
    assert active_provider.name == "deepseek"
    assert active_provider.model == "deepseek-chat"


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
    assert fallback_config.default_provider == "deepseek"
    assert fallback_config.default_target_lang == "zh-CN"
