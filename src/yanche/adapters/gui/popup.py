"""无焦点桌面划词悬浮窗 (Popup GUI)

严格遵循 agent.md 防焦点窃取规范，确保窗口弹出时绝不中断用户的键盘打字与原窗口活动状态。
支持四角与四边无级自由缩放、QSplitter 原文/译文高度比例调节、一键切换“只显示译文”、
多主题切换（Dark/Light/Glass/Auto跟随系统）以及自定义透明度调节。
"""

from __future__ import annotations
from typing import Optional, Callable
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QEvent, QRect
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
import pyperclip
from yanche.core.config import UIConfig
from yanche.core.models import TranslationResult
from yanche.adapters.gui.theme import (
    AVAILABLE_THEMES,
    AVAILABLE_OPACITIES,
    get_effective_theme,
    get_theme_stylesheet,
    get_theme_menu_style,
)

RESIZE_MARGIN = 10  # 边缘缩放感应带宽 (像素)

CURSOR_MAP = {
    "top_left": Qt.CursorShape.SizeFDiagCursor,
    "bottom_right": Qt.CursorShape.SizeFDiagCursor,
    "top_right": Qt.CursorShape.SizeBDiagCursor,
    "bottom_left": Qt.CursorShape.SizeBDiagCursor,
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
}


