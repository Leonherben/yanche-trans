# -*- mode: python ; coding: utf-8 -*-
"""言蹊翻译 (YanXi Trans) PyInstaller 打包配置文件

支持跨平台（Linux & Windows）构建紧凑的高性能发布目录。
同时集成 GUI 桌面应用 (yanxi) 与命令行工具 (yanxi-cli)。
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

project_dir = Path(SPECPATH).resolve()
src_dir = project_dir / "src"

# 收集 certifi 证书及内部资源
datas = collect_data_files("certifi")
assets_dir = project_dir / "assets"
if assets_dir.exists():
    for f in assets_dir.glob("*"):
        if f.is_file():
            datas.append((str(f), "assets"))

# 平台专属依赖收集
is_win = sys.platform.startswith("win")
is_linux = sys.platform.startswith("linux")

hiddenimports = [
    "yanxi",
    "yanxi.main",
    "yanxi.cli.main",
    "yanxi.adapters.gui.popup",
    "yanxi.adapters.gui.tray",
    "yanxi.adapters.gui.theme",
    "yanxi.adapters.gui.settings_dialog",
    "yanxi.adapters.selection.base",
    "yanxi.adapters.selection.linux_x11",
    "yanxi.adapters.selection.hotkey_fallback",
    "yanxi.core.config",
    "yanxi.core.models",
    "yanxi.core.cache.sqlite_cache",
    "yanxi.core.single_instance",
    "yanxi.core.translator.factory",
    "yanxi.core.translator.base",
    "yanxi.core.translator.openai_compatible",
    "yanxi.core.translator.microsoft",
    "pyperclip",
    "socksio",
    "httpx",
    "pydantic",
    "pydantic_core",
] + collect_submodules("pynput")

icon_file = str(assets_dir / "icon.ico") if is_win else str(assets_dir / "icon.png")
if not os.path.exists(icon_file):
    icon_file = None

# 精简排除未使用的大型组件与 Qt 子模块
shared_excludes = [
    "tkinter",
    "unittest",
    "pytest",
    "pdb",
    "difflib",
    "doctest",
    # 排除 PySide6 冗余大型模块
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtSql",
    "PySide6.QtXml",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
]

# 1. 分析 GUI 主程序
a_gui = Analysis(
    [str(src_dir / "yanxi" / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=shared_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="yanxi",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# 2. 分析 CLI 命令行程序
a_cli = Analysis(
    [str(src_dir / "yanxi" / "cli" / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=shared_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_cli = PYZ(a_cli.pure, a_cli.zipped_data, cipher=block_cipher)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="yanxi-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI 保持控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

# 过滤不需要的 Qt 动态库 (QtQuick, QtQml, QtPdf, QtVirtualKeyboard, QtOpenGL 等)
def filter_binaries(binaries):
    unwanted = ("quick", "qml", "pdf", "virtualkeyboard", "opengl")
    return [b for b in binaries if not any(u in b[0].lower() for u in unwanted)]

# 3. 收集并整合至同一目录 dist/yanxi
coll = COLLECT(
    exe_gui,
    filter_binaries(a_gui.binaries),
    a_gui.zipfiles,
    a_gui.datas,
    exe_cli,
    filter_binaries(a_cli.binaries),
    a_cli.zipfiles,
    a_cli.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="yanxi",
)
