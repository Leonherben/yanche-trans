"""无焦点桌面划词悬浮窗 (Popup GUI)

严格遵循 agent.md 防焦点窃取规范，确保窗口弹出时绝不中断用户的键盘打字与原窗口活动状态。
支持四角与四边无级自由缩放、QSplitter 原文/译文高度比例调节、一键切换“只显示译文”、
多主题切换（Dark/Light/Glass/Auto跟随系统）、无级百分比透明度滑动条 (40%~100%) 以及多快捷键/侧键触发。
"""

from __future__ import annotations
from html import escape
from typing import Optional, Callable, List
from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QEvent, QRect
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QTextCursor, QPainter, QPen

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSlider,
    QSplitter,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)
import pyperclip
import sys
from yanxi.core.config import UIConfig, SelectionConfig, SelectionMode, ProviderConfig
from yanxi.core.provider_state import is_configured

if sys.platform == "win32":
    try:
        from yanxi.adapters.gui.windows_effects import enable_blur_behind, disable_blur_behind
    except Exception:
        enable_blur_behind = None
        disable_blur_behind = None
else:
    enable_blur_behind = None
    disable_blur_behind = None

from yanxi.adapters.gui.providers import provider_label, provider_menu_label, add_provider_actions
from yanxi.adapters.gui.selection_modes import MODE_LABELS, MODE_DESCRIPTIONS, add_mode_actions
from yanxi.adapters.gui.languages import language_label, add_language_actions
from yanxi.core.models import TranslationResult
from yanxi.adapters.gui.theme import (
    AVAILABLE_THEMES,
    get_effective_theme,
    get_theme_stylesheet,
    get_theme_menu_style,
)
from yanxi.adapters.selection.hotkey_fallback import (
    normalize_to_pynput,
    format_for_display,
    is_valid_pynput_hotkey,
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


def qkey_to_pynput(modifiers: Qt.KeyboardModifiers, key: int, text: str = "") -> Optional[str]:
    """将 Qt 按键事件转换为 pynput 快捷键字符串"""
    if key in (
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Meta,
        Qt.Key.Key_AltGr,
    ):
        return None

    parts = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("<ctrl>")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("<alt>")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("<shift>")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("<cmd>")

    key_part = None
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        key_part = chr(key).lower()
    elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        key_part = chr(key)
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        key_part = f"<f{key - Qt.Key.Key_F1 + 1}>"
    elif key == Qt.Key.Key_Space:
        key_part = "<space>"
    elif key == Qt.Key.Key_Tab:
        key_part = "<tab>"
    elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        key_part = "<enter>"
    elif key == Qt.Key.Key_Backspace:
        key_part = "<backspace>"
    elif text and len(text) == 1 and text.isprintable():
        key_part = text.lower()

    if not key_part:
        return None
    parts.append(key_part)
    return "+".join(parts)


class KeyRecorderEdit(QLineEdit):
    """支持按键录制与手动输入的快捷键控件"""

    def __init__(self, initial_hotkey: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._is_recording: bool = False
        self._raw_pynput: str = ""
        self.setPlaceholderText("点击“录制”或手动输入 (如 Alt+D)")
        self._update_style(normal=True)
        if initial_hotkey:
            self.set_hotkey_value(initial_hotkey)

    def _update_style(self, normal: bool = True) -> None:
        if normal:
            self.setStyleSheet("""
                QLineEdit {
                    background: #161b22;
                    color: #e6edf3;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-family: monospace;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border-color: #58a6ff;
                }
            """)
        else:
            self.setStyleSheet("""
                QLineEdit {
                    background: #1c2128;
                    color: #58a6ff;
                    border: 2px solid #58a6ff;
                    border-radius: 6px;
                    padding: 5px 9px;
                    font-family: monospace;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)

    def set_hotkey_value(self, hotkey: str) -> None:
        normalized = normalize_to_pynput(hotkey)
        self._raw_pynput = normalized
        self.setText(format_for_display(normalized))

    def get_hotkey_value(self) -> str:
        text = self.text().strip()
        if not text:
            return ""
        return normalize_to_pynput(text)

    def start_recording(self) -> None:
        self._is_recording = True
        self._update_style(normal=False)
        self.setPlaceholderText("请直接按下键盘组合键 (Esc 取消)...")
        self.clear()
        self.setFocus()

    def stop_recording(self) -> None:
        self._is_recording = False
        self._update_style(normal=True)
        self.setPlaceholderText("点击“录制”或手动输入 (如 Alt+D)")
        if self._raw_pynput:
            self.setText(format_for_display(self._raw_pynput))

    def focusOutEvent(self, event) -> None:
        if self._is_recording:
            self.stop_recording()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._is_recording:
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Escape:
            self.stop_recording()
            event.accept()
            return

        # 检查是否是纯修饰键
        if event.key() in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
        ):
            mods = []
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                mods.append("Ctrl")
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                mods.append("Alt")
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                mods.append("Shift")
            if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
                mods.append("Win")
            self.setText(" + ".join(mods) + " + ...")
            event.accept()
            return

        combo = qkey_to_pynput(event.modifiers(), event.key(), event.text())
        if combo and is_valid_pynput_hotkey(combo):
            self.set_hotkey_value(combo)
            self.stop_recording()
            self.clearFocus()
            event.accept()
        else:
            event.accept()


class HotkeyRowWidget(QFrame):
    """单条快捷键配置行（包含输入框、录制按钮、删除按钮）"""

    def __init__(
        self,
        hotkey_str: str,
        on_delete: Callable[[HotkeyRowWidget], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.on_delete = on_delete

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.edit = KeyRecorderEdit(hotkey_str, self)
        layout.addWidget(self.edit, stretch=1)

        self.record_btn = QPushButton("录制", self)
        self.record_btn.setToolTip("按下键盘按键录制快捷键")
        self.record_btn.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #30363d;
                color: #58a6ff;
                border-color: #58a6ff;
            }
        """)
        self.record_btn.clicked.connect(self.edit.start_recording)
        layout.addWidget(self.record_btn)

        self.del_btn = QPushButton("✕", self)
        self.del_btn.setToolTip("删除")
        self.del_btn.setFixedSize(28, 28)
        self.del_btn.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #b62324;
                color: #ffffff;
                border-color: #f85149;
            }
        """)
        self.del_btn.clicked.connect(lambda: self.on_delete(self))
        layout.addWidget(self.del_btn)

    def get_hotkey(self) -> str:
        return self.edit.get_hotkey_value()


class HotkeySettingsDialog(QDialog):
    """全局多快捷键配置对话框"""

    def __init__(
        self,
        selection_config: SelectionConfig,
        on_save: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.selection_config = selection_config
        self.on_save = on_save
        self.setWindowTitle("快捷键设置")
        self.resize(440, 360)
        self.setMinimumSize(380, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.rows: list[HotkeyRowWidget] = []
        self._init_ui()

    @property
    def input_hotkey(self):
        """兼容原有单快捷键属性访问与测试用例"""
        if self.rows:
            return self.rows[0].edit
        return None

    def _init_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #e6edf3;
            }
            QLabel {
                color: #e6edf3;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(10)

        # 快捷键列表滚动区域
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #30363d; border-radius: 8px; background: #0d1117; }")

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_container)
        main_layout.addWidget(scroll, stretch=1)

        # 添加已有快捷键
        initial_keys = self.selection_config.get_all_hotkeys()
        for k in initial_keys:
            self._add_row(k)

        # “+ 添加快捷键” 按钮
        add_bar = QHBoxLayout()
        self.add_btn = QPushButton("+ 添加快捷键", self)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #58a6ff;
                border: 1px dashed #388bfd;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: #1f242c;
                border-color: #58a6ff;
                color: #79c0ff;
            }
        """)
        self.add_btn.clicked.connect(lambda: self._add_row("", start_recording=True))
        add_bar.addWidget(self.add_btn)
        add_bar.addStretch()
        main_layout.addLayout(add_bar)

        # 常用预设推荐栏 (极简无废话)
        preset_bar = QHBoxLayout()
        preset_bar.setSpacing(6)
        preset_title = QLabel("常用预设:", self)
        preset_title.setStyleSheet("font-size: 11px; color: #8b949e;")
        preset_bar.addWidget(preset_title)

        presets = [
            ("Alt + D", "<alt>+d"),
            ("Ctrl + Alt + T", "<ctrl>+<alt>+t"),
            ("Alt + Q", "<alt>+q"),
            ("F2", "<f2>"),
        ]
        for title, keycode in presets:
            btn = QPushButton(title, self)
            btn.setStyleSheet("""
                QPushButton {
                    background: #161b22;
                    color: #c9d1d9;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #30363d;
                    color: #58a6ff;
                    border-color: #58a6ff;
                }
            """)
            btn.clicked.connect(lambda checked, k=keycode: self._quick_add_preset(k))
            preset_bar.addWidget(btn)
        preset_bar.addStretch()
        main_layout.addLayout(preset_bar)

        # 状态提示标签（默认空，不占冗余说明）
        self.status_lbl = QLabel("", self)
        self.status_lbl.setStyleSheet("font-size: 11px; color: #f85149;")
        main_layout.addWidget(self.status_lbl)

        # 底部操作栏
        btn_box = QHBoxLayout()

        reset_btn = QPushButton("恢复默认", self)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8b949e;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #f85149;
                border-color: #da3633;
            }
        """)
        reset_btn.clicked.connect(self._reset_to_default)
        btn_box.addWidget(reset_btn)

        btn_box.addStretch()

        cancel_btn = QPushButton("取消", self)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 5px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #30363d;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("保存", self)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f6feb;
                color: #ffffff;
                border: 1px solid #388bfd;
                border-radius: 6px;
                padding: 5px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #388bfd;
            }
        """)
        save_btn.clicked.connect(self._save_and_apply)
        btn_box.addWidget(save_btn)

        main_layout.addLayout(btn_box)

    def _add_row(self, hotkey_str: str, start_recording: bool = False) -> HotkeyRowWidget:
        row = HotkeyRowWidget(hotkey_str, on_delete=self._remove_row, parent=self.list_container)
        self.rows.append(row)
        self.list_layout.insertWidget(len(self.rows) - 1, row)
        row.show()
        if start_recording:
            row.edit.start_recording()
        return row

    def _remove_row(self, row: HotkeyRowWidget) -> None:
        if row in self.rows:
            self.rows.remove(row)
            self.list_layout.removeWidget(row)
            row.deleteLater()
            self._flash_status("已移除快捷键")

    def _quick_add_preset(self, preset_keycode: str) -> None:
        norm = normalize_to_pynput(preset_keycode)
        existing = [normalize_to_pynput(r.get_hotkey()) for r in self.rows if r.get_hotkey()]
        if norm in existing:
            self._flash_status(f"快捷键 {format_for_display(norm)} 已在列表中")
            return
        self._add_row(norm)
        self._flash_status(f"已添加快捷键：{format_for_display(norm)}")

    def _reset_to_default(self) -> None:
        for r in list(self.rows):
            self._remove_row(r)
        self._add_row("<alt>+d")
        self._flash_status("已重置为默认快捷键：Alt + D")

    def _flash_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def _save_and_apply(self) -> None:
        raw_keys = [r.get_hotkey() for r in self.rows if r.get_hotkey()]
        valid_keys: list[str] = []
        for k in raw_keys:
            norm = normalize_to_pynput(k)
            if not is_valid_pynput_hotkey(norm):
                self._flash_status(f"快捷键 '{k}' 格式无效，请检查")
                return
            if norm not in valid_keys:
                valid_keys.append(norm)

        if not valid_keys:
            self._flash_status("请至少保留一个有效快捷键")
            return

        self.selection_config.set_all_hotkeys(valid_keys)
        if self.on_save:
            self.on_save()
        self.accept()




