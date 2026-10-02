"""三个界面入口共用引擎名称和配置状态。"""

from typing import Callable, Mapping

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from yanxi.core.config import ProviderConfig
from yanxi.core.provider_state import is_microsoft, is_local_service, is_configured


PROVIDER_LABELS = {"microsoft": "微软翻译", "deepseek": "DeepSeek", "openai": "OpenAI",
                   "zhipu": "智谱 GLM", "custom": "自定义服务"}


def provider_label(name: str) -> str:
    return PROVIDER_LABELS.get(name, name)


def provider_status(config: ProviderConfig) -> str:
    if is_microsoft(config) and not config.api_key.strip():
        return "免配置"
    if is_local_service(config):
        return "本地服务"
    return "已配置密钥" if config.api_key.strip() else "未配置密钥"


def provider_menu_label(name: str, config: ProviderConfig | None) -> str:
    label = provider_label(name)
    return f"{label} · {provider_status(config)}" if config else label


def add_provider_actions(menu: QMenu, names: list[str], configs: Mapping[str, ProviderConfig],
                         current: str, on_change: Callable[[str], None]) -> dict[str, QAction]:
    group = QActionGroup(menu)
    menu._provider_group = group
    group.setExclusive(True)
    actions = {}
    for name in names:
        config = configs.get(name)
        label = provider_menu_label(name, config)
        missing = config is not None and not is_configured(config)
        action = QAction(f"{label}（点击设置）" if missing else label, menu, checkable=not missing)
        if not missing:
            action.setChecked(name == current)
            group.addAction(action)
        action.triggered.connect(lambda checked, value=name: on_change(value))
        menu.addAction(action)
        actions[name] = action
    return actions
