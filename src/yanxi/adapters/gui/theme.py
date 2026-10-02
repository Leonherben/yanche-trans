"""主题管理引擎 (Theme Engine)

支持 Dark (深色)、Light (浅色)、Glass (透光玻璃) 及 Auto (跟随系统)。
实时感知操作系统明暗偏好，提供高品质 QSS 样式表与动态透明度调节。
"""

from __future__ import annotations
import subprocess
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

AVAILABLE_THEMES = [
    ("auto", "跟随系统"),
    ("dark", "深色模式 (Dark)"),
    ("light", "浅色模式 (Light)"),
    ("glass", "透明玻璃 (Glass)"),
]

AVAILABLE_OPACITIES = [
    (1.0, "100% (不透明)"),
    (0.95, "95% (推荐)"),
    (0.85, "85%"),
    (0.75, "75%"),
    (0.60, "60% (通透)"),
]


def detect_system_theme() -> str:
    """探测操作系统当前是深色还是浅色模式"""
    # 1. 优先使用 Qt 6.5+ 原生平台样式探测
    app = QGuiApplication.instance()
    if app:
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
            elif scheme == Qt.ColorScheme.Light:
                return "light"
        except Exception:
            pass

    # 2. Linux Mint / GNOME / Ubuntu 原生 gsettings 探测
    try:
        res = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        val = res.stdout.strip().strip("'\"")
        if "dark" in val.lower():
            return "dark"
        elif "light" in val.lower():
            return "light"
    except Exception:
        pass

    # 兜底为深色
    return "dark"


def get_effective_theme(theme_name: str) -> str:
    """根据配置的模式解析出最终生效的主题 ('dark' | 'light' | 'glass')"""
    if theme_name == "auto":
        return detect_system_theme()
    if theme_name in ("dark", "light", "glass"):
        return theme_name
    return "dark"


import sys


def get_system_font_family() -> str:
    """获取与当前操作系统深度契合的标准 UI 字体族"""
    if sys.platform == "win32":
        return '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif'
    elif sys.platform == "darwin":
        return '-apple-system, "PingFang SC", "Helvetica Neue", "Hiragino Sans GB", sans-serif'
    else:
        return '"Noto Sans CJK SC", "WenQuanYi Micro Hei", "PingFang SC", sans-serif'


def _get_font_stylesheet_prefix() -> str:
    font = get_system_font_family()
    return f"""
    * {{
        font-family: {font};
    }}
    QWidget {{
        font-family: {font};
    }}
    """


def get_theme_stylesheet(effective_theme: str) -> str:
    """获取指定主题的高保真 QSS 样式表（自动注入平台最佳字体）"""
    prefix = _get_font_stylesheet_prefix()
    if effective_theme == "light":
        return prefix + _LIGHT_STYLESHEET
    elif effective_theme == "glass":
        return prefix + _GLASS_STYLESHEET
    else:
        return prefix + _DARK_STYLESHEET


def get_theme_menu_style(effective_theme: str) -> str:
    """获取与当前主题匹配的右键/弹出菜单样式（自动注入平台最佳字体）"""
    font = get_system_font_family()
    if effective_theme == "light":
        return f"""
            QMenu {{
                background-color: #ffffff;
                color: #18181b;
                border: 1px solid #e4e4e7;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 6px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: #f4f4f5;
                color: #09090b;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #e4e4e7;
                margin: 4px 6px;
            }}
        """
    elif effective_theme == "glass":
        return f"""
            QMenu {{
                background-color: rgba(24, 24, 27, 0.92);
                color: #f4f4f5;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 6px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(255, 255, 255, 0.12);
                margin: 4px 6px;
            }}
        """
    else:  # dark
        return f"""
            QMenu {{
                background-color: #18181b;
                color: #f4f4f5;
                border: 1px solid #27272a;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 6px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: #27272a;
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #27272a;
                margin: 4px 6px;
            }}
        """


