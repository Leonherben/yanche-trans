"""浮窗与托盘共用的语言名称和互斥菜单。"""

from typing import Callable

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu


LANGUAGES = {"auto": "自动检测", "zh-CN": "简体中文", "en": "English",
             "ja": "日本語", "ko": "한국어"}


def language_label(code: str) -> str:
    return LANGUAGES.get(code, code)


def add_language_actions(menu: QMenu, current: str, on_change: Callable[[str], None],
                         *, source: bool = False) -> dict[str, QAction]:
    group = QActionGroup(menu)
    group.setExclusive(True)
    codes = [code for code in LANGUAGES if source or code != "auto"]
    if current not in codes:
        codes.append(current)
    actions = {}
    for code in codes:
        action = QAction(language_label(code), menu, checkable=True)
        action.setChecked(code == current)
        if code not in LANGUAGES or (code == "auto" and not source):
            action.setEnabled(False)
        else:
            action.triggered.connect(lambda checked, value=code: on_change(value))
        group.addAction(action)
        menu.addAction(action)
        actions[code] = action
    return actions


def sync_language_actions(menu: QMenu, actions: dict[str, QAction], current: str,
                          *, source: bool = False) -> None:
    """更新检查状态，复用自定义语言动作，避免清空正在使用的 Qt 菜单。"""
    standard = {code for code in LANGUAGES if source or code != "auto"}
    custom = getattr(menu, "_custom_language_action", None)
    for code in list(actions):
        if code not in standard:
            custom = actions.pop(code)
    if current not in standard:
        if custom is None:
            custom = QAction(menu, checkable=True)
            custom.setEnabled(False)
            group = next(iter(actions.values())).actionGroup()
            group.addAction(custom)
            menu.addAction(custom)
        custom.setText(language_label(current))
        custom.setVisible(True)
        actions[current] = custom
    elif custom is not None:
        custom.setChecked(False)
        custom.setVisible(False)
    menu._custom_language_action = custom
    for code, action in actions.items():
        action.setChecked(code == current)
