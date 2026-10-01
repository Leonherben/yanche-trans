#!/usr/bin/env python3
"""言蹊翻译 (YanXi Trans) 应用图标生成脚本

使用 PySide6 QPainter 矢量渲染高分辨率图标，并生成多尺寸 Windows ICO 与 Linux PNG 图标。
"""

import os
import struct
import sys
from pathlib import Path

# 确保无头渲染环境
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QRect, QPointF, QBuffer, QIODevice
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPixmap,
)


def create_base_icon_pixmap(size: int = 512) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # 1. 绘制渐变圆角底板 (现代毛玻璃/极简雅蓝质感)
    padding = size * 0.04
    rect_size = size - 2 * padding
    radius = rect_size * 0.22

    gradient = QLinearGradient(QPointF(padding, padding), QPointF(size - padding, size - padding))
    gradient.setColorAt(0.0, QColor("#3b82f6"))  # 亮蓝
    gradient.setColorAt(1.0, QColor("#1d4ed8"))  # 深蓝
    painter.setBrush(gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(padding, padding, rect_size, rect_size, radius, radius)

    # 2. 绘制微妙的内发光/边框高光
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QColor(255, 255, 255, 60))
    painter.drawRoundedRect(padding + 1, padding + 1, rect_size - 2, rect_size - 2, radius - 1, radius - 1)

    # 3. 绘制核心标志汉字 "言"
    painter.setPen(QColor("#ffffff"))
    font_size = int(size * 0.52)
    font = QFont("Noto Sans CJK SC", font_size, QFont.Weight.Bold)
    if not font.exactMatch():
        font = QFont("WenQuanYi Micro Hei", font_size, QFont.Weight.Bold)
    if not font.exactMatch():
        font = QFont("Sans-Serif", font_size, QFont.Weight.Bold)
    painter.setFont(font)

    # 轻微上移居中，视觉效果更平衡
    text_rect = QRect(0, int(-size * 0.02), size, size)
    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "言")

    painter.end()
    return pixmap


def pack_pngs_to_ico(png_buffers: list[tuple[int, bytes]], output_path: Path) -> None:
    """将多个不同分辨率的 PNG 数据打包为标准的 Windows ICO 格式"""
    num_images = len(png_buffers)
    header = struct.pack("<HHH", 0, 1, num_images)
    
    entries = []
    offset = 6 + 16 * num_images
    data_blobs = []

    for size, data in png_buffers:
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        entries.append(entry)
        data_blobs.append(data)
        offset += len(data)

    with open(output_path, "wb") as f:
        f.write(header)
        for entry in entries:
            f.write(entry)
        for blob in data_blobs:
            f.write(blob)


def generate_all_icons(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])

    base_pixmap = create_base_icon_pixmap(512)

    # 保存主 PNG (256x256 及 512x512)
    png_256 = base_pixmap.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    png_256_path = assets_dir / "icon.png"
    png_256.save(str(png_256_path), "PNG")
    print(f"✅ 生成 Linux/通用图标: {png_256_path} (256x256)")

    # 生成多尺寸 Windows ICO (16, 32, 48, 64, 128, 256)
    ico_sizes = [16, 32, 48, 64, 128, 256]
    png_buffers: list[tuple[int, bytes]] = []

    for s in ico_sizes:
        scaled = base_pixmap.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buf, "PNG")
        png_buffers.append((s, bytes(buf.data())))
        buf.close()

    ico_path = assets_dir / "icon.ico"
    pack_pngs_to_ico(png_buffers, ico_path)
    print(f"✅ 生成 Windows 多分辨率 ICO 图标: {ico_path} (16~256px)")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    assets_dir = project_root / "assets"
    generate_all_icons(assets_dir)
