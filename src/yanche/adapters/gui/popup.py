"""无焦点桌面划词悬浮窗 (Popup GUI)

严格遵循 agent.md 防焦点窃取规范，确保窗口弹出时绝不中断用户的键盘打字与原窗口活动状态。
"""

from __future__ import annotations
from typing import Optional, Callable
from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
import pyperclip
from yanche.core.config import UIConfig
from yanche.core.models import TranslationResult


class PopupBubble(QWidget):
    """防焦点窃取的极简悬浮翻译气泡窗口"""

    # 异步触发信号（线程安全）
    show_translation_signal = Signal(object)
    show_loading_signal = Signal(str, int, int)
    dismiss_signal = Signal(int, int)
    closed = Signal()

    def __init__(self, config: UIConfig, on_retranslate: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self.config = config
        self.on_retranslate = on_retranslate
        self._is_pinned = False
        self._current_result: Optional[TranslationResult] = None

        # 核心防焦点夺取窗口标志：采用 Tool 属性常驻，避免被系统 WM 作为 ToolTip 隐式强退
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._drag_pos = QPoint()
        self._init_ui()

        # 自动收起定时器
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self._on_auto_hide)

        # 绑定信号
        self.show_translation_signal.connect(self.display_result)
        self.show_loading_signal.connect(self.display_loading)
        self.dismiss_signal.connect(self.dismiss_if_outside)

    def _init_ui(self) -> None:
        self.setMinimumWidth(320)
        self.setMaximumWidth(self.config.max_width)
        self.setMinimumHeight(140)
        self.setMaximumHeight(self.config.max_height)

        # 主卡片容器
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self._apply_style()

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(6)

        # 1. 顶栏：Provider 标签 + 耗时 + 钉住 + 关闭
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        self.provider_label = QLabel("言澈翻译", self)
        self.provider_label.setStyleSheet("color: #79c0ff; font-weight: bold; font-size: 11px;")
        top_bar.addWidget(self.provider_label)

        self.latency_label = QLabel("", self)
        self.latency_label.setStyleSheet("color: #8b949e; font-size: 10px;")
        top_bar.addWidget(self.latency_label)

        top_bar.addStretch()

        self.pin_btn = QPushButton("📌", self)
        self.pin_btn.setFixedSize(22, 22)
        self.pin_btn.setToolTip("固定浮窗")
        self.pin_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pin_btn.clicked.connect(self._toggle_pin)
        self.pin_btn.setStyleSheet("background: transparent; border: none; font-size: 11px;")
        top_bar.addWidget(self.pin_btn)

        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(self.hide)
        self.close_btn.setStyleSheet("background: transparent; border: none; color: #8b949e; font-weight: bold;")
        top_bar.addWidget(self.close_btn)

        container_layout.addLayout(top_bar)

        # 2. 原文展示区域（灰色小字预览）
        self.original_label = QLabel(self)
        self.original_label.setWordWrap(True)
        self.original_label.setStyleSheet("color: #8b949e; font-size: 11px; padding-bottom: 2px;")
        self.original_label.setMaximumHeight(40)
        container_layout.addWidget(self.original_label)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #30363d; max-height: 1px;")
        container_layout.addWidget(line)

        # 3. 译文富文本区
        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.text_browser.setStyleSheet(
            f"background: transparent; border: none; color: #e6edf3; font-size: {self.config.font_size}px; line-height: 1.4;"
        )
        container_layout.addWidget(self.text_browser)

        # 4. 底栏操作栏
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)

        self.status_msg = QLabel("", self)
        self.status_msg.setStyleSheet("color: #3fb950; font-size: 10px;")
        bottom_bar.addWidget(self.status_msg)

        bottom_bar.addStretch()

        self.copy_btn = QPushButton("复制译文", self)
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_btn.setStyleSheet(
            "background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 2px 8px; font-size: 11px;"
        )
        self.copy_btn.clicked.connect(self._copy_result)
        bottom_bar.addWidget(self.copy_btn)

        container_layout.addLayout(bottom_bar)

        # 整体布局
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.addWidget(self.container)

    def _apply_style(self) -> None:
        """深色拟物扁平主题"""
        self.container.setStyleSheet("""
            QFrame#container {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
            }
        """)

    def _toggle_pin(self) -> None:
        self._is_pinned = not self._is_pinned
        if self._is_pinned:
            self.pin_btn.setText("📍")
            self.pin_btn.setToolTip("浮窗已固定（不会自动收起，点击取消固定）")
            self.pin_btn.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; border-radius: 4px; font-size: 11px; padding: 1px;"
            )
            self.auto_hide_timer.stop()
            self.status_msg.setText("📌 浮窗已固定")
            QTimer.singleShot(1500, lambda: self.status_msg.setText(""))
        else:
            self.pin_btn.setText("📌")
            self.pin_btn.setToolTip("固定浮窗")
            self.pin_btn.setStyleSheet("background: transparent; border: none; font-size: 11px;")
            if self.config.auto_hide_seconds > 0:
                self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)
            self.status_msg.setText("浮窗已取消固定")
            QTimer.singleShot(1500, lambda: self.status_msg.setText(""))

    def _copy_result(self) -> None:
        if self._current_result and self._current_result.is_success():
            pyperclip.copy(self._current_result.translated_text)
            self.status_msg.setText("已复制到剪贴板 ✔")
            QTimer.singleShot(1500, lambda: self.status_msg.setText(""))

    def _on_auto_hide(self) -> None:
        if self._is_pinned:
            return
        if not self.underMouse():
            self.hide()

    def display_loading(self, text: str, cursor_x: int, cursor_y: int) -> None:
        """显示加载状态并定位在鼠标光标周围"""
        self.provider_label.setText("言澈翻译 ⏳")
        self.latency_label.setText("正在翻译中...")
        display_preview = text if len(text) <= 60 else text[:57] + "..."
        self.original_label.setText(display_preview)
        self.text_browser.setHtml("<span style='color: #8b949e; font-style: italic;'>正在向 API 请求译文...</span>")
        self.adjust_position(cursor_x, cursor_y)
        self.show()

    def display_result(self, result: TranslationResult) -> None:
        """展示完成的翻译结果"""
        self._current_result = result
        if result.from_cache:
            self.provider_label.setText(f"⚡ {result.provider}")
            self.latency_label.setText("本地秒开缓存")
        else:
            self.provider_label.setText(f"🤖 {result.provider}")
            self.latency_label.setText(f"{result.latency_ms}ms")

        # 截断或完整展示原文
        orig = result.original_text
        preview = orig if len(orig) <= 60 else orig[:57] + "..."
        self.original_label.setText(preview)

        # 格式化输出译文（成功使用 Markdown 原生排版，失败呈现错误样式）
        if not result.is_success():
            html_err = result.translated_text.replace("\n", "<br>")
            self.text_browser.setHtml(f"<span style='color: #f85149; font-weight: 500;'>{html_err}</span>")
        else:
            self.text_browser.setMarkdown(result.translated_text)

        # 重新自适应高度并确保可见
        self.adjustSize()
        self.show()

        if self._is_pinned:
            self.auto_hide_timer.stop()
        elif self.config.auto_hide_seconds > 0:
            self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)

    def dismiss_if_outside(self, cursor_x: int = 0, cursor_y: int = 0) -> None:
        """如果浮窗正处于显示状态且未钉住，当点击落在浮窗几何区域外部时平滑收起"""
        if not self.isVisible() or self._is_pinned:
            return

        # 使用 Qt 原生逻辑光标坐标，天然消除 Surface 2.0x 高分屏 DPI 缩放影响
        mouse_pos = QCursor.pos()
        if not self.frameGeometry().contains(mouse_pos):
            self.hide()

    def hideEvent(self, event) -> None:
        self.closed.emit()
        super().hideEvent(event)

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
        w = max(self.width(), 320)
        h = max(self.height(), 160)

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

    # 鼠标拖动支持
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def enterEvent(self, event) -> None:
        """鼠标悬停浮窗上时暂停自动收起"""
        self.auto_hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """鼠标移出浮窗后若未钉住则重启自动收起"""
        if not self._is_pinned and self.config.auto_hide_seconds > 0:
            self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)
