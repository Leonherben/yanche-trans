"""言蹊翻译 (YanXi Trans) 应用图标加载与管理助手

提供跨平台、自适应寻找多尺寸高清图标，并在缺少外部资源时自动使用纯代码优雅兜底。
全面适配 Windows 独立打包 (onedir/onefile)、Linux 桌面及源码运行环境。
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


def find_icon_paths() -> list[Path]:
    """探测所有可用的应用图标路径，适配打包环境、源码环境与系统安装环境"""
    candidates: list[Path] = []

    # 1. Windows / Linux 独立发布包环境 (sys.frozen)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir / "assets" / "icon.ico",
            exe_dir / "assets" / "icon.png",
            exe_dir / "_internal" / "assets" / "icon.ico",
            exe_dir / "_internal" / "assets" / "icon.png",
        ])
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            candidates.extend([
                meipass / "assets" / "icon.ico",
                meipass / "assets" / "icon.png",
            ])

    # 2. 源码仓库 assets 目录（向上寻根直至包含 pyproject.toml）
    curr = Path(__file__).resolve()
    for parent in curr.parents:
        if (parent / "pyproject.toml").is_file():
            candidates.extend([
                parent / "assets" / "icon.ico",
                parent / "assets" / "icon.png",
            ])
            break

    # 3. Windows 用户应用配置目录
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.extend([
                Path(appdata) / "yanxi" / "assets" / "icon.ico",
                Path(appdata) / "yanxi" / "assets" / "icon.png",
            ])

    # 4. Linux 用户与系统图标路径
    if sys.platform.startswith("linux"):
        user_opt = Path.home() / ".local" / "opt" / "yanxi" / "assets"
        candidates.extend([
            user_opt / "icon.png",
            user_opt / "icon.ico",
            Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "yanxi.png",
            Path("/usr/share/icons/hicolor/256x256/apps/yanxi.png"),
        ])

    found: list[Path] = []
    for p in candidates:
        if p.is_file() and p not in found:
            found.append(p)
    return found


def find_icon_path() -> Optional[Path]:
    """返回首选的应用图标路径（向后兼容）"""
    paths = find_icon_paths()
    if not paths:
        return None
    # Windows 优先使用 .ico，非 Windows 优先使用 .png
    if sys.platform == "win32":
        ico_paths = [p for p in paths if p.suffix.lower() == ".ico"]
        if ico_paths:
            return ico_paths[0]
    else:
        png_paths = [p for p in paths if p.suffix.lower() == ".png"]
        if png_paths:
            return png_paths[0]
    return paths[0]


def create_fallback_icon_pixmap(size: int = 64) -> QPixmap:
    """程序化矢量渲染备用图标，确保在缺失外部资产时依然有一致的视觉体验"""
    _ensure_gui_app()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    padding = size * 0.05
    rect_size = size - 2 * padding
    radius = rect_size * 0.22

    painter.setBrush(QColor("#2563eb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(padding, padding, rect_size, rect_size, radius, radius)

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
    """获取言蹊翻译标准多尺寸 QIcon，自动整合 ICO 与 PNG 资产"""
    paths = find_icon_paths()
    if paths:
        _ensure_gui_app()
        icon = QIcon()
        # Windows 优先添加 ICO（内含多尺寸），再补充 PNG
        if sys.platform == "win32":
            sorted_paths = sorted(paths, key=lambda p: 0 if p.suffix.lower() == ".ico" else 1)
        else:
            sorted_paths = sorted(paths, key=lambda p: 0 if p.suffix.lower() == ".png" else 1)

        for p in sorted_paths:
            icon.addFile(str(p))

        if not icon.isNull():
            return icon

    return QIcon(create_fallback_icon_pixmap(128))


def get_tray_icon() -> QIcon:
    """获取适配托盘栏的高清抗锯齿图标"""
    return get_app_icon()


def configure_windows_app_id(app_id: str = "yanxi.trans.desktop.app") -> None:
    """在 Windows 平台上配置当前进程的 Explicit AppUserModelID，以确保任务栏正确展示应用图标而非 Python 默认图标"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception as e:
            print(f"⚠️ 设置 Windows AppUserModelID 失败: {e}")

