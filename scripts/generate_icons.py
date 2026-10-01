#!/usr/bin/env python3
"""言蹊翻译 (YanXi Trans) 应用图标生成与部署脚本

基于 assets/icon.svg 矢量设计源文件，自动生成全尺寸 Linux PNG 与 Windows 多分辨率 ICO。
"""

import os
import shutil
import struct
import sys
from pathlib import Path

# 确保无头渲染环境
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QRectF, QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


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
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1] + ["-platform", "offscreen"])

    svg_file = assets_dir / "icon.svg"
    if not svg_file.exists():
        raise FileNotFoundError(f"未找到矢量图标源文件: {svg_file}")

    renderer = QSvgRenderer(str(svg_file))

    # 1. 渲染并生成主 PNG (256x256)
    png_256_image = QImage(256, 256, QImage.Format.Format_ARGB32_Premultiplied)
    png_256_image.fill(Qt.GlobalColor.transparent)
    p256 = QPainter(png_256_image)
    p256.setRenderHint(QPainter.RenderHint.Antialiasing)
    p256.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(p256, QRectF(0, 0, 256, 256))
    p256.end()

    png_256_path = assets_dir / "icon.png"
    png_256_image.save(str(png_256_path), "PNG")
    print(f"✅ 生成 Linux/通用图标: {png_256_path} (256x256)")

    # 2. 生成多尺寸 Windows ICO (16, 24, 32, 48, 64, 128, 256)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    png_buffers: list[tuple[int, bytes]] = []

    for s in ico_sizes:
        img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(p, QRectF(0, 0, s, s))
        p.end()

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        png_buffers.append((s, bytes(buf.data())))
        buf.close()

    ico_path = assets_dir / "icon.ico"
    pack_pngs_to_ico(png_buffers, ico_path)
    print(f"✅ 生成 Windows 多分辨率 ICO 图标: {ico_path} (16~256px)")

    # 3. 同步安装至当前系统的用户图标目录 (Linux)
    if sys.platform.startswith("linux"):
        sys_icon = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "yanxi.png"
        sys_icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png_256_path, sys_icon)
        print(f"✅ 同步安装至系统图标目录: {sys_icon}")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    assets_dir = project_root / "assets"
    generate_all_icons(assets_dir)
