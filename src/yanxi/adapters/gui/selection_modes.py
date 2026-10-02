"""浮窗、托盘和设置共用的取词模式文案及菜单。"""

from typing import Callable

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu

from yanxi.core.config import SelectionMode


MODE_LABELS = {
    SelectionMode.MANUAL: "快捷键翻译",
    SelectionMode.AUTOMATIC: "划选即翻译",
    SelectionMode.COMPANION: "划词翻译（仅开窗）",
}
MODE_DESCRIPTIONS = {
    SelectionMode.MANUAL: "选中文字后按快捷键翻译，不自动翻译。",
    SelectionMode.AUTOMATIC: "选中文字并松开鼠标后自动翻译，浮窗收起时也会触发。",
    SelectionMode.COMPANION: "仅浮窗打开时划词自动翻译；浮窗收起后不打扰，按快捷键唤出。",
}


def add_mode_actions(
    menu: QMenu,
    current_mode: SelectionMode,
    on_change: Callable[[SelectionMode], None],
) -> dict[SelectionMode, QAction]:
    group = QActionGroup(menu)
    group.setExclusive(True)
    menu.setToolTipsVisible(True)
    actions = {}
    for mode in SelectionMode:
        action = QAction(MODE_LABELS[mode], menu, checkable=True)
        action.setChecked(mode == current_mode)
        action.setToolTip(MODE_DESCRIPTIONS[mode])
        action.triggered.connect(lambda checked, selected=mode: on_change(selected))
        group.addAction(action)
        menu.addAction(action)
        actions[mode] = action
    return actions