_DARK_STYLESHEET = """
    QFrame#main_container {
        background-color: #0d1117;
        border: 1px solid #27272a;
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #d4d4d8;
        font-weight: 600;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #e4e4e7;
        font-weight: 500;
        font-size: 11px;
        background-color: #18181b;
        border: 1px solid #27272a;
        border-radius: 6px;
        padding: 2px 8px;
    }
    QPushButton#provider_btn:hover {
        background-color: #27272a;
        border-color: #3f3f46;
        color: #ffffff;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #a1a1aa;
        font-size: 13px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#action_btn:hover {
        background-color: #27272a;
        border-color: #3f3f46;
        color: #ffffff;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #a1a1aa;
        font-size: 12px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#close_btn:hover {
        background-color: #27272a;
        border-color: #3f3f46;
        color: #ffffff;
    }
    QFrame#card_frame {
        background-color: #161b22;
        border: 1px solid #27272a;
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #a1a1aa;
        font-size: 12px;
        line-height: 1.4;
        background: transparent;
        border: none;
    }
    QPlainTextEdit#original_text:focus {
        border: none;
        outline: none;
    }
    QPushButton#subtle_btn {
        background: transparent;
        border: 1px solid transparent;
        color: #71717a;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 4px;
    }
    QPushButton#subtle_btn:hover {
        background: #27272a;
        border-color: #3f3f46;
        color: #e4e4e7;
    }
    QLabel#meta_label {
        color: #71717a;
        font-size: 11px;
    }
    QTextBrowser#trans_browser {
        background: transparent;
        border: none;
        color: #f4f4f5;
        font-size: 13px;
        selection-background-color: #3f3f46;
        selection-color: #ffffff;
    }
    QPushButton#action_btn_primary {
        background-color: #27272a;
        color: #e4e4e7;
        border: 1px solid #3f3f46;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 500;
    }
    QPushButton#action_btn_primary:hover {
        background-color: #3f3f46;
        border-color: #52525b;
        color: #ffffff;
    }
    QSplitter#card_splitter {
        background: transparent;
    }
    QSplitter#card_splitter::handle:vertical {
        height: 6px;
        background-color: transparent;
        margin: 1px 0px;
    }
    QSplitter#card_splitter::handle:vertical:hover {
        background-color: #3f3f46;
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: #52525b;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #27272a;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #52525b;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QSizeGrip {
        background: transparent;
        width: 14px;
        height: 14px;
    }
"""

_LIGHT_STYLESHEET = """
    QFrame#main_container {
        background-color: #ffffff;
        border: 1px solid #e4e4e7;
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #27272a;
        font-weight: 600;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #27272a;
        font-weight: 500;
        font-size: 11px;
        background-color: #f4f4f5;
        border: 1px solid #e4e4e7;
        border-radius: 6px;
        padding: 2px 8px;
    }
    QPushButton#provider_btn:hover {
        background-color: #e4e4e7;
        border-color: #d4d4d8;
        color: #09090b;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #71717a;
        font-size: 13px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#action_btn:hover {
        background-color: #f4f4f5;
        border-color: #e4e4e7;
        color: #18181b;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #71717a;
        font-size: 12px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#close_btn:hover {
        background-color: #f4f4f5;
        border-color: #e4e4e7;
        color: #18181b;
    }
    QFrame#card_frame {
        background-color: #f6f8fa;
        border: 1px solid #e4e4e7;
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #52525b;
        font-size: 12px;
        line-height: 1.4;
        background: transparent;
        border: none;
    }
    QPlainTextEdit#original_text:focus {
        border: none;
        outline: none;
    }
    QPushButton#subtle_btn {
        background: transparent;
        border: 1px solid transparent;
        color: #71717a;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 4px;
    }
    QPushButton#subtle_btn:hover {
        background: #e4e4e7;
        border-color: #d4d4d8;
        color: #18181b;
    }
    QLabel#meta_label {
        color: #71717a;
        font-size: 11px;
    }
    QTextBrowser#trans_browser {
        background: transparent;
        border: none;
        color: #18181b;
        font-size: 13px;
        selection-background-color: #d4d4d8;
        selection-color: #09090b;
    }
    QPushButton#action_btn_primary {
        background-color: #f4f4f5;
        color: #18181b;
        border: 1px solid #e4e4e7;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 500;
    }
    QPushButton#action_btn_primary:hover {
        background-color: #e4e4e7;
        border-color: #d4d4d8;
        color: #09090b;
    }
    QSplitter#card_splitter {
        background: transparent;
    }
    QSplitter#card_splitter::handle:vertical {
        height: 6px;
        background-color: transparent;
        margin: 1px 0px;
    }
    QSplitter#card_splitter::handle:vertical:hover {
        background-color: #d4d4d8;
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: #a1a1aa;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #e4e4e7;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #a1a1aa;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QSizeGrip {
        background: transparent;
        width: 14px;
        height: 14px;
    }
"""