class OriginalTextEdit(QPlainTextEdit):
    """支持手动编辑、复制粘贴、回车即时翻译与接口向下兼容的原文输入框"""
    return_pressed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("original_text")
        self.setPlaceholderText("输入或粘贴需要翻译的文本 (回车翻译，Shift+回车换行)...")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def text(self) -> str:
        """保持与 QLabel.text() 100% 接口兼容"""
        return self.toPlainText()

    def setText(self, text: str) -> None:
        """供系统注入文本（如划词或重译），静默更新且光标移至末尾"""
        self.blockSignals(True)
        self.setPlainText(text)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.blockSignals(False)

    def setWordWrap(self, wrap: bool) -> None:
        pass  # 兼容空实现

    def setTextInteractionFlags(self, flags) -> None:
        pass  # 兼容空实现

    def mousePressEvent(self, event) -> None:
        win = self.window()
        if win and hasattr(win, "_activate_window_for_input"):
            win._activate_window_for_input()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.window():
                self.window().hide()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.return_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)



class PopupBubble(QWidget):
    """防焦点窃取的高颜值多功能悬浮翻译气泡窗口"""

    # 异步触发信号（线程安全）
    show_translation_signal = Signal(object)
    show_loading_signal = Signal(str, int, int)
    dismiss_signal = Signal(int, int)
    closed = Signal()
    query_invalidated = Signal()

    def __init__(
        self,
        config: UIConfig,
        selection_config: Optional[SelectionConfig] = None,
        on_retranslate: Optional[Callable[[str], None]] = None,
        on_switch_provider: Optional[Callable[[str, str], None]] = None,
        on_save_config: Optional[Callable[[], None]] = None,
        on_clear_cache: Optional[Callable[[], None]] = None,
        on_update_selection_config: Optional[Callable[[], None]] = None,
        available_providers: Optional[list[str]] = None,
        default_provider: str = "microsoft",
        on_open_settings: Optional[Callable[[], None]] = None,
        default_source_lang: str = "auto",
        default_target_lang: str = "zh-CN",
        on_source_lang_change: Optional[Callable[[str], None]] = None,
        on_target_lang_change: Optional[Callable[[str], None]] = None,
        provider_configs: Optional[dict[str, ProviderConfig]] = None,
        on_configure_provider: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.selection_config = selection_config or SelectionConfig()
        self.on_retranslate = on_retranslate
        self.on_switch_provider = on_switch_provider
        self.on_save_config = on_save_config
        self.on_clear_cache = on_clear_cache
        self.on_update_selection_config = on_update_selection_config
        self.on_open_settings = on_open_settings
        self.available_providers = available_providers or ["microsoft", "deepseek", "openai", "zhipu", "custom"]
        self._current_provider = default_provider
        self.provider_configs = provider_configs or {}
        self.on_configure_provider = on_configure_provider
        self._source_lang = default_source_lang
        self._target_lang = default_target_lang
        self.on_source_lang_change = on_source_lang_change
        self.on_target_lang_change = on_target_lang_change
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

        # 核心窗口标志：Tool 属性常驻，无边框置顶，支持按需输入交互
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
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

        # 手动输入防抖翻译定时器 (600ms)
        self._input_debounce_timer = QTimer(self)
        self._input_debounce_timer.setSingleShot(True)
        self._input_debounce_timer.timeout.connect(self._on_manual_translate_requested)

        # 自动收起定时器
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self._on_auto_hide)

        # 模式状态：是否处于主动打字输入状态
        self._is_active_input_mode: bool = False

        self._init_ui()

        if sys.platform == "win32":
            self._ensure_no_activate_style()

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
        container_layout.setContentsMargins(10, 8, 10, 8)
        container_layout.setSpacing(6)

        # ==================== 1. 单行极简控制栏 (Single-Row Header) ====================
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(5)

        self.brand_badge = QLabel("言蹊", self)
        self.brand_badge.setObjectName("brand_badge")
        self.brand_badge.hide()

        # 左侧 1: Provider 切换胶囊 [DeepSeek]
        self.provider_btn = QPushButton(provider_label(self._current_provider), self)
        self.provider_btn.setObjectName("provider_btn")
        self.provider_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.provider_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.provider_btn.setToolTip("切换翻译引擎")
        self.provider_btn.clicked.connect(self._show_provider_menu)
        self.provider_label = self.provider_btn  # 保持属性兼容
        self.set_active_provider(self._current_provider)
        top_bar.addWidget(self.provider_btn)

        # 左侧 2: 紧凑语言胶囊 [自动 ⇄ 中 ▾]
        self.direction_btn = QPushButton(self)
        self.direction_btn.setObjectName("provider_btn")
        self.direction_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.direction_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.direction_btn.setToolTip("切换源语言或目标语言，重译当前原文")
        self.direction_btn.setAccessibleName("翻译方向")
        self.direction_btn.clicked.connect(self._show_language_menu)
        self.set_translation_direction(self._source_lang, self._target_lang)
        top_bar.addWidget(self.direction_btn)

        top_bar.addStretch()

        # 右侧 1: 取词模式胶囊 [伴随阅读 ▾]
        self.mode_btn = QPushButton(self)
        self.mode_btn.setObjectName("provider_btn")
        self.mode_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_btn.clicked.connect(self._show_selection_mode_menu)
        self._selection_listener_enabled = True
        self.refresh_selection_mode()
        top_bar.addWidget(self.mode_btn)

        # 右侧 2: 钉住/固定按钮 [📌]
        self.pin_btn = QPushButton("📌", self)
        self.pin_btn.setObjectName("pin_btn")
        self.pin_btn.setFixedSize(26, 26)
        self.pin_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setToolTip("固定位置")
        self.pin_btn.clicked.connect(self._toggle_pin)
        top_bar.addWidget(self.pin_btn)


        # 右侧 3: 更多/设置菜单按钮 [⚙]
        self.more_btn = QPushButton("⚙", self)
        self.more_btn.setObjectName("action_btn")
        self.more_btn.setFixedSize(26, 26)
        self.more_btn.setToolTip("设置与服务管理")
        self.more_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.clicked.connect(self._show_more_menu)
        top_bar.addWidget(self.more_btn)

        # 右侧 4: 关闭按钮 [✕]
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setObjectName("close_btn")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setToolTip("收起（程序仍在托盘运行）")
        self.close_btn.setAccessibleName("收起浮窗")
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

        # 原文编辑/预览区
        self.original_edit = OriginalTextEdit(self)
        self.original_label = self.original_edit  # 保持属性兼容
        self.original_edit.return_pressed.connect(self._on_manual_translate_requested)
        self.original_edit.textChanged.connect(self._on_original_text_changed)
        self.original_edit.installEventFilter(self)
        orig_layout.addWidget(self.original_edit, stretch=1)

        # 原文卡片底栏：清空、即时翻译、复制原文
        orig_bottom = QHBoxLayout()
        orig_bottom.setContentsMargins(0, 0, 0, 0)
        orig_bottom.setSpacing(6)
        self.orig_meta_label = QLabel("0 字符", self)
        self.orig_meta_label.setObjectName("meta_label")
        orig_bottom.addWidget(self.orig_meta_label)

        orig_bottom.addStretch()

        self.clear_orig_btn = QPushButton("清空", self)
        self.clear_orig_btn.setObjectName("subtle_btn")
        self.clear_orig_btn.setToolTip("清空输入内容")
        self.clear_orig_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_orig_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_orig_btn.clicked.connect(self._clear_input)
        self.clear_orig_btn.hide()
        orig_bottom.addWidget(self.clear_orig_btn)

        self.translate_btn = QPushButton("翻译", self)
        self.translate_btn.setObjectName("subtle_btn")
        self.translate_btn.setToolTip("立即翻译 (回车)")
        self.translate_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.translate_btn.clicked.connect(self._on_manual_translate_requested)
        self.translate_btn.hide()
        orig_bottom.addWidget(self.translate_btn)

        self.copy_orig_btn = QPushButton("复制", self)
        self.copy_orig_btn.setObjectName("subtle_btn")
        self.copy_orig_btn.setToolTip("复制原文")
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

        # 译文 Markdown 富文本展示（自适应伸展，支持选中、Ctrl+C 与右键菜单）
        self.text_browser = QTextBrowser(self)
        self.text_browser.setObjectName("trans_browser")
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.text_browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.text_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_browser.customContextMenuRequested.connect(self._show_text_browser_context_menu)
        trans_layout.addWidget(self.text_browser, stretch=1)

        # 译文卡片底栏：状态提示 + 复制译文按钮
        trans_bottom = QHBoxLayout()
        trans_bottom.setContentsMargins(0, 0, 0, 0)
        trans_bottom.setSpacing(8)

        self.latency_label = QLabel("", self)
        self.latency_label.setObjectName("meta_label")
        trans_bottom.addWidget(self.latency_label)

        self.status_msg = QLabel("", self)
        self.status_msg.setStyleSheet("font-size: 11px; font-weight: 500;")
        trans_bottom.addWidget(self.status_msg)

        trans_bottom.addStretch()

        self.copy_btn = QPushButton("复制", self)
        self.copy_btn.setObjectName("action_btn_primary")
        self.copy_btn.setToolTip("复制译文")
        self.copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_result)
        trans_bottom.addWidget(self.copy_btn)

        trans_layout.addLayout(trans_bottom)

        self.recovery_bar = QWidget(self)
        recovery_layout = QHBoxLayout(self.recovery_bar)
        recovery_layout.setContentsMargins(0, 0, 0, 0)
        self.retry_btn = QPushButton("重试", self.recovery_bar)
        self.error_settings_btn = QPushButton("打开设置", self.recovery_bar)
        for button in (self.retry_btn, self.error_settings_btn):
            button.setObjectName("subtle_btn")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            recovery_layout.addWidget(button)
        recovery_layout.addStretch()
        self.retry_btn.clicked.connect(self._on_manual_translate_requested)
        self.error_settings_btn.clicked.connect(self._open_current_provider_settings)
        trans_layout.addWidget(self.recovery_bar)
        self.recovery_bar.hide()
        self.copy_btn.setEnabled(False)

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
        self.hint_label = QLabel("", self)
        self.hint_label.hide()
        bottom_bar.addWidget(self.hint_label)

        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self)
        self.size_grip.setToolTip("调整大小")
        self.size_grip.setFixedSize(14, 14)
        self.size_grip.setCursor(Qt.CursorShape.SizeFDiagCursor)
        bottom_bar.addWidget(self.size_grip)

        container_layout.addLayout(bottom_bar)


        # 整体布局外边距（紧密贴合主容器，彻底杜绝黑色方框底色与边距伪影）
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.container)

        # 阴影特效属性（适配不同模式透明度）
        self.shadow_effect = QGraphicsDropShadowEffect(self.container)
        self.shadow_effect.setBlurRadius(16)
        self.shadow_effect.setOffset(0, 4)
        self.shadow_effect.setColor(QColor(0, 0, 0, 80))

        # 应用主题与透明度
        self.apply_theme(self._theme, self._opacity)

    def _ensure_no_activate_style(self) -> None:
        """Windows 下确保应用 WS_EX_NOACTIVATE 扩展样式，绝不与外部前台焦点竞争"""
        if sys.platform == "win32":
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                hwnd = int(self.winId())
                if hwnd:
                    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    if not (ex_style & WS_EX_NOACTIVATE):
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
            except Exception:
                pass

    def _activate_window_for_input(self) -> None:
        """当用户点击输入框或主动要求键盘打字时，临时启用激活状态"""
        self._is_active_input_mode = True
        if sys.platform == "win32":
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                hwnd = int(self.winId())
                if hwnd:
                    ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        self.activateWindow()
        self.original_edit.setFocus()

    def _deactivate_input_mode(self) -> None:
        """离开主动输入时恢复非激活悬浮模式"""
        self._is_active_input_mode = False
        self._ensure_no_activate_style()

    def nativeEvent(self, eventType, message):
        """Windows 消息泵拦截：处理 WM_MOUSEACTIVATE 消息，禁止点击时自动激活窗口打断前台应用"""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                import ctypes
                # WM_MOUSEACTIVATE = 0x0021, MA_NOACTIVATE = 3
                msg_addr = int(message)
                offset = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4
                msg_id = ctypes.c_uint.from_address(msg_addr + offset).value
                if msg_id == 0x0021:
                    if not getattr(self, "_is_active_input_mode", False):
                        return True, 3
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        effective = get_effective_theme(self._theme)
        if enable_blur_behind and effective == "glass":
            try:
                hwnd = int(self.winId())
                enable_blur_behind(hwnd, dark=True)
            except Exception:
                pass
        if not getattr(self, "_is_active_input_mode", False):
            self._ensure_no_activate_style()

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

        if hasattr(self, "shadow_effect") and self.shadow_effect:
            shadow_alpha = 40 if effective == "light" else 80
            self.shadow_effect.setColor(QColor(0, 0, 0, shadow_alpha))

        # Windows 原生亚克力与毛玻璃增强
        if enable_blur_behind and self.isVisible():
            try:
                hwnd = int(self.winId())
                if effective == "glass":
                    enable_blur_behind(hwnd, dark=True)
                elif disable_blur_behind:
                    disable_blur_behind(hwnd)
            except Exception:
                pass

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
            self.pin_btn.setText("📌")
            self.pin_btn.setToolTip("取消固定")
            pin_bg = "#e4e4e7" if effective == "light" else "#27272a"
            pin_color = "#18181b" if effective == "light" else "#f4f4f5"
            pin_border = "#d4d4d8" if effective == "light" else "#3f3f46"
            self.pin_btn.setStyleSheet(f"""
                QPushButton#pin_btn {{
                    background-color: {pin_bg};
                    color: {pin_color};
                    border: 1px solid {pin_border};
                    border-radius: 6px;
                    font-size: 12px;
                }}
            """)
        else:
            self.pin_btn.setText("📌")
            self.pin_btn.setToolTip("固定位置")
            hover_bg = "#f4f4f5" if effective == "light" else "#27272a"
            hover_border = "#e4e4e7" if effective == "light" else "#3f3f46"
            self.pin_btn.setStyleSheet(f"""
                QPushButton#pin_btn {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    font-size: 12px;
                    border-radius: 6px;
                }}
                QPushButton#pin_btn:hover {{
                    background-color: {hover_bg};
                    border-color: {hover_border};
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
            self._flash_status("已固定位置")
        else:
            self._fixed_pos = None
            self.config.fixed_x = None
            self.config.fixed_y = None
            self._flash_status("已取消固定")

        self._restart_auto_hide_timer()
        self._update_pin_ui()
        self._save_current_config()

    def _toggle_only_translation(self, checked: bool) -> None:
        """切换是否只显示译文卡片"""
        self._only_translation = checked
        self.config.only_translation = checked

        if self._only_translation:
            self.orig_card.hide()
            self._flash_status("已切换为只显示译文")
        else:
            self.orig_card.show()
            saved_sizes = getattr(self.config, "splitter_sizes", [90, 180])
            if saved_sizes and len(saved_sizes) == 2:
                self.splitter.setSizes(saved_sizes)
            self._flash_status("已恢复显示原文与译文")

        self._save_current_config()

    def refresh_selection_mode(self, listener_enabled: Optional[bool] = None) -> None:
        """同步模式标签；暂停状态独立于模式，不因切换模式而恢复取词。"""
        if listener_enabled is not None:
            self._selection_listener_enabled = listener_enabled
        mode = self.selection_config.get_mode()
        label = MODE_LABELS[mode]
        if self._selection_listener_enabled:
            self.mode_btn.setText(label)
            self.mode_btn.setToolTip(MODE_DESCRIPTIONS[mode])
        else:
            self.mode_btn.setText("取词已暂停")
            self.mode_btn.setToolTip(f"当前模式：{label}。请在托盘中恢复取词。")
        if hasattr(self, "auto_hide_timer"):
            if self.isVisible():
                self._restart_auto_hide_timer()
            else:
                self.auto_hide_timer.stop()

    def _show_selection_mode_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(get_effective_theme(self._theme)))
        add_mode_actions(menu, self.selection_config.get_mode(), self._set_selection_mode)
        menu.exec(self.mode_btn.mapToGlobal(QPoint(0, self.mode_btn.height() + 2)))
        menu.deleteLater()

    def _set_selection_mode(self, mode: SelectionMode) -> None:
        self.selection_config.set_mode(mode)
        self._save_current_config()
        if self.on_update_selection_config:
            self.on_update_selection_config()
        self.refresh_selection_mode()
        self._flash_status(f"已切换为{MODE_LABELS[self.selection_config.get_mode()]}")

    def _toggle_mouse_side_button(self, checked: bool) -> None:
        """切换鼠标侧键取词触发"""
        self.selection_config.enable_mouse_side_button = checked
        self._save_current_config()
        if self.on_update_selection_config:
            self.on_update_selection_config()
        status_text = "鼠标侧键触发已开启" if checked else "鼠标侧键触发已关闭"
        self._flash_status(status_text)

    def _show_hotkey_settings_dialog(self) -> None:
        """打开快捷键配置弹窗"""
        dlg = HotkeySettingsDialog(
            selection_config=self.selection_config,
            on_save=self._on_hotkey_dialog_saved,
            parent=self,
        )
        dlg.exec()

    def _on_hotkey_dialog_saved(self) -> None:
        self._save_current_config()
        if self.on_update_selection_config:
            self.on_update_selection_config()
        self._flash_status(f"快捷键已更新为: {self.selection_config.hotkey}")

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
        self._flash_status("已恢复默认尺寸与比例")

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
        def _clear() -> None:
            try:
                self.status_msg.setText("")
            except Exception:
                pass
        QTimer.singleShot(duration_ms, _clear)

    def _flash_orig_meta(self, msg: str, duration_ms: int = 1800) -> None:
        self.orig_meta_label.setText(msg)

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

    def _safe_copy_to_clipboard(self, text: str) -> None:
        if not text:
            return
        # 1. 优先使用 Qt 原生系统剪贴板通道（对 Wayland / X11 / Windows 提供最佳系统原生兼容）
        try:
            from PySide6.QtGui import QGuiApplication, QClipboard
            cb = QGuiApplication.clipboard()
            if cb:
                cb.setText(text, QClipboard.Mode.Clipboard)
                cb.setText(text, QClipboard.Mode.Selection)
        except Exception:
            pass

        # 2. 同时使用 pyperclip 兜底写入剪贴板
        try:
            pyperclip.copy(text)
        except Exception:
            pass

    def _flash_copy_success(self, btn: QPushButton, text: str = "已复制") -> None:
        """为复制按钮提供温润的即时微动效反馈"""
        if not btn:
            return
        orig_text = btn.text()
        btn.setText(text)
        QTimer.singleShot(1200, lambda: btn.setText(orig_text))

    def _copy_original(self) -> None:
        text = self.original_edit.toPlainText().strip() or self._last_requested_text or (
            self._current_result.original_text if self._current_result else ""
        )
        if text:
            self._safe_copy_to_clipboard(text)
            self._flash_status("已复制原文")
            self._flash_copy_success(self.copy_orig_btn, "已复制")

    def _copy_result(self) -> None:
        if self._current_result and self._current_result.is_success():
            self._safe_copy_to_clipboard(self._current_result.translated_text)
            self._flash_status("已复制译文")
            self._flash_copy_success(self.copy_btn, "已复制")

    def _open_current_provider_settings(self) -> None:
        if self.on_configure_provider:
            self.on_configure_provider(self._current_provider)
        elif self.on_open_settings:
            self.on_open_settings()

    def _on_original_text_changed(self) -> None:
        """用户在输入框手动修改或粘贴文本时的响应"""
        self.query_invalidated.emit()
        self._input_debounce_timer.stop()
        self._current_result = None
        self.copy_btn.setEnabled(False)
        self.recovery_bar.hide()
        text = self.original_edit.toPlainText().strip()
        has_text = bool(text)
        self.clear_orig_btn.setVisible(has_text)
        self.translate_btn.setVisible(has_text)
        self.orig_meta_label.setText(self._format_meta(text))

        if text:
            self.text_browser.clear()
            self.latency_label.setText("")
            self.status_msg.setText("原文已修改，待重新翻译")
            if self.config.auto_translate_input:
                self._input_debounce_timer.start(600)
        else:
            self._input_debounce_timer.stop()
            self.text_browser.clear()
            self.latency_label.setText("")
            self.status_msg.setText("")

    def mark_query_pending(self) -> None:
        """设置应用后标记待重译，保留当前原文，不自动发出新请求。"""
        self._on_original_text_changed()
        self._input_debounce_timer.stop()

    def _on_manual_translate_requested(self) -> None:
        """用户敲击回车或点击'翻译'按钮或输入防抖结束时触发翻译"""
        self._input_debounce_timer.stop()
        text = self.original_edit.toPlainText().strip()
        if not text:
            return
        self._last_requested_text = text
        if self.on_retranslate:
            self.on_retranslate(text)
        elif self.on_switch_provider:
            self.on_switch_provider(self._current_provider, text)

    def _clear_input(self) -> None:
        """一键清空输入框与结果"""
        self.query_invalidated.emit()
        self._input_debounce_timer.stop()
        self.original_edit.clear()
        self.text_browser.clear()
        self.status_msg.setText("")
        self.latency_label.setText("")
        self.orig_meta_label.setText("0 字符")
        self._last_requested_text = ""
        self._current_result = None
        self.copy_btn.setEnabled(False)
        self.recovery_bar.hide()
        self.clear_orig_btn.hide()
        self.translate_btn.hide()
        self.original_edit.setFocus()

    def open_for_input(self) -> None:
        """主动打开浮窗，聚焦于原文输入框，供用户手动键入或复制粘贴查词"""
        self.query_invalidated.emit()
        self._input_debounce_timer.stop()
        self.original_edit.clear()
        self.text_browser.clear()
        self.status_msg.setText("")
        self.latency_label.setText("")
        self.orig_meta_label.setText("0 字符")
        self._last_requested_text = ""
        self._current_result = None
        self.copy_btn.setEnabled(False)
        self.recovery_bar.hide()
        self.clear_orig_btn.hide()
        self.translate_btn.hide()

        if self._is_pinned and self._fixed_pos is not None:
            self.move(self._fixed_pos)
        elif self._is_pinned and getattr(self.config, "fixed_x", None) is not None:
            self._fixed_pos = QPoint(self.config.fixed_x, self.config.fixed_y)
            self.move(self._fixed_pos)
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                cx = geo.x() + (geo.width() - self.width()) // 2
                cy = geo.y() + (geo.height() - self.height()) // 2
                self.move(cx, cy)

        self._activate_window_for_input()
        self.show()
        self.raise_()
        self.activateWindow()
        self.original_edit.setFocus()

    def _show_more_menu(self) -> None:
        """弹出更多选项设置菜单 (集成无级透明度滑动条、主题、模式B、快捷键)"""
        effective = get_effective_theme(self._theme)
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(effective))

        # 1. 钉住/固定
        pin_text = "取消固定" if self._is_pinned else "固定位置"
        act_pin = menu.addAction(pin_text)
        act_pin.triggered.connect(self._toggle_pin)

        # 2. 只显示译文
        act_only_trans = menu.addAction("只显示译文")
        act_only_trans.setCheckable(True)
        act_only_trans.setChecked(self._only_translation)
        act_only_trans.triggered.connect(self._toggle_only_translation)

        menu.addSeparator()

        mode_menu = menu.addMenu("取词模式")
        add_mode_actions(mode_menu, self.selection_config.get_mode(), self._set_selection_mode)

        # 4. 鼠标侧键触发开关
        act_side = menu.addAction("鼠标侧键触发")
        act_side.setCheckable(True)
        act_side.setChecked(self.selection_config.enable_mouse_side_button)
        act_side.triggered.connect(self._toggle_mouse_side_button)

        # 5. 快捷键配置
        hk_label = self.selection_config.hotkey
        act_hotkey = menu.addAction(f"快捷键设置 ({hk_label})...")
        act_hotkey.triggered.connect(self._show_hotkey_settings_dialog)

        menu.addSeparator()

        # 6. 主题风格子菜单
        theme_menu = menu.addMenu("主题风格")
        theme_menu.setStyleSheet(get_theme_menu_style(effective))
        for code, name in AVAILABLE_THEMES:
            is_curr = (self._theme == code)
            mark = "✓ " if is_curr else "   "
            act = theme_menu.addAction(f"{mark}{name}")
            act.triggered.connect(lambda checked, t=code: self._handle_theme_change(t))

        # 7. 无级透明度百分比调节 (QSlider 40% ~ 100%)
        opacity_action = QWidgetAction(menu)
        op_widget = QWidget(menu)
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(12, 4, 12, 4)
        op_layout.setSpacing(8)

        op_title = QLabel("透明度:", op_widget)
        op_title.setStyleSheet("font-size: 11px; font-weight: 500;")

        op_slider = QSlider(Qt.Orientation.Horizontal, op_widget)
        op_slider.setRange(40, 100)
        curr_pct = int(round(self._opacity * 100))
        op_slider.setValue(curr_pct)
        op_slider.setFixedWidth(100)
        op_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #30363d;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #52525b;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #f4f4f5;
                border: 1px solid #71717a;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
            }
        """)

        op_val_label = QLabel(f"{curr_pct}%", op_widget)
        op_val_label.setFixedWidth(34)
        op_val_label.setStyleSheet("font-size: 11px; color: #a1a1aa; font-weight: bold;")

        def _on_slider_change(val: int):
            op_val_label.setText(f"{val}%")
            self.apply_theme(opacity=val / 100.0)

        op_slider.valueChanged.connect(_on_slider_change)

        op_layout.addWidget(op_title)
        op_layout.addWidget(op_slider)
        op_layout.addWidget(op_val_label)
        opacity_action.setDefaultWidget(op_widget)
        menu.addAction(opacity_action)

        menu.addSeparator()

        # 8. 设置
        if self.on_open_settings:
            act_settings = menu.addAction("设置")
            act_settings.triggered.connect(self.on_open_settings)

        # 9. 恢复默认尺寸
        act_reset = menu.addAction("恢复默认尺寸")
        act_reset.triggered.connect(self._reset_window_geometry)

        # 10. 清空本地缓存
        if self.on_clear_cache:
            act_cache = menu.addAction("清空缓存")
            act_cache.triggered.connect(self._handle_clear_cache)

        pos = self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 2))
        menu.exec(pos)
        menu.deleteLater()

    def _handle_theme_change(self, theme_code: str) -> None:
        self.apply_theme(theme_name=theme_code)
        name_map = dict(AVAILABLE_THEMES)
        self._flash_status(f"主题已切换为：{name_map.get(theme_code, theme_code)}")

    def _handle_clear_cache(self) -> None:
        if self.on_clear_cache:
            self.on_clear_cache()
            self._flash_status("本地缓存已清空")

    def _create_provider_menu(self) -> QMenu:
        effective = get_effective_theme(self._theme)
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(effective))

        add_provider_actions(menu, self.available_providers, self.provider_configs,
                             self._current_provider, self._handle_provider_switch)

        if self.on_open_settings:
            menu.addSeparator()
            act_manage = menu.addAction("管理服务与 API Key")
            act_manage.triggered.connect(self.on_open_settings)

        return menu

    def _show_provider_menu(self) -> None:
        menu = self._create_provider_menu()

        pos = self.provider_btn.mapToGlobal(QPoint(0, self.provider_btn.height() + 2))
        menu.exec(pos)
        menu.deleteLater()

    def _handle_provider_switch(self, provider_name: str) -> None:
        config = self.provider_configs.get(provider_name)
        if config and not is_configured(config):
            if self.on_configure_provider:
                self.on_configure_provider(provider_name)
            return
        if provider_name == self._current_provider:
            return
        if self.on_switch_provider:
            self.on_switch_provider(provider_name, self.current_query_text())
        self.set_active_provider(provider_name)

    def current_query_text(self) -> str:
        return self.original_edit.toPlainText().strip()

    def set_translation_direction(self, source: str, target: str) -> None:
        self._source_lang, self._target_lang = source, target
        compact_map = {
            "auto": "自动",
            "zh-CN": "中",
            "zh-TW": "繁中",
            "en": "英",
            "ja": "日",
            "ko": "韩",
            "fr": "法",
            "de": "德",
            "es": "西",
            "ru": "俄",
            "it": "意",
        }
        s_lbl = compact_map.get(source, language_label(source))
        t_lbl = compact_map.get(target, language_label(target))
        self.direction_btn.setText(f"{s_lbl} ⇄ {t_lbl}")
        self.direction_btn.setToolTip(f"翻译方向：{language_label(source)} → {language_label(target)}（点击切换）")

    def _create_language_menu(self) -> QMenu:
        effective = get_effective_theme(self._theme)
        menu = QMenu(self)
        menu.setStyleSheet(get_theme_menu_style(effective))
        source_menu = menu.addMenu("源语言")
        target_menu = menu.addMenu("目标语言")
        add_language_actions(source_menu, self._source_lang, self._handle_source_lang_change, source=True)
        add_language_actions(target_menu, self._target_lang, self._handle_target_lang_change)
        return menu

    def _show_language_menu(self) -> None:
        menu = self._create_language_menu()
        menu.exec(self.direction_btn.mapToGlobal(QPoint(0, self.direction_btn.height() + 2)))
        menu.deleteLater()

    def _handle_source_lang_change(self, code: str) -> None:
        if code == self._source_lang:
            return
        if self.on_source_lang_change:
            self.on_source_lang_change(code)
        self.set_translation_direction(code, self._target_lang)

    def _handle_target_lang_change(self, code: str) -> None:
        if code == self._target_lang:
            return
        if self.on_target_lang_change:
            self.on_target_lang_change(code)
        self.set_translation_direction(self._source_lang, code)

    def set_active_provider(self, provider_name: str) -> None:
        """更新当前生效的翻译引擎显示"""
        self._current_provider = provider_name
        if hasattr(self, "provider_btn"):
            self.provider_btn.setText(provider_label(provider_name))
            self.provider_btn.setToolTip(provider_menu_label(provider_name, self.provider_configs.get(provider_name)) + "；点击切换引擎")

    def display_loading(self, text: str, cursor_x: int, cursor_y: int) -> None:
        """显示加载状态并智能定位（未固定时避让光标，固定时坚守坐标）"""
        self._input_debounce_timer.stop()
        self.auto_hide_timer.stop()
        self._current_result = None
        self.copy_btn.setEnabled(False)
        self.recovery_bar.hide()
        self._last_requested_text = text
        self.set_active_provider(self._current_provider)
        self.latency_label.setText("正在翻译...")
        self.status_msg.setText("")

        self.original_label.setText(text)
        self.orig_meta_label.setText(self._format_meta(text))

        effective = get_effective_theme(self._theme)
        loading_color = "#57606a" if effective == "light" else "#8b949e"
        self.text_browser.setHtml(
            f"<span style='color: {loading_color}; font-style: italic;'>正在翻译...</span>"
        )


        if self._is_pinned and self._fixed_pos is not None:
            self.move(self._fixed_pos)
        elif self._is_pinned and getattr(self.config, "fixed_x", None) is not None:
            self._fixed_pos = QPoint(self.config.fixed_x, self.config.fixed_y)
            self.move(self._fixed_pos)
        elif self.isVisible():
            # 伴随阅读模式：若浮窗已在屏幕上，划选新词时保持当前位置就地刷新，避免频繁跳跃遮挡正文
            pass
        else:
            self.adjust_position(cursor_x, cursor_y)
            if self._is_pinned:
                # 初始固定但未保存坐标的边界场景
                self._fixed_pos = self.pos()
                self.config.fixed_x = self.pos().x()
                self.config.fixed_y = self.pos().y()
                self._save_current_config()

        has_text = bool(text.strip())
        self.clear_orig_btn.setVisible(has_text)
        self.translate_btn.setVisible(has_text)

        if not self.isVisible():
            self._deactivate_input_mode()
            self.show()
            if sys.platform == "win32":
                try:
                    import ctypes
                    # SW_SHOWNOACTIVATE = 4, 保证绝不窃取外部前台焦点或打断右键菜单
                    ctypes.windll.user32.ShowWindow(int(self.winId()), 4)
                except Exception:
                    pass

    def display_result(self, result: TranslationResult) -> None:
        """展示完成的翻译结果"""
        self._current_result = result
        self._current_provider = result.provider
        self._last_requested_text = result.original_text
        self.status_msg.clear()

        self.set_active_provider(result.provider)
        if result.from_cache:
            self.latency_label.setText("本地缓存")
        else:
            self.latency_label.setText(f"{result.latency_ms:.0f}ms")


        self.original_label.setText(result.original_text)
        self.orig_meta_label.setText(self._format_meta(result.original_text))

        has_text = bool(result.original_text.strip())
        self.clear_orig_btn.setVisible(has_text)
        self.translate_btn.setVisible(has_text)

        if not result.is_success():
            message = result.translated_text.removeprefix("[Error]").strip() or "翻译失败，请重试。"
            html_err = escape(message).replace("\n", "<br>")
            self.text_browser.setHtml(
                f"<span style='color: #f85149; font-weight: 500;'>{html_err}</span>"
            )
            self.copy_btn.setEnabled(False)
            self.error_settings_btn.setVisible(bool(self.on_configure_provider or self.on_open_settings))
            self.recovery_bar.show()
        else:
            self.text_browser.setMarkdown(result.translated_text)
            self.copy_btn.setEnabled(True)
            self.recovery_bar.hide()

        if self._is_pinned or self.selection_config.get_mode() == SelectionMode.COMPANION:
            if self._is_pinned and self._fixed_pos is not None:
                self.move(self._fixed_pos)
            self.auto_hide_timer.stop()
        else:
            self._restart_auto_hide_timer()

        if not self.isVisible():
            self._deactivate_input_mode()
            self.show()
            if sys.platform == "win32":
                try:
                    import ctypes
                    # SW_SHOWNOACTIVATE = 4, 保证绝不窃取外部前台焦点或打断右键菜单
                    ctypes.windll.user32.ShowWindow(int(self.winId()), 4)
                except Exception:
                    pass

    def dismiss_if_outside(self, cursor_x: int = 0, cursor_y: int = 0) -> None:
        """如果浮窗正处于显示状态且未钉住，当点击落在浮窗几何区域外部时平滑收起"""
        if not self.isVisible() or self._is_pinned:
            return
        # 伴随阅读模式下，用户需要在文档/浏览器中频繁划选，点击外部绝不自动收起，由 Esc 或 ✕ 主动关闭
        if self.selection_config.get_mode() == SelectionMode.COMPANION:
            return

        mouse_pos = QCursor.pos()
        if not self.frameGeometry().contains(mouse_pos):
            self.hide()

    def hideEvent(self, event) -> None:
        self._input_debounce_timer.stop()
        self.auto_hide_timer.stop()
        self._deactivate_input_mode()
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
        """拦截主卡片外壳事件，支持贴边/贴角的顺滑拉伸缩放与文本编辑聚焦激活"""
        if hasattr(self, "original_edit") and watched == self.original_edit:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._activate_window_for_input()

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
                        self._flash_status("固定位置与尺寸已更新")
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
                    self._flash_status("固定位置与尺寸已更新")
                self._save_timer.start(500)
                event.accept()
                return

            self._drag_pos = QPoint()
            if self._is_pinned:
                self._fixed_pos = self.pos()
                self.config.fixed_x = self.x()
                self.config.fixed_y = self.y()
                self._save_current_config()
                self._flash_status("固定位置已更新")
            event.accept()

    def enterEvent(self, event) -> None:
        """鼠标悬停浮窗上时暂停自动收起"""
        self.auto_hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """鼠标移出浮窗后若未钉住则重启自动收起"""
        self._restart_auto_hide_timer()
        self.unsetCursor()
        super().leaveEvent(event)

    def _restart_auto_hide_timer(self) -> None:
        self.auto_hide_timer.stop()
        if (
            not self._is_pinned
            and self.selection_config.get_mode() != SelectionMode.COMPANION
            and self.config.auto_hide_seconds > 0
        ):
            self.auto_hide_timer.start(self.config.auto_hide_seconds * 1000)

    def _show_text_browser_context_menu(self, pos: QPoint) -> None:
        """为译文展示区提供高颜值定制右键菜单"""
        menu = QMenu(self)
        effective = get_effective_theme(self._theme)
        menu.setStyleSheet(get_theme_menu_style(effective))

        cursor = self.text_browser.textCursor()
        if cursor.hasSelection():
            act_copy_sel = menu.addAction("复制选中内容 (Ctrl+C)")
            act_copy_sel.triggered.connect(self.text_browser.copy)

        act_copy_all = menu.addAction("复制全部译文")
        act_copy_all.triggered.connect(self._copy_result)

        menu.addSeparator()
        act_select_all = menu.addAction("全选 (Ctrl+A)")
        act_select_all.triggered.connect(self.text_browser.selectAll)

        menu.exec(self.text_browser.mapToGlobal(pos))
        menu.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return

        # 悬浮窗内任意位置按 Ctrl+C 智能复制
        if (
            event.key() == Qt.Key.Key_C
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            if self.original_edit.hasFocus() and self.original_edit.textCursor().hasSelection():
                self.original_edit.copy()
            elif self.text_browser.textCursor().hasSelection():
                self.text_browser.copy()
            else:
                self._copy_result()
            event.accept()
            return

        super().keyPressEvent(event)
