"""配置管理模型与跨平台持久化 (Configuration Engine)

支持跨平台标准配置目录（XDG_CONFIG_HOME / APPDATA），支持多 API Provider 切换。
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """单个翻译服务提供商的配置"""
    name: str = "deepseek"
    provider_type: str = "openai_compatible"  # openai_compatible | baidu | etc.
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout_seconds: float = 10.0
    system_prompt: str = (
        "You are a professional, accurate translator. "
        "Translate the input text naturally into the requested target language. "
        "Output ONLY the translated result without any quotes, conversational filler, or commentary. "
        "If the input is a single term or phrase, provide a concise explanation and phonetic if helpful."
    )


class SelectionConfig(BaseModel):
    """划词触发策略配置"""
    enable_x11_primary: bool = True  # Linux 下鼠标划选松开自动翻译
    debounce_ms: int = 200           # 选词消抖延迟毫秒
    min_length: int = 1              # 最小划词字符数
    max_length: int = 2000           # 最大划词字符数
    hotkey: str = "<ctrl>+<alt>+t"   # 通用选词/翻译热键
    panic_hotkey: str = "<ctrl>+<alt>+<esc>"  # 紧急逃生键


class UIConfig(BaseModel):
    """悬浮窗 UI 配置"""
    theme: str = "dark"              # dark | light | auto
    font_size: int = 13              # 字号
    min_width: int = 360             # 最小宽度
    min_height: int = 200            # 最小高度
    window_width: int = 450          # 初始/用户拉伸记忆宽度
    window_height: int = 320         # 初始/用户拉伸记忆高度
    fixed_x: Optional[int] = None    # 固定位置 X 坐标
    fixed_y: Optional[int] = None    # 固定位置 Y 坐标
    is_pinned: bool = False          # 是否记忆固定状态
    auto_hide_seconds: int = 8       # 失去交互后自动收起秒数（0表示不自动收起）
    window_opacity: float = 0.98     # 窗口透明度


def _default_providers() -> Dict[str, ProviderConfig]:
    return {
        "deepseek": ProviderConfig(
            name="deepseek",
            provider_type="openai_compatible",
            base_url="https://api.deepseek.com/v1",
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            model="deepseek-chat",
        ),
        "openai": ProviderConfig(
            name="openai",
            provider_type="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            model="gpt-4o-mini",
        ),
        "zhipu": ProviderConfig(
            name="zhipu",
            provider_type="openai_compatible",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key=os.environ.get("ZHIPU_API_KEY", ""),
            model="glm-4-flash",
        ),
        "custom": ProviderConfig(
            name="custom",
            provider_type="openai_compatible",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="qwen2.5:1.5b",
        ),
    }


class AppConfig(BaseModel):
    """应用总体配置"""
    default_provider: str = "deepseek"
    default_source_lang: str = "auto"
    default_target_lang: str = "zh-CN"
    enable_cache: bool = True
    cache_ttl_days: int = 30
    providers: Dict[str, ProviderConfig] = Field(default_factory=_default_providers)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @classmethod
    def get_default_config_path(cls) -> Path:
        """获取遵循平台规范的配置文件路径"""
        if sys.platform == "win32":
            base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return base_dir / "yanche" / "config.json"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> AppConfig:
        """加载配置文件，若不存在则创建默认配置"""
        config_path = path or cls.get_default_config_path()
        if not config_path.exists():
            instance = cls()
            # 预设常用供应商模板
            instance.providers = {
                "deepseek": ProviderConfig(
                    name="deepseek",
                    provider_type="openai_compatible",
                    base_url="https://api.deepseek.com/v1",
                    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                    model="deepseek-chat",
                ),
                "openai": ProviderConfig(
                    name="openai",
                    provider_type="openai_compatible",
                    base_url="https://api.openai.com/v1",
                    api_key=os.environ.get("OPENAI_API_KEY", ""),
                    model="gpt-4o-mini",
                ),
                "zhipu": ProviderConfig(
                    name="zhipu",
                    provider_type="openai_compatible",
                    base_url="https://open.bigmodel.cn/api/paas/v4",
                    api_key=os.environ.get("ZHIPU_API_KEY", ""),
                    model="glm-4-flash",
                ),
                "custom": ProviderConfig(
                    name="custom",
                    provider_type="openai_compatible",
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",
                    model="qwen2.5:1.5b",
                ),
            }
            instance.save(config_path)
            return instance

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        except Exception:
            # 读取损坏时安全回退，不抛致命崩溃
            return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """保存配置到文件"""
        config_path = path or self.get_default_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    def get_active_provider(self) -> ProviderConfig:
        """获取当前激活的 Provider 配置"""
        return self.providers.get(
            self.default_provider,
            ProviderConfig(name=self.default_provider, api_key="")
        )