_GLASS_STYLESHEET = """
    QFrame#main_container {
        background-color: rgba(18, 18, 20, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #f4f4f5;
        font-weight: 600;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #f4f4f5;
        font-weight: 500;
        font-size: 11px;
        background-color: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 6px;
        padding: 2px 8px;
    }
    QPushButton#provider_btn:hover {
        background-color: rgba(255, 255, 255, 0.15);
        border-color: rgba(255, 255, 255, 0.25);
        color: #ffffff;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #d4d4d8;
        font-size: 13px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#action_btn:hover {
        background-color: rgba(255, 255, 255, 0.15);
        border-color: rgba(255, 255, 255, 0.25);
        color: #ffffff;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: 1px solid transparent;
        color: #d4d4d8;
        font-size: 12px;
        font-weight: bold;
        border-radius: 6px;
    }
    QPushButton#close_btn:hover {
        background-color: rgba(255, 255, 255, 0.15);
        border-color: rgba(255, 255, 255, 0.25);
        color: #ffffff;
    }
    QFrame#card_frame {
        background-color: rgba(25, 25, 28, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #d4d4d8;
        font-size: 12px;
        line-height: 1.4;
        background: transparent;
        border: none;
    }
    QPlainTextEdit#original_text:focus {
        border: none;
        outline: none;
    }
    QPushButton#subtle_btn {
        background: transparent;
        border: 1px solid transparent;
        color: #a1a1aa;
        font-size: 11px;
        padding: 2px 6px;
        border-radius: 4px;
    }
    QPushButton#subtle_btn:hover {
        background: rgba(255, 255, 255, 0.12);
        border-color: rgba(255, 255, 255, 0.20);
        color: #ffffff;
    }
    QLabel#meta_label {
        color: rgba(255, 255, 255, 0.55);
        font-size: 11px;
    }
    QTextBrowser#trans_browser {
        background: transparent;
        border: none;
        color: #ffffff;
        font-size: 13px;
        selection-background-color: rgba(255, 255, 255, 0.25);
        selection-color: #ffffff;
    }
    QPushButton#action_btn_primary {
        background-color: rgba(255, 255, 255, 0.10);
        color: #f4f4f5;
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 500;
    }
    QPushButton#action_btn_primary:hover {
        background-color: rgba(255, 255, 255, 0.18);
        border-color: rgba(255, 255, 255, 0.28);
        color: #ffffff;
    }
    QSplitter#card_splitter {
        background: transparent;
    }
    QSplitter#card_splitter::handle:vertical {
        height: 6px;
        background-color: transparent;
        margin: 1px 0px;
    }
    QSplitter#card_splitter::handle:vertical:hover {
        background-color: rgba(255, 255, 255, 0.25);
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: rgba(255, 255, 255, 0.40);
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.18);
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(255, 255, 255, 0.35);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QSizeGrip {
        background: transparent;
        width: 14px;
        height: 14px;
    }
"""