class PopupBubble(QWidget):
    """防焦点窃取的高颜值多主题悬浮翻译气泡窗口"""

    # 异步触发信号（线程安全）
    show_translation_signal = Signal(object)
    show_loading_signal = Signal(str, int, int)
    dismiss_signal = Signal(int, int)
    closed = Signal()

    def __init__(
        self,
        config: UIConfig,
        on_retranslate: Optional[Callable[[str], None]] = None,
        on_switch_provider: Optional[Callable[[str, str], None]] = None,
        on_save_config: Optional[Callable[[], None]] = None,
        on_clear_cache: Optional[Callable[[], None]] = None,
        available_providers: Optional[list[str]] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.on_retranslate = on_retranslate
        self.on_switch_provider = on_switch_provider
        self.on_save_config = on_save_config
        self.on_clear_cache = on_clear_cache
        self.available_providers = available_providers or ["deepseek", "openai", "zhipu", "custom"]
        self._current_provider = "deepseek"
        self._last_requested_text = ""
        self._current_result: Optional[TranslationResult] = None

        # 主题与透明度状态
        self._theme = getattr(self.config, "theme", "auto")
        self._opacity = getattr(self.config, "window_opacity", 0.95)

        # 仅显示译文与固定位置状态
        self._only_translation = getattr(self.config, "only_translation", False)
        self._is_pinned = getattr(self.config, "is_pinned", False)
        if (
            getattr(self.config, "fixed_x", None) is not None
            and getattr(self.config, "fixed_y", None) is not None
        ):
            self._fixed_pos: Optional[QPoint] = QPoint(self.config.fixed_x, self.config.fixed_y)
        else:
            self._fixed_pos = None

        # 核心防焦点夺取窗口标志：采用 Tool 属性常驻，避免被系统 WM 作为 ToolTip 隐式强退
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 鼠标拖动与多向缩放状态变量
        self.setMouseTracking(True)
        self._drag_pos = QPoint()
        self._resize_region: Optional[str] = None
        self._resize_start_pos = QPoint()
        self._resize_start_geom: Optional[QRect] = None

        # 配置保存防抖定时器
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_current_config)

        # 自动收起定时器
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self._on_auto_hide)

        self._init_ui()

        # 恢复记忆的固定位置
        if self._is_pinned and self._fixed_pos is not None:
            self.move(self._fixed_pos)

        # 监听系统明暗主题切换信号（当主题设为跟随系统时实时热重载）
        app = QGuiApplication.instance()
        if app:
            try:
                app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
            except Exception:
                pass

        # 绑定跨线程/异步信号
        self.show_translation_signal.connect(self.display_result)
        self.show_loading_signal.connect(self.display_loading)
        self.dismiss_signal.connect(self.dismiss_if_outside)

    def _init_ui(self) -> None:
        min_w = getattr(self.config, "min_width", 360)
        min_h = getattr(self.config, "min_height", 200)
        self.setMinimumSize(min_w, min_h)

        # 恢复记忆的尺寸
        init_w = max(getattr(self.config, "window_width", 450), min_w)
        init_h = max(getattr(self.config, "window_height", 320), min_h)
        self.resize(init_w, init_h)

        # 主卡片外壳容器
        self.container = QFrame(self)
        self.container.setObjectName("main_container")
        self.container.setMouseTracking(True)
        self.container.installEventFilter(self)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 8)
        container_layout.setSpacing(8)

        # ==================== 1. 顶栏 (Header) ====================
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        # 品牌标识
        self.brand_badge = QLabel("言澈", self)
        self.brand_badge.setObjectName("brand_badge")
        top_bar.addWidget(self.brand_badge)

        # Provider 切换胶囊按钮
        self.provider_btn = QPushButton(f"🤖 {self._current_provider} ▾", self)
        self.provider_btn.setObjectName("provider_btn")
        self.provider_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.provider_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.provider_btn.setToolTip("点击切换翻译模型/服务商")
        self.provider_btn.clicked.connect(self._show_provider_menu)
        self.provider_label = self.provider_btn  # 保持属性兼容
        top_bar.addWidget(self.provider_btn)

        top_bar.addStretch()

        # 钉住/固定按钮
        self.pin_btn = QPushButton("📌", self)
        self.pin_btn.setObjectName("pin_btn")
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.clicked.connect(self._toggle_pin)
        top_bar.addWidget(self.pin_btn)

        # 更多操作菜单按钮
        self.more_btn = QPushButton("⋯", self)
        self.more_btn.setObjectName("action_btn")
        self.more_btn.setFixedSize(26, 26)
        self.more_btn.setToolTip("更多设置与选项 (主题/透明度)")
        self.more_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.clicked.connect(self._show_more_menu)
        top_bar.addWidget(self.more_btn)

        # 关闭按钮
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setObjectName("close_btn")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        top_bar.addWidget(self.close_btn)

        container_layout.addLayout(top_bar)

        # ==================== 2. 原文卡片 (Original Card) ====================
        self.orig_card = QFrame(self)
        self.orig_card.setObjectName("card_frame")
        orig_layout = QVBoxLayout(self.orig_card)
        orig_layout.setContentsMargins(10, 8, 10, 8)
        orig_layout.setSpacing(6)

        # 原文预览区（内嵌平滑滚动）
        orig_scroll = QScrollArea(self)
        orig_scroll.setWidgetResizable(True)
        orig_scroll.setFrameShape(QFrame.Shape.NoFrame)
        orig_scroll.setStyleSheet("background: transparent; border: none;")

        self.original_label = QLabel(self)
        self.original_label.setObjectName("original_text")
        self.original_label.setWordWrap(True)
        self.original_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        orig_scroll.setWidget(self.original_label)
        orig_layout.addWidget(orig_scroll, stretch=1)

        # 原文卡片底栏：词数统计 + 复制原文
        orig_bottom = QHBoxLayout()
        orig_bottom.setContentsMargins(0, 0, 0, 0)
        self.orig_meta_label = QLabel("0 字符", self)
        self.orig_meta_label.setStyleSheet("color: #6e7681; font-size: 10px;")
        orig_bottom.addWidget(self.orig_meta_label)

        orig_bottom.addStretch()

        self.copy_orig_btn = QPushButton("📋 复制原文", self)
        self.copy_orig_btn.setObjectName("subtle_btn")
        self.copy_orig_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_orig_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_orig_btn.clicked.connect(self._copy_original)
        orig_bottom.addWidget(self.copy_orig_btn)

        orig_layout.addLayout(orig_bottom)

        # ==================== 3. 译文卡片 (Translation Card) ====================
        self.trans_card = QFrame(self)
        self.trans_card.setObjectName("card_frame")
        trans_layout = QVBoxLayout(self.trans_card)
        trans_layout.setContentsMargins(10, 8, 10, 8)
        trans_layout.setSpacing(6)

        # 译文 Markdown 富文本展示（自适应伸展）
        self.text_browser = QTextBrowser(self)
        self.text_browser.setObjectName("trans_browser")
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        trans_layout.addWidget(self.text_browser, stretch=1)

        # 译文卡片底栏：耗时/缓存 + 状态提示 + 复制译文按钮
        trans_bottom = QHBoxLayout()
        trans_bottom.setContentsMargins(0, 0, 0, 0)

        self.latency_label = QLabel("", self)
        self.latency_label.setStyleSheet("color: #8b949e; font-size: 10px;")
        trans_bottom.addWidget(self.latency_label)

        self.status_msg = QLabel("", self)
        self.status_msg.setStyleSheet("color: #3fb950; font-size: 10px; font-weight: 500; margin-left: 6px;")
        trans_bottom.addWidget(self.status_msg)

        trans_bottom.addStretch()

        self.copy_btn = QPushButton("📋 复制译文", self)
        self.copy_btn.setObjectName("action_btn_primary")
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_result)
        trans_bottom.addWidget(self.copy_btn)

        trans_layout.addLayout(trans_bottom)

        # ==================== 4. 垂直分割器 (QSplitter) ====================
        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.setObjectName("card_splitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.orig_card)
        self.splitter.addWidget(self.trans_card)

        # 加载记忆的卡片高度比例
        saved_sizes = getattr(self.config, "splitter_sizes", [90, 180])
        if saved_sizes and len(saved_sizes) == 2:
            self.splitter.setSizes(saved_sizes)
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        if self._only_translation:
            self.orig_card.hide()

        container_layout.addWidget(self.splitter, stretch=1)

        # ==================== 5. 底部右下角缩放手柄 ====================
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        self.hint_label = QLabel("Esc 关闭 · 四角/边缘均可自由缩放", self)
        self.hint_label.setStyleSheet("color: #6e7681; font-size: 10px;")
        bottom_bar.addWidget(self.hint_label)

        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self)
        self.size_grip.setToolTip("拖拽调整窗口大小")
        self.size_grip.setFixedSize(14, 14)
        self.size_grip.setCursor(Qt.CursorShape.SizeFDiagCursor)
        bottom_bar.addWidget(self.size_grip)

        container_layout.addLayout(bottom_bar)

        # 整体布局外边距
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.addWidget(self.container)

        # 应用主题与透明度
        self.apply_theme(self._theme, self._opacity)

    def apply_theme(self, theme_name: Optional[str] = None, opacity: Optional[float] = None) -> None:
        """动态应用主题与透明度"""
        if theme_name is not None:
            self._theme = theme_name
            self.config.theme = theme_name
        if opacity is not None:
            self._opacity = max(0.4, min(1.0, opacity))
            self.config.window_opacity = self._opacity

        effective = get_effective_theme(self._theme)
        qss = get_theme_stylesheet(effective)
        self.setStyleSheet(qss)
        self.setWindowOpacity(self._opacity)

        self._update_pin_ui()
        self._save_current_config()

    def _on_system_color_scheme_changed(self) -> None:
        """系统主题明暗切换时触发热重载"""
        if self._theme == "auto":
            self.apply_theme("auto")

    def _update_pin_ui(self) -> None:
        """根据当前固定状态与主题刷新图钉按钮外观"""
        effective = get_effective_theme(self._theme)
        if self._is_pinned:
            self.pin_btn.setText("📍")
            self.pin_btn.setToolTip("浮窗已固定在此位置（点击取消固定，恢复跟随光标）")
            self.pin_btn.setStyleSheet("""
                QPushButton#pin_btn {
                    background-color: #1f6feb;
                    color: #ffffff;
                    border: 1px solid #388bfd;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)
        else:
            self.pin_btn.setText("📌")
            self.pin_btn.setToolTip("固定浮窗位置（选词时保持在固定坐标，不跟随光标）")
            hover_bg = "#eaeef2" if effective == "light" else "rgba(255, 255, 255, 0.12)"
            self.pin_btn.setStyleSheet(f"""
                QPushButton#pin_btn {{
                    background-color: transparent;
                    border: none;
                    font-size: 12px;
                    border-radius: 4px;
                }}
                QPushButton#pin_btn:hover {{
                    background-color: {hover_bg};
                }}
            """)

    def _toggle_pin(self) -> None:
        """切换窗口固定状态并持久化"""
        self._is_pinned = not self._is_pinned
        self.config.is_pinned = self._is_pinned

        if self._is_pinned:
            self._fixed_pos = self.pos()
            self.config.fixed_x = self._fixed_pos.x()
            self.config.fixed_y = self._fixed_pos.y()
            self.auto_hide_timer.stop()
            self._flash_status("📌 浮窗已固定在当前位置")
        else:
            self._fixed_pos = None
            self.config.fixed_x = None
            self.config.fixed_y = None
            if self.config.auto_hide_seconds > 0:
                self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)
            self._flash_status("浮窗已取消固定（恢复跟随光标）")

        self._update_pin_ui()
        self._save_current_config()

    def _toggle_only_translation(self, checked: bool) -> None:
        """切换是否只显示译文卡片"""
        self._only_translation = checked
        self.config.only_translation = checked

        if self._only_translation:
            self.orig_card.hide()
            self._flash_status("已切换为：只显示译文")
        else:
            self.orig_card.show()
            saved_sizes = getattr(self.config, "splitter_sizes", [90, 180])
            if saved_sizes and len(saved_sizes) == 2:
                self.splitter.setSizes(saved_sizes)
            self._flash_status("已恢复：显示原文与译文")

        self._save_current_config()

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """记录用户拖拽调节的卡片高度比例"""
        sizes = self.splitter.sizes()
        if len(sizes) == 2 and sizes[0] > 0 and sizes[1] > 0:
            self.config.splitter_sizes = sizes
            self._save_timer.start(500)

    def _reset_window_geometry(self) -> None:
        """重置窗口尺寸、分割比例与固定位置"""
        self._is_pinned = False
        self._fixed_pos = None
        self._only_translation = False
        self.config.is_pinned = False
        self.config.only_translation = False
        self.config.fixed_x = None
        self.config.fixed_y = None
        self.config.window_width = 450
        self.config.window_height = 320
        self.config.splitter_sizes = [90, 180]
        self.resize(450, 320)
        self.orig_card.show()
        self.splitter.setSizes([90, 180])
        self._update_pin_ui()
        self._save_current_config()
        self._flash_status("🔄 已恢复默认尺寸、比例与跟随模式")

    def _save_current_config(self) -> None:
        if self.on_save_config:
            try:
                self.on_save_config()
            except Exception as e:
                print(f"⚠️ 保存 UI 配置失败: {e}")

    def _on_auto_hide(self) -> None:
        if self._is_pinned:
            return
        if not self.underMouse():
            self.hide()

    def _flash_status(self, msg: str, duration_ms: int = 1800) -> None:
        self.status_msg.setText(msg)
        QTimer.singleShot(duration_ms, lambda: self.status_msg.setText(""))

    def _flash_orig_meta(self, msg: str, duration_ms: int = 1800) -> None:
        old = self.orig_meta_label.text()
        self.orig_meta_label.setText(msg)
        QTimer.singleShot(duration_ms, lambda: self.orig_meta_label.setText(old))

    @staticmethod
    def _format_meta(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return "0 字符"
        chars = len(cleaned)
        words = len(cleaned.split())
        if " " in cleaned and words > 1:
            return f"{words} 词 · {chars} 字符"
        return f"{chars} 字符"

    def _copy_original(self) -> None:
        text = self._last_requested_text or (
            self._current_result.original_text if self._current_result else ""
        )
        if text:
            pyperclip.copy(text)
            self._flash_orig_meta("原文已复制 ✔")

    def _copy_result(self) -> None:
        if self._current_result and self._current_result.is_success():
            pyperclip.copy(self._current_result.translated_text)
            self._flash_status("译文已复制 ✔")

    def _show_more_menu(self) -> None:
        """弹出更多选项设置菜单 (集成主题与透明度)"""
        effective = get_effective_theme(self._theme)
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(effective))

        # 1. 钉住/固定
        pin_text = "📍 取消固定 (恢复跟随光标)" if self._is_pinned else "📌 固定在当前位置"
        act_pin = menu.addAction(pin_text)
        act_pin.triggered.connect(self._toggle_pin)

        # 2. 只显示译文
        act_only_trans = menu.addAction("👁️ 只显示译文")
        act_only_trans.setCheckable(True)
        act_only_trans.setChecked(self._only_translation)
        act_only_trans.triggered.connect(self._toggle_only_translation)

        menu.addSeparator()

        # 3. 🎨 主题风格子菜单
        theme_menu = menu.addMenu("🎨 主题风格")
        theme_menu.setStyleSheet(get_theme_menu_style(effective))
        for code, name in AVAILABLE_THEMES:
            is_curr = (self._theme == code)
            mark = "✔ " if is_curr else "   "
            act = theme_menu.addAction(f"{mark}{name}")
            act.triggered.connect(lambda checked, t=code: self._handle_theme_change(t))

        # 4. 🪟 窗口透明度子菜单
        opacity_menu = menu.addMenu("🪟 窗口透明度")
        opacity_menu.setStyleSheet(get_theme_menu_style(effective))
        for val, label in AVAILABLE_OPACITIES:
            is_curr = abs(self._opacity - val) < 0.03
            mark = "✔ " if is_curr else "   "
            act = opacity_menu.addAction(f"{mark}{label}")
            act.triggered.connect(lambda checked, o=val: self._handle_opacity_change(o))

        menu.addSeparator()

        # 5. 恢复默认尺寸与比例
        act_reset = menu.addAction("🔄 恢复默认尺寸与比例")
        act_reset.triggered.connect(self._reset_window_geometry)

        # 6. 清空本地缓存
        if self.on_clear_cache:
            act_cache = menu.addAction("🗑️ 清空本地翻译缓存")
            act_cache.triggered.connect(self._handle_clear_cache)

        pos = self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 2))
        menu.exec(pos)

    def _handle_theme_change(self, theme_code: str) -> None:
        self.apply_theme(theme_name=theme_code)
        name_map = dict(AVAILABLE_THEMES)
        self._flash_status(f"主题已切换为：{name_map.get(theme_code, theme_code)}")

    def _handle_opacity_change(self, opacity: float) -> None:
        self.apply_theme(opacity=opacity)
        self._flash_status(f"透明度已设为：{int(opacity * 100)}%")

    def _handle_clear_cache(self) -> None:
        if self.on_clear_cache:
            self.on_clear_cache()
            self._flash_status("本地缓存已清空 🗑️")

    def _show_provider_menu(self) -> None:
        """点击浮窗左上角小图标，弹出可供选择的翻译引擎菜单"""
        effective = get_effective_theme(self._theme)
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(effective))

        curr = self._current_provider
        for p in self.available_providers:
            mark = "✔ " if p == curr else "   "
            act = menu.addAction(f"{mark}{p}")
            act.triggered.connect(lambda checked, name=p: self._handle_provider_switch(name))

        pos = self.provider_btn.mapToGlobal(QPoint(0, self.provider_btn.height() + 2))
        menu.exec(pos)

    def _handle_provider_switch(self, provider_name: str) -> None:
        self._current_provider = provider_name
        self.provider_btn.setText(f"🤖 {provider_name} ▾")
        if self.on_switch_provider:
            text_to_translate = self._last_requested_text or (
                self._current_result.original_text if self._current_result else ""
            )
            self.on_switch_provider(provider_name, text_to_translate)

    def display_loading(self, text: str, cursor_x: int, cursor_y: int) -> None:
        """显示加载状态并智能定位（未固定时避让光标，固定时坚守坐标）"""
        self._last_requested_text = text
        self.provider_btn.setText(f"⏳ {self._current_provider} ▾")
        self.latency_label.setText("正在请求翻译...")
        self.status_msg.setText("")

        self.original_label.setText(text)
        self.orig_meta_label.setText(self._format_meta(text))

        effective = get_effective_theme(self._theme)
        loading_color = "#57606a" if effective == "light" else "#8b949e"
        self.text_browser.setHtml(
            f"<span style='color: {loading_color}; font-style: italic;'>正在向 API 请求译文...</span>"
        )

        if self._is_pinned and self._fixed_pos is not None:
            self.move(self._fixed_pos)
        elif self._is_pinned and getattr(self.config, "fixed_x", None) is not None:
            self._fixed_pos = QPoint(self.config.fixed_x, self.config.fixed_y)
            self.move(self._fixed_pos)
        else:
            self.adjust_position(cursor_x, cursor_y)
            if self._is_pinned:
                # 初始固定但未保存坐标的边界场景
                self._fixed_pos = self.pos()
                self.config.fixed_x = self.pos().x()
                self.config.fixed_y = self.pos().y()
                self._save_current_config()

        self.show()

    def display_result(self, result: TranslationResult) -> None:
        """展示完成的翻译结果"""
        self._current_result = result
        self._current_provider = result.provider
        self._last_requested_text = result.original_text

        if result.from_cache:
            self.provider_btn.setText(f"⚡ {result.provider} ▾")
            self.latency_label.setText("⚡ 本地缓存")
        else:
            self.provider_btn.setText(f"🤖 {result.provider} ▾")
            self.latency_label.setText(f"⏱️ {result.latency_ms:.0f}ms")

        self.original_label.setText(result.original_text)
        self.orig_meta_label.setText(self._format_meta(result.original_text))

        if not result.is_success():
            html_err = result.translated_text.replace("\n", "<br>")
            self.text_browser.setHtml(
                f"<span style='color: #f85149; font-weight: 500;'>{html_err}</span>"
            )
        else:
            self.text_browser.setMarkdown(result.translated_text)

        if self._is_pinned:
            if self._fixed_pos is not None:
                self.move(self._fixed_pos)
            self.auto_hide_timer.stop()
        elif self.config.auto_hide_seconds > 0:
            self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)

        self.show()

    def dismiss_if_outside(self, cursor_x: int = 0, cursor_y: int = 0) -> None:
        """如果浮窗正处于显示状态且未钉住，当点击落在浮窗几何区域外部时平滑收起"""
        if not self.isVisible() or self._is_pinned:
            return

        mouse_pos = QCursor.pos()
        if not self.frameGeometry().contains(mouse_pos):
            self.hide()

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        min_w = getattr(self.config, "min_width", 360)
        min_h = getattr(self.config, "min_height", 200)
        if self.width() >= min_w and self.height() >= min_h:
            self.config.window_width = self.width()
            self.config.window_height = self.height()
            self._save_timer.start(500)

    def adjust_position(self, cursor_x: int = 0, cursor_y: int = 0) -> None:
        """根据当前鼠标位置和多屏幕边界进行智能边缘检测避让"""
        pos = QCursor.pos()
        target_x = pos.x() + 15
        target_y = pos.y() + 15

        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        if not screen:
            self.move(target_x, target_y)
            return

        geom = screen.availableGeometry()
        w = max(self.width(), 360)
        h = max(self.height(), 200)

        # 靠右溢出翻转
        if target_x + w > geom.right():
            target_x = pos.x() - w - 10
            if target_x < geom.left():
                target_x = geom.left() + 10

        # 靠下溢出翻转
        if target_y + h > geom.bottom():
            target_y = pos.y() - h - 10
            if target_y < geom.top():
                target_y = geom.top() + 10

        self.move(target_x, target_y)

    # ==================== 四角与四边无级自由缩放支持 ====================
    def _get_resize_region(self, pos: QPoint) -> Optional[str]:
        """检测鼠标落点是否处于 4 个角落或 4 条边缘感应区内"""
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        m = RESIZE_MARGIN

        on_left = 0 <= x <= m
        on_right = (w - m) <= x <= w
        on_top = 0 <= y <= m
        on_bottom = (h - m) <= y <= h

        if on_top and on_left:
            return "top_left"
        elif on_top and on_right:
            return "top_right"
        elif on_bottom and on_left:
            return "bottom_left"
        elif on_bottom and on_right:
            return "bottom_right"
        elif on_left:
            return "left"
        elif on_right:
            return "right"
        elif on_top:
            return "top"
        elif on_bottom:
            return "bottom"
        return None

    def _do_resize(self, cur_pos: QPoint) -> None:
        """执行四角/边缘无级缩放计算"""
        if not self._resize_region or not self._resize_start_geom:
            return
        dx = cur_pos.x() - self._resize_start_pos.x()
        dy = cur_pos.y() - self._resize_start_pos.y()

        orig = self._resize_start_geom
        x, y, w, h = orig.x(), orig.y(), orig.width(), orig.height()
        min_w = getattr(self.config, "min_width", 360)
        min_h = getattr(self.config, "min_height", 200)

        # 水平方向计算
        if "right" in self._resize_region:
            w = max(min_w, orig.width() + dx)
        elif "left" in self._resize_region:
            new_w = max(min_w, orig.width() - dx)
            x = orig.x() + (orig.width() - new_w)
            w = new_w

        # 垂直方向计算
        if "bottom" in self._resize_region:
            h = max(min_h, orig.height() + dy)
        elif "top" in self._resize_region:
            new_h = max(min_h, orig.height() - dy)
            y = orig.y() + (orig.height() - new_h)
            h = new_h

        self.setGeometry(x, y, w, h)
        self.config.window_width = self.width()
        self.config.window_height = self.height()
        if self._is_pinned:
            self._fixed_pos = self.pos()
            self.config.fixed_x = self.x()
            self.config.fixed_y = self.y()
        self._save_timer.start(500)

    def eventFilter(self, watched, event) -> bool:
        """拦截主卡片外壳事件，支持贴边/贴角的顺滑拉伸缩放"""
        if watched == self.container:
            if event.type() == QEvent.Type.MouseMove:
                pos_in_bubble = self.container.mapTo(self, event.pos())
                region = self._get_resize_region(pos_in_bubble)
                if not event.buttons():
                    if region and region in CURSOR_MAP:
                        self.setCursor(CURSOR_MAP[region])
                        self.container.setCursor(CURSOR_MAP[region])
                    else:
                        self.unsetCursor()
                        self.container.unsetCursor()
                elif event.buttons() == Qt.MouseButton.LeftButton and self._resize_region:
                    self._do_resize(event.globalPosition().toPoint())
                    return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    pos_in_bubble = self.container.mapTo(self, event.pos())
                    region = self._get_resize_region(pos_in_bubble)
                    if region:
                        self._resize_region = region
                        self._resize_start_pos = event.globalPosition().toPoint()
                        self._resize_start_geom = self.geometry()
                        return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._resize_region:
                    self._resize_region = None
                    self._resize_start_geom = None
                    self.unsetCursor()
                    self.container.unsetCursor()
                    if self._is_pinned:
                        self._fixed_pos = self.pos()
                        self.config.fixed_x = self.x()
                        self.config.fixed_y = self.y()
                        self._flash_status("📍 固定位置与尺寸已更新")
                    self._save_timer.start(500)
                    return True

        return super().eventFilter(watched, event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            region = self._get_resize_region(event.pos())
            if region:
                self._resize_region = region
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                event.accept()
                return

            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self._resize_region:
                self._do_resize(event.globalPosition().toPoint())
                event.accept()
                return
            elif not self._drag_pos.isNull():
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()
                return

        # 无按键悬停更新光标形态
        region = self._get_resize_region(event.pos())
        if region and region in CURSOR_MAP:
            self.setCursor(CURSOR_MAP[region])
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resize_region:
                self._resize_region = None
                self._resize_start_geom = None
                self.unsetCursor()
                if self._is_pinned:
                    self._fixed_pos = self.pos()
                    self.config.fixed_x = self.x()
                    self.config.fixed_y = self.y()
                    self._flash_status("📍 固定位置与尺寸已更新")
                self._save_timer.start(500)
                event.accept()
                return

            self._drag_pos = QPoint()
            if self._is_pinned:
                self._fixed_pos = self.pos()
                self.config.fixed_x = self.x()
                self.config.fixed_y = self.y()
                self._save_current_config()
                self._flash_status("📍 固定位置已更新")
            event.accept()

    def enterEvent(self, event) -> None:
        """鼠标悬停浮窗上时暂停自动收起"""
        self.auto_hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """鼠标移出浮窗后若未钉住则重启自动收起"""
        if not self._is_pinned and self.config.auto_hide_seconds > 0:
            self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)
        self.unsetCursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)
