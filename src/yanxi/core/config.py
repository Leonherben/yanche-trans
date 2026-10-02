"""配置管理模型与跨平台持久化 (Configuration Engine)

支持跨平台标准配置目录（XDG_CONFIG_HOME / APPDATA），支持多 API Provider 切换。
"""

from __future__ import annotations
import json
import os
import sys
from enum import Enum
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


class SelectionMode(str, Enum):
    """互斥取词模式；由旧布尔配置推导，避免重复持久化。"""

    MANUAL = "manual"
    AUTOMATIC = "automatic"
    COMPANION = "companion"


class SelectionConfig(BaseModel):
    """划词触发策略配置"""
    enable_x11_primary: bool = True  # Linux 下是否加载 X11 选区服务
    auto_popup_on_selection: bool = True  # 划选松开自动翻译
    auto_popup_only_when_visible: bool = True  # 伴随阅读模式：仅在悬浮窗已打开时才自动划词翻译
    debounce_ms: int = 150           # 选词消抖延迟毫秒
    min_length: int = 1              # 最小划词字符数
    max_length: int = 2000           # 最大划词字符数
    hotkey: str = "<alt>+d"          # 主选词/翻译热键 (Alt + D)
    extra_hotkeys: list[str] = Field(default_factory=list)  # 额外绑定的多快捷键
    enable_mouse_side_button: bool = True  # 启用鼠标侧键 (X1/X2) 划词取词触发
    panic_hotkey: str = "<ctrl>+<alt>+<esc>"  # 紧急逃生键

    def get_mode(self) -> SelectionMode:
        if not self.auto_popup_on_selection:
            return SelectionMode.MANUAL
        if self.auto_popup_only_when_visible:
            return SelectionMode.COMPANION
        return SelectionMode.AUTOMATIC

    def set_mode(self, mode: SelectionMode | str) -> None:
        mode = SelectionMode(mode)
        self.auto_popup_on_selection = mode != SelectionMode.MANUAL
        self.auto_popup_only_when_visible = mode == SelectionMode.COMPANION

    def get_all_hotkeys(self) -> list[str]:
        """获取所有已启用的快捷键列表（去重且保序）"""
        keys: list[str] = []
        if self.hotkey and self.hotkey.strip():
            keys.append(self.hotkey.strip().lower())
        for k in self.extra_hotkeys:
            cleaned = k.strip().lower()
            if cleaned and cleaned not in keys:
                keys.append(cleaned)
        return keys or ["<alt>+d"]

    def set_all_hotkeys(self, hotkeys: list[str]) -> None:
        """更新所有快捷键列表，第一个作为主快捷键，其余作为额外快捷键"""
        cleaned = [k.strip().lower() for k in hotkeys if k and k.strip()]
        unique: list[str] = []
        seen = set()
        for k in cleaned:
            if k not in seen:
                seen.add(k)
                unique.append(k)
        if unique:
            self.hotkey = unique[0]
            self.extra_hotkeys = unique[1:]
        else:
            self.hotkey = "<alt>+d"
            self.extra_hotkeys = []



class UIConfig(BaseModel):
    """悬浮窗 UI 配置"""
    theme: str = "auto"              # auto | dark | light | glass (默认跟随系统)
    font_size: int = 13              # 字号
    min_width: int = 360             # 最小宽度
    min_height: int = 200            # 最小高度
    window_width: int = 450          # 初始/用户拉伸记忆宽度
    window_height: int = 320         # 初始/用户拉伸记忆高度
    fixed_x: Optional[int] = None    # 固定位置 X 坐标
    fixed_y: Optional[int] = None    # 固定位置 Y 坐标
    is_pinned: bool = False          # 是否记忆固定状态
    only_translation: bool = False   # 是否只显示译文卡片
    splitter_sizes: list[int] = Field(default_factory=lambda: [90, 180])  # 原文与译文高度分配
    auto_hide_seconds: int = 8       # 失去交互后自动收起秒数（0表示不自动收起）
    window_opacity: float = 0.95     # 窗口透明度 (0.4 ~ 1.0)
    open_on_startup: bool = True     # 打开应用时是否自动展示悬浮窗 (默认开启)
    auto_translate_input: bool = True  # 保留输入后自动翻译；关闭时回车或按钮提交


class UpdateConfig(BaseModel):
    """在线软件更新偏好"""
    auto_check_update: bool = True     # 启动时是否自动检查更新
    check_interval_hours: int = 24     # 自动检查时间间隔（小时）
    last_check_timestamp: float = 0.0  # 上次检测时间戳


def _default_providers() -> Dict[str, ProviderConfig]:
    return {
        "deepseek": ProviderConfig(
            name="deepseek",
            provider_type="openai_compatible",
            base_url="https://api.deepseek.com/v1",
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            model="deepseek-chat",
        ),
        "microsoft": ProviderConfig(
            name="microsoft",
            provider_type="microsoft",
            base_url="https://www.bing.com/ttranslatev3",
            api_key="",
            model="bing-web",
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
    default_provider: str = "microsoft"
    default_source_lang: str = "auto"
    default_target_lang: str = "zh-CN"
    enable_cache: bool = True
    cache_ttl_days: int = 30
    providers: Dict[str, ProviderConfig] = Field(default_factory=_default_providers)
    selection: SelectionConfig = Field(default_factory=SelectionConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)

    @classmethod
    def get_default_config_path(cls) -> Path:
        """获取遵循平台规范的配置文件路径，若存在旧版 yanche 目录则自动平滑迁移"""
        if sys.platform == "win32":
            base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        target_dir = base_dir / "yanxi"
        old_dir = base_dir / "yanche"
        if not target_dir.exists() and old_dir.exists():
            try:
                import shutil
                shutil.copytree(old_dir, target_dir)
            except Exception:
                pass
        return target_dir / "config.json"

    @classmethod
    def load(cls, path: Optional[Path] = None) -> AppConfig:
        """加载配置文件，若不存在则创建默认配置"""
        config_path = path or cls.get_default_config_path()
        if not config_path.exists():
            instance = cls()
            instance.providers = _default_providers()
            instance.save(config_path)
            return instance

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            instance = cls.model_validate(data)
            # 自动补全缺失的内置提供商（如新增的 microsoft）
            defaults = _default_providers()
            for k, v in defaults.items():
                if k not in instance.providers:
                    instance.providers[k] = v
            return instance
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
