#!/usr/bin/env python3
"""言蹊翻译 (YanXi Trans) 应用图标生成与部署脚本

基于 assets/icon.svg 矢量设计源文件，自动生成全尺寸 Linux PNG 与 Windows 多分辨率标准 ICO。
符合 Windows 规范：16~64px 采用标准 DIB/BMP 格式，128~256px 采用 PNG 格式。
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


def create_dib_icon_entry(qimg: QImage) -> bytes:
    """将 QImage 转换为标准的 Windows ICO DIB (BMP) 数据块。
    
    Windows 规范要求：16~64px 尺寸在 PE 资源与任务栏中必须使用 32 位 DIB 格式，
    包含 BITMAPINFOHEADER (biHeight 为 2*h，包含 XOR 与 AND 掩码) + BGRA 像素 + 1位 AND 掩码。
    """
    w = qimg.width()
    h = qimg.height()
    img = qimg.convertToFormat(QImage.Format.Format_ARGB32)

    header = struct.pack(
        "<IIIHHIIIIII",
        40,          # biSize (40 字节 BITMAPINFOHEADER)
        w,           # biWidth
        2 * h,       # biHeight (必须为 2*h)
        1,           # biPlanes
        32,          # biBitCount (32位真彩色 + 8位 Alpha)
        0,           # biCompression (BI_RGB)
        w * h * 4,   # biSizeImage
        0, 0, 0, 0   # 保留字段
    )

    pixel_data = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            pixel = img.pixelColor(x, y)
            pixel_data.extend([pixel.blue(), pixel.green(), pixel.red(), pixel.alpha()])

    row_bytes = (w + 31) // 32 * 4
    and_mask = bytearray(row_bytes * h)

    return header + bytes(pixel_data) + bytes(and_mask)


def pack_compliant_ico(entries: list[tuple[int, bytes]], output_path: Path) -> None:
    """将包含 DIB 与 PNG 的多个尺寸打包为标准的 Windows ICO 格式文件"""
    num_images = len(entries)
    header = struct.pack("<HHH", 0, 1, num_images)

    dir_entries = []
    offset = 6 + 16 * num_images
    data_blobs = []

    for size, data in entries:
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        entry = struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        dir_entries.append(entry)
        data_blobs.append(data)
        offset += len(data)

    with open(output_path, "wb") as f:
        f.write(header)
        for entry in dir_entries:
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
    print(f"✅ 生成 Linux/通用主图标: {png_256_path} (256x256)")

    # 2. 生成完全兼容 Windows 官方规范的多分辨率 ICO (16~64 DIB + 128~256 PNG)
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    entries: list[tuple[int, bytes]] = []

    for s in ico_sizes:
        img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        renderer.render(p, QRectF(0, 0, s, s))
        p.end()

        if s <= 64:
            data = create_dib_icon_entry(img)
        else:
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            data = bytes(buf.data())
            buf.close()

        entries.append((s, data))

    ico_path = assets_dir / "icon.ico"
    pack_compliant_ico(entries, ico_path)
    print(f"✅ 生成 Windows 标准混合格式 ICO 图标: {ico_path} (16~64px DIB + 128~256px PNG)")

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
