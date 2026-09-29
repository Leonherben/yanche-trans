"""系统托盘指示器 (System Tray Icon)

提供后台常驻状态指示、快速切换翻译模型与目标语言、开关划词监听以及安全退出。
"""

from __future__ import annotations
from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget
from quicktrans.core.config import AppConfig


class QuickTransTray(QSystemTrayIcon):
    """跨平台系统托盘"""

    def __init__(
        self,
        config: AppConfig,
        parent: Optional[QWidget] = None,
        on_toggle_listener: Optional[Callable[[bool], None]] = None,
        on_provider_change: Optional[Callable[[str], None]] = None,
        on_target_lang_change: Optional[Callable[[str], None]] = None,
        on_clear_cache: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        icon = self._create_vector_icon()
        super().__init__(icon, parent)
        self.config = config
        self.on_toggle_listener = on_toggle_listener
        self.on_provider_change = on_provider_change
        self.on_target_lang_change = on_target_lang_change
        self.on_clear_cache = on_clear_cache
        self.on_quit = on_quit

        self._listener_enabled = True
        self.setToolTip("QuickTrans 划词翻译 (正在监听)")
        self._build_menu()

    def _create_vector_icon(self) -> QIcon:
        """程序化绘制优雅的暗青色托盘图标，避免对外部 PNG 文件的依赖"""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制圆角背景
        painter.setBrush(QColor("#1f6feb"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

        # 绘制字母 "译" 或 "T"
        painter.setPen(QColor("#ffffff"))
        font = QFont("Sans-Serif", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "译")
        painter.end()

        return QIcon(pixmap)

    def _build_menu(self) -> None:
        menu = QMenu()

        # 1. 状态开关
        self.toggle_action = QAction("✔ 划词监听: 开启", menu)
        self.toggle_action.triggered.connect(self._handle_toggle)
        menu.addAction(self.toggle_action)

        menu.addSeparator()

        # 2. 翻译引擎单选菜单
        provider_menu = menu.addMenu("🌐 翻译引擎 (Provider)")
        for name in self.config.providers.keys():
            act = QAction(name, provider_menu, checkable=True)
            if name == self.config.default_provider:
                act.setChecked(True)
            act.triggered.connect(lambda checked, p=name: self._handle_provider_changed(p))
            provider_menu.addAction(act)

        # 3. 目标语言选择
        lang_menu = menu.addMenu("🗣 目标语言")
        langs = [("简体中文", "zh-CN"), ("English", "en"), ("日本語", "ja"), ("한국어", "ko")]
        for title, code in langs:
            act = QAction(title, lang_menu, checkable=True)
            if code == self.config.default_target_lang:
                act.setChecked(True)
            act.triggered.connect(lambda checked, c=code: self._handle_lang_changed(c))
            lang_menu.addAction(act)

        menu.addSeparator()

        # 4. 清理本地缓存
        clear_cache_act = QAction("🧹 清理本地翻译缓存", menu)
        clear_cache_act.triggered.connect(self._handle_clear_cache)
        menu.addAction(clear_cache_act)

        # 5. 逃生键提示 (只读展示)
        panic_hint = QAction(f"⚡ 逃生热键: {self.config.selection.panic_hotkey}", menu)
        panic_hint.setEnabled(False)
        menu.addAction(panic_hint)

        menu.addSeparator()

        # 6. 退出程序
        quit_act = QAction("🚪 退出 QuickTrans", menu)
        quit_act.triggered.connect(self._handle_quit)
        menu.addAction(quit_act)

        self.setContextMenu(menu)

    def _handle_toggle(self) -> None:
        self._listener_enabled = not self._listener_enabled
        if self._listener_enabled:
            self.toggle_action.setText("✔ 划词监听: 开启")
            self.setToolTip("QuickTrans 划词翻译 (正在监听)")
        else:
            self.toggle_action.setText("✖ 划词监听: 已暂停")
            self.setToolTip("QuickTrans 划词翻译 (已暂停)")

        if self.on_toggle_listener:
            self.on_toggle_listener(self._listener_enabled)

    def _handle_provider_changed(self, provider_name: str) -> None:
        self.config.default_provider = provider_name
        self.config.save()
        self._build_menu()
        if self.on_provider_change:
            self.on_provider_change(provider_name)

    def _handle_lang_changed(self, lang_code: str) -> None:
        self.config.default_target_lang = lang_code
        self.config.save()
        self._build_menu()
        if self.on_target_lang_change:
            self.on_target_lang_change(lang_code)

    def _handle_clear_cache(self) -> None:
        if self.on_clear_cache:
            self.on_clear_cache()

    def _handle_quit(self) -> None:
        if self.on_quit:
            self.on_quit()
