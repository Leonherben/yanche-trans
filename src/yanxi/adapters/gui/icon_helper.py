"""言蹊翻译 (YanXi Trans) 应用图标加载与管理助手

提供跨平台、自适应寻找多尺寸高清图标，并在缺少外部资源时自动使用纯代码优雅兜底。
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap


def _ensure_gui_app() -> None:
    """确保在渲染或读取 QPixmap 前存在 QGuiApplication 实例"""
    if QGuiApplication.instance() is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])


def find_icon_path() -> Optional[Path]:
    """探测应用图标路径，适配打包环境、源码环境与系统安装环境"""
    candidates = []

    # 1. PyInstaller 打包目录
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "icon.png")

    # 2. 源码仓库 assets 目录（向上寻根直至包含 pyproject.toml）
    curr = Path(__file__).resolve()
    for parent in curr.parents:
        cand = parent / "assets" / "icon.png"
        if cand.is_file() and (parent / "pyproject.toml").is_file():
            candidates.append(cand)
            break

    # 3. Linux 用户安装路径
    user_opt = Path.home() / ".local" / "opt" / "yanxi" / "assets" / "icon.png"
    user_hicolor = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "yanxi.png"
    candidates.extend([user_opt, user_hicolor])

    # 4. 全局系统安装路径
    candidates.append(Path("/usr/share/icons/hicolor/256x256/apps/yanxi.png"))

    for p in candidates:
        if p.is_file():
            return p
    return None


def create_fallback_icon_pixmap(size: int = 64) -> QPixmap:
    """程序化矢量渲染备用图标，确保在缺失外部资产时依然有一致的视觉体验"""
    _ensure_gui_app()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 绘制优雅的渐变圆角底板
    padding = size * 0.05
    rect_size = size - 2 * padding
    radius = rect_size * 0.22

    painter.setBrush(QColor("#2563eb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(padding, padding, rect_size, rect_size, radius, radius)

    # 绘制文字
    painter.setPen(QColor("#ffffff"))
    font_size = int(size * 0.5)
    font = QFont("Noto Sans CJK SC", font_size, QFont.Weight.Bold)
    if not font.exactMatch():
        font = QFont("Sans-Serif", font_size, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "言")
    painter.end()

    return pixmap


def get_app_icon() -> QIcon:
    """获取言蹊翻译标准 QIcon"""
    icon_path = find_icon_path()
    if icon_path:
        _ensure_gui_app()
        pix = QPixmap(str(icon_path))
        if not pix.isNull():
            return QIcon(pix)
    return QIcon(create_fallback_icon_pixmap(128))


def get_tray_icon() -> QIcon:
    """获取适配托盘栏的高清抗锯齿图标"""
    return get_app_icon()
