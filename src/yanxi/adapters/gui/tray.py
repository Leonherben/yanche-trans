"""系统托盘指示器 (System Tray Icon)

提供后台常驻状态指示、快速切换翻译模型与目标语言、开关划词监听以及安全退出。
"""

from __future__ import annotations
from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget
from yanxi.core.config import AppConfig, SelectionMode
from yanxi.adapters.gui.selection_modes import MODE_LABELS, add_mode_actions
from yanxi.adapters.gui.languages import language_label, add_language_actions, sync_language_actions
from yanxi.adapters.gui.providers import provider_label, provider_menu_label, add_provider_actions
from yanxi.core.provider_state import is_configured
from yanxi.adapters.gui.theme import AVAILABLE_THEMES, AVAILABLE_OPACITIES
from yanxi.adapters.gui.icon_helper import get_tray_icon


class 言蹊翻译Tray(QSystemTrayIcon):
    """跨平台系统托盘"""

    def __init__(
        self,
        config: AppConfig,
        parent: Optional[QWidget] = None,
        on_open_input: Optional[Callable[[], None]] = None,
        on_toggle_listener: Optional[Callable[[bool], None]] = None,
        on_provider_change: Optional[Callable[[str], None]] = None,
        on_target_lang_change: Optional[Callable[[str], None]] = None,
        on_theme_change: Optional[Callable[[str], None]] = None,
        on_opacity_change: Optional[Callable[[float], None]] = None,
        on_selection_mode_change: Optional[Callable[[SelectionMode], None]] = None,
        on_clear_cache: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
        on_check_update: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_source_lang_change: Optional[Callable[[str], None]] = None,
    ) -> None:
        icon = self._create_vector_icon()
        super().__init__(icon, parent)
        self.config = config
        self.on_open_input = on_open_input
        self.on_toggle_listener = on_toggle_listener
        self.on_provider_change = on_provider_change
        self.on_target_lang_change = on_target_lang_change
        self.on_source_lang_change = on_source_lang_change
        self.on_theme_change = on_theme_change
        self.on_opacity_change = on_opacity_change
        self.on_selection_mode_change = on_selection_mode_change
        self.on_clear_cache = on_clear_cache
        self.on_open_settings = on_open_settings
        self.on_check_update = on_check_update
        self.on_quit = on_quit

        self._listener_enabled = True
        self.provider_actions: dict[str, QAction] = {}
        self.lang_actions: dict[str, QAction] = {}
        self.setToolTip("言蹊翻译")
        self._build_menu()
        self.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """支持鼠标左键双击打开查词窗口，单击或右键弹出菜单"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._handle_open_input()
            return
        menu = self.contextMenu()
        if menu:
            menu.popup(QCursor.pos())

    def _handle_open_input(self) -> None:
        if self.on_open_input:
            self.on_open_input()

    def _create_vector_icon(self) -> QIcon:
        """获取应用托盘图标（优先加载高精度 PNG，缺失时自动回退矢量渲染）"""
        return get_tray_icon()

    def _build_menu(self) -> None:
        menu = QMenu()

        # 0. 主动输入查词
        input_action = QAction("输入查词...", menu)
        input_action.triggered.connect(self._handle_open_input)
        menu.addAction(input_action)

        menu.addSeparator()

        # 1. 状态开关与划选翻译
        self.toggle_action = QAction("取词服务: 开启", menu)
        self.toggle_action.triggered.connect(self._handle_toggle)
        menu.addAction(self.toggle_action)

        self.mode_menu = menu.addMenu("取词模式")
        self.mode_actions = add_mode_actions(
            self.mode_menu, self.config.selection.get_mode(), self._handle_selection_mode_changed
        )
        self.update_selection_mode()

        menu.addSeparator()

        # 2. 翻译引擎单选菜单
        self.provider_menu = menu.addMenu("翻译引擎")
        self.refresh_providers()

        # 3. 与浮窗共用翻译方向选项
        self.source_lang_menu = menu.addMenu("源语言")
        self.target_lang_menu = menu.addMenu("目标语言")
        self.update_translation_direction()

        menu.addSeparator()

        # 4. 主题与外观设置
        theme_menu = menu.addMenu("主题风格")
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        curr_theme = getattr(self.config.ui, "theme", "auto")
        for code, name in AVAILABLE_THEMES:
            act = QAction(name, theme_menu, checkable=True)
            if code == curr_theme:
                act.setChecked(True)
            act.triggered.connect(lambda checked, t=code: self._handle_theme_changed(t))
            theme_group.addAction(act)
            theme_menu.addAction(act)

        opacity_menu = menu.addMenu("窗口透明度")
        opacity_group = QActionGroup(opacity_menu)
        opacity_group.setExclusive(True)
        curr_opacity = getattr(self.config.ui, "window_opacity", 0.95)
        for val, label in AVAILABLE_OPACITIES:
            act = QAction(label, opacity_menu, checkable=True)
            if abs(curr_opacity - val) < 0.03:
                act.setChecked(True)
            act.triggered.connect(lambda checked, o=val: self._handle_opacity_changed(o))
            opacity_group.addAction(act)
            opacity_menu.addAction(act)

        menu.addSeparator()

        # 5. 打开设置
        if self.on_open_settings:
            settings_act = QAction("⚙ 设置...", menu)
            settings_act.triggered.connect(self.on_open_settings)
            menu.addAction(settings_act)

        # 检查更新
        if self.on_check_update:
            update_act = QAction("🔄 检查更新...", menu)
            update_act.triggered.connect(self.on_check_update)
            menu.addAction(update_act)

        # 6. 清理本地缓存
        clear_cache_act = QAction("清空缓存", menu)
        clear_cache_act.triggered.connect(self._handle_clear_cache)
        menu.addAction(clear_cache_act)

        # 6. 逃生键提示 (只读展示)
        panic_hint = QAction(f"强制退出: {self.config.selection.panic_hotkey}", menu)
        panic_hint.setEnabled(False)
        menu.addAction(panic_hint)

        menu.addSeparator()

        # 7. 退出程序
        quit_act = QAction("退出", menu)
        quit_act.triggered.connect(self._handle_quit)
        menu.addAction(quit_act)

        self.setContextMenu(menu)

    def _handle_theme_changed(self, theme_code: str) -> None:
        self.config.ui.theme = theme_code
        self.config.save()
        if self.on_theme_change:
            self.on_theme_change(theme_code)

    def _handle_opacity_changed(self, opacity: float) -> None:
        self.config.ui.window_opacity = opacity
        self.config.save()
        if self.on_opacity_change:
            self.on_opacity_change(opacity)

    def _handle_selection_mode_changed(self, mode: SelectionMode) -> None:
        if self.on_selection_mode_change:
            self.on_selection_mode_change(mode)
        else:
            self.config.selection.set_mode(mode)
            self.config.save()
        self.update_selection_mode()

    def update_selection_mode(self) -> None:
        mode = self.config.selection.get_mode()
        label = MODE_LABELS[mode]
        for candidate, action in self.mode_actions.items():
            action.setChecked(candidate == mode)
        suffix = "（已暂停）" if not self._listener_enabled else ""
        self.mode_menu.setTitle(f"取词模式：{label}{suffix}")
        self.setToolTip(f"言蹊翻译 · {label}{suffix}")

    def _handle_toggle(self) -> None:
        self._listener_enabled = not self._listener_enabled
        if self._listener_enabled:
            self.toggle_action.setText("取词服务: 开启")
        else:
            self.toggle_action.setText("取词服务: 已暂停")
        self.update_selection_mode()

        if self.on_toggle_listener:
            self.on_toggle_listener(self._listener_enabled)

    def _handle_provider_changed(self, provider_name: str) -> None:
        if self.on_provider_change:
            self.on_provider_change(provider_name)
        else:
            config = self.config.providers.get(provider_name)
            if not config or not is_configured(config):
                return
            if provider_name == self.config.default_provider:
                return
            self.config.default_provider = provider_name
            self.config.save()
        self.update_active_provider(self.config.default_provider)

    def update_active_provider(self, provider_name: str) -> None:
        """从外部（如浮窗）同步选中的引擎状态"""
        for name, act in self.provider_actions.items():
            act.setChecked(name == provider_name)
        self.provider_menu.setTitle(f"翻译引擎：{provider_label(provider_name)}")

    def refresh_providers(self) -> None:
        if not self.provider_actions:
            self.provider_actions = add_provider_actions(
                self.provider_menu, list(self.config.providers), self.config.providers,
                self.config.default_provider, self._handle_provider_changed
            )
        group = self.provider_menu._provider_group
        for name, config in self.config.providers.items():
            action = self.provider_actions.get(name)
            if action is None:
                action = QAction(self.provider_menu)
                action.triggered.connect(lambda checked, value=name: self._handle_provider_changed(value))
                self.provider_menu.addAction(action)
                self.provider_actions[name] = action
            ready = is_configured(config)
            label = provider_menu_label(name, config)
            action.setText(label if ready else f"{label}（点击设置）")
            action.setCheckable(ready)
            if ready:
                group.addAction(action)
            else:
                group.removeAction(action)
        for name, action in self.provider_actions.items():
            action.setVisible(name in self.config.providers)
        self.update_active_provider(self.config.default_provider)

    def _handle_lang_changed(self, lang_code: str) -> None:
        if lang_code == self.config.default_target_lang:
            return
        if self.on_target_lang_change:
            self.on_target_lang_change(lang_code)
        else:
            self.config.default_target_lang = lang_code
            self.config.save()
        self.update_translation_direction()

    def _handle_source_lang_changed(self, lang_code: str) -> None:
        if lang_code == self.config.default_source_lang:
            return
        if self.on_source_lang_change:
            self.on_source_lang_change(lang_code)
        else:
            self.config.default_source_lang = lang_code
            self.config.save()
        self.update_translation_direction()

    def update_translation_direction(self) -> None:
        source, target = self.config.default_source_lang, self.config.default_target_lang
        for menu, attribute, current, callback, is_source in (
            (self.source_lang_menu, "source_lang_actions", source, self._handle_source_lang_changed, True),
            (self.target_lang_menu, "lang_actions", target, self._handle_lang_changed, False),
        ):
            actions = getattr(self, attribute, {})
            if not actions:
                actions = add_language_actions(menu, current, callback, source=is_source)
                setattr(self, attribute, actions)
            sync_language_actions(menu, actions, current, source=is_source)
        self.source_lang_menu.setTitle(f"源语言：{language_label(source)}")
        self.target_lang_menu.setTitle(f"目标语言：{language_label(target)}")

    def _handle_clear_cache(self) -> None:
        if self.on_clear_cache:
            self.on_clear_cache()

    def _handle_quit(self) -> None:
        if self.on_quit:
            self.on_quit()


