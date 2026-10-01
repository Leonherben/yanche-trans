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
                color: #1f2328;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: #0969da;
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #d0d7de;
                margin: 4px 6px;
            }}
        """
    elif effective_theme == "glass":
        return f"""
            QMenu {{
                background-color: rgba(22, 27, 34, 0.90);
                color: #f0f6fc;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: #1f6feb;
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: rgba(255, 255, 255, 0.15);
                margin: 4px 6px;
            }}
        """
    else:  # dark
        return f"""
            QMenu {{
                background-color: #161b22;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 4px;
                font-size: 12px;
                font-family: {font};
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-family: {font};
            }}
            QMenu::item:selected {{
                background-color: #1f6feb;
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #30363d;
                margin: 4px 6px;
            }}
        """


_DARK_STYLESHEET = """
    QFrame#main_container {
        background-color: #0d1117;
        border: 1px solid #30363d;
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #58a6ff;
        font-weight: bold;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #c9d1d9;
        font-weight: 500;
        font-size: 11px;
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 11px;
        padding: 2px 10px;
    }
    QPushButton#provider_btn:hover {
        background-color: #21262d;
        border-color: #58a6ff;
        color: #58a6ff;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: none;
        color: #8b949e;
        font-size: 13px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#action_btn:hover {
        background-color: #21262d;
        color: #c9d1d9;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: none;
        color: #8b949e;
        font-size: 12px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#close_btn:hover {
        background-color: rgba(248, 81, 73, 0.2);
        color: #f85149;
    }
    QFrame#card_frame {
        background-color: #161b22;
        border: 1px solid #21262d;
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #8b949e;
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
        border: none;
        color: #8b949e;
        font-size: 10px;
        padding: 1px 4px;
    }
    QPushButton#subtle_btn:hover {
        color: #58a6ff;
    }
    QLabel#meta_label {
        color: #8b949e;
        font-size: 11px;
    }
    QTextBrowser#trans_browser {
        background: transparent;
        border: none;
        color: #e6edf3;
        font-size: 13px;
        selection-background-color: #1f6feb;
        selection-color: #ffffff;
    }
    QPushButton#action_btn_primary {
        background-color: #21262d;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
    }
    QPushButton#action_btn_primary:hover {
        background-color: #30363d;
        color: #58a6ff;
        border-color: #58a6ff;
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
        background-color: #388bfd;
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: #1f6feb;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #30363d;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #58a6ff;
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
        border: 1px solid #d0d7de;
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #0969da;
        font-weight: bold;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #1f2328;
        font-weight: 500;
        font-size: 11px;
        background-color: #f6f8fa;
        border: 1px solid #d0d7de;
        border-radius: 11px;
        padding: 2px 10px;
    }
    QPushButton#provider_btn:hover {
        background-color: #eaeef2;
        border-color: #0969da;
        color: #0969da;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: none;
        color: #656d76;
        font-size: 13px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#action_btn:hover {
        background-color: #f3f4f6;
        color: #1f2328;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: none;
        color: #656d76;
        font-size: 12px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#close_btn:hover {
        background-color: rgba(207, 34, 46, 0.15);
        color: #cf222e;
    }
    QFrame#card_frame {
        background-color: #f6f8fa;
        border: 1px solid #e1e4e8;
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #57606a;
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
        border: none;
        color: #57606a;
        font-size: 10px;
        padding: 1px 4px;
    }
    QPushButton#subtle_btn:hover {
        color: #0969da;
    }
    QLabel#meta_label {
        color: #57606a;
        font-size: 11px;
    }
    QTextBrowser#trans_browser {
        background: transparent;
        border: none;
        color: #1f2328;
        font-size: 13px;
        selection-background-color: #0969da;
        selection-color: #ffffff;
    }
    QPushButton#action_btn_primary {
        background-color: #ffffff;
        color: #1f2328;
        border: 1px solid #d0d7de;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
    }
    QPushButton#action_btn_primary:hover {
        background-color: #f3f4f6;
        color: #0969da;
        border-color: #0969da;
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
        background-color: #0969da;
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: #0550ae;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #d0d7de;
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #0969da;
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
        background-color: rgba(13, 17, 23, 0.78);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 10px;
    }
    QLabel#brand_badge {
        color: #58a6ff;
        font-weight: bold;
        font-size: 12px;
        padding: 1px 4px;
    }
    QPushButton#provider_btn {
        color: #f0f6fc;
        font-weight: 500;
        font-size: 11px;
        background-color: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 11px;
        padding: 2px 10px;
    }
    QPushButton#provider_btn:hover {
        background-color: rgba(255, 255, 255, 0.16);
        border-color: #58a6ff;
        color: #58a6ff;
    }
    QPushButton#action_btn {
        background-color: transparent;
        border: none;
        color: #c9d1d9;
        font-size: 13px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#action_btn:hover {
        background-color: rgba(255, 255, 255, 0.12);
        color: #ffffff;
    }
    QPushButton#close_btn {
        background-color: transparent;
        border: none;
        color: #c9d1d9;
        font-size: 12px;
        font-weight: bold;
        border-radius: 4px;
    }
    QPushButton#close_btn:hover {
        background-color: rgba(248, 81, 73, 0.3);
        color: #ff7b72;
    }
    QFrame#card_frame {
        background-color: rgba(22, 27, 34, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
    }
    QLabel#original_text, QPlainTextEdit#original_text {
        color: #c9d1d9;
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
        border: none;
        color: #8b949e;
        font-size: 10px;
        padding: 1px 4px;
    }
    QPushButton#subtle_btn:hover {
        color: #58a6ff;
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
        selection-background-color: #1f6feb;
        selection-color: #ffffff;
    }
    QPushButton#action_btn_primary {
        background-color: rgba(255, 255, 255, 0.10);
        color: #f0f6fc;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
    }
    QPushButton#action_btn_primary:hover {
        background-color: rgba(255, 255, 255, 0.20);
        color: #58a6ff;
        border-color: #58a6ff;
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
        background-color: #58a6ff;
        border-radius: 2px;
    }
    QSplitter#card_splitter::handle:vertical:pressed {
        background-color: #1f6feb;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 6px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.2);
        min-height: 20px;
        border-radius: 3px;
    }
    QScrollBar::handle:vertical:hover {
        background: #58a6ff;
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
