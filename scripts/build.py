#!/usr/bin/env python3
"""言蹊翻译 (YanXi Trans) 跨平台独立分发包打包构建脚本

支持在 Linux 与 Windows 环境下一键生成绿色便携与免安装发布压缩包。
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

# 确保在 Windows 或非 UTF-8 控制台下输出 Emoji 和中文不抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_version(project_root: Path) -> str:
    init_file = project_root / "src" / "yanxi" / "__init__.py"
    if init_file.exists():
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_file.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    return "0.1.0"


def generate_linux_desktop_files(bundle_dir: Path) -> None:
    """生成 Linux 下的 .desktop 快捷方式与一键安装/卸载脚本"""
    install_script = bundle_dir / "install.sh"
    install_script.write_text(
        """#!/usr/bin/env bash
set -e

APP_NAME="yanxi"
INSTALL_DIR="$HOME/.local/opt/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📦 正在安装 言蹊翻译 (YanXi Trans)..."

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# 复制二进制及所有依赖
cp -rf "$SCRIPT_DIR"/* "$INSTALL_DIR/"

# 建立全局命令软链接
ln -sf "$INSTALL_DIR/yanxi" "$BIN_DIR/yanxi"
ln -sf "$INSTALL_DIR/yanxi-cli" "$BIN_DIR/yanxi-cli"

# 安装图标
if [ -f "$INSTALL_DIR/assets/icon.png" ]; then
    cp "$INSTALL_DIR/assets/icon.png" "$ICON_DIR/yanxi.png"
fi

# 生成桌面快捷方式
cat > "$DESKTOP_DIR/yanxi.desktop" <<EOF
[Desktop Entry]
Name=言蹊翻译
GenericName=桌面划词翻译
Comment=轻量级、无焦点窃取的桌面划词翻译工具
Exec=$INSTALL_DIR/yanxi
Icon=yanxi
Terminal=false
Type=Application
Categories=Utility;Office;Translation;
StartupNotify=false
EOF

chmod +x "$DESKTOP_DIR/yanxi.desktop"
chmod +x "$INSTALL_DIR/yanxi"
chmod +x "$INSTALL_DIR/yanxi-cli"

echo "✨ 安装成功！"
echo "   • 命令行运行: yanxi 或 yanxi-cli"
echo "   • 快捷方式已加入应用程序菜单 (言蹊翻译)"
""",
        encoding="utf-8",
    )
    install_script.chmod(0o755)

    uninstall_script = bundle_dir / "uninstall.sh"
    uninstall_script.write_text(
        """#!/usr/bin/env bash
set -e

echo "🗑️ 正在卸载 言蹊翻译..."
rm -rf "$HOME/.local/opt/yanxi"
rm -f "$HOME/.local/bin/yanxi" "$HOME/.local/bin/yanxi-cli"
rm -f "$HOME/.local/share/applications/yanxi.desktop"
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/yanxi.png"
echo "✅ 言蹊翻译 已完全卸载。"
""",
        encoding="utf-8",
    )
    uninstall_script.chmod(0o755)


def generate_windows_helpers(bundle_dir: Path) -> None:
    """生成 Windows 下的便捷启动与说明文件"""
    bat_content = """@echo off
chcp 65001 >nul 2>&1
start "" "%~dp0yanxi.exe"
exit
"""
    (bundle_dir / "启动言蹊翻译.bat").write_text(bat_content, encoding="utf-8")
    (bundle_dir / "run_yanxi.bat").write_text(bat_content, encoding="utf-8")

    # 创建桌面快捷方式 (带精准 icon.ico 图标绑定)
    vbs_content = """Set WshShell = CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")
strCurrentDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
Set oShellLink = WshShell.CreateShortcut(strDesktop & "\\言蹊翻译.lnk")
oShellLink.TargetPath = strCurrentDir & "\\yanxi.exe"
oShellLink.WorkingDirectory = strCurrentDir
oShellLink.Description = "言蹊翻译 - 极速桌面划词翻译工具"
If CreateObject("Scripting.FileSystemObject").FileExists(strCurrentDir & "\\assets\\icon.ico") Then
    oShellLink.IconLocation = strCurrentDir & "\\assets\\icon.ico,0"
Else
    oShellLink.IconLocation = strCurrentDir & "\\yanxi.exe,0"
End If
oShellLink.Save
MsgBox "桌面快捷方式已成功创建！" & vbCrLf & "可在桌面双击【言蹊翻译】图标启动应用。", 64, "言蹊翻译"
"""
    (bundle_dir / "创建桌面快捷方式.vbs").write_text(vbs_content, encoding="utf-8")

    shortcut_bat = """@echo off
cscript //nologo "%~dp0创建桌面快捷方式.vbs"
"""
    (bundle_dir / "创建桌面快捷方式.bat").write_text(shortcut_bat, encoding="utf-8")

    readme = bundle_dir / "README_使用说明.txt"
    readme.write_text(
        """言蹊翻译 (YanXi Trans) Windows 绿色免安装版
==================================================

【如何使用】
1. 双击运行 "启动言蹊翻译.bat" 或 "yanxi.exe"；
2. 推荐双击 "创建桌面快捷方式.vbs"，将在桌面生成带言蹊精美图标的快捷方式；
3. 程序启动后将在屏幕右下角系统托盘静默常驻；
4. 选中文本按下快捷键 (默认 Alt+D) 即可立即划词翻译！

【功能亮点】
- 预置免费微软翻译 (Microsoft Translator)，开箱即用免配置
- 悬浮窗采用无焦点置顶防抢占技术，打字输入不中断
- 右下角托盘图标支持一键切换翻译引擎、暗黑/亮色主题与透明度
- 偏好设置中内置【软件更新与关于】，支持在线检测 GitHub 最新版本并一键升级

【命令行支持】
可在当前目录下打开 CMD / PowerShell 运行：
  .\\yanxi-cli.exe "Hello world"
==================================================
""",
        encoding="utf-8",
    )


def create_archive(bundle_dir: Path, out_archive: Path, is_win: bool) -> None:
    if out_archive.exists():
        out_archive.unlink()

    print(f"📦 正在打包发布压缩包: {out_archive.name} ...")
    if is_win or str(out_archive).endswith(".zip"):
        with zipfile.ZipFile(out_archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(bundle_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = Path("yanxi") / full_p.relative_to(bundle_dir)
                    zf.write(full_p, rel_p)
    else:
        with tarfile.open(out_archive, "w:gz") as tf:
            tf.add(bundle_dir, arcname="yanxi")


def prune_bundle(bundle_dir: Path) -> None:
    """清理打包产物中未使用的多余静态资源和多国语言包，极致优化发布包体积"""
    print("\n[3.5/4] 深度优化打包体积，清理多余静态与翻译资源...")
    # 精简 Qt translations (清理 6MB+ 冗余多国语言包，仅保留中文或全部移除)
    translations_dir = bundle_dir / "_internal" / "PySide6" / "Qt" / "translations"
    if translations_dir.exists():
        removed_count = 0
        removed_bytes = 0
        for f in list(translations_dir.glob("*.qm")):
            if not f.name.startswith("qt_zh_CN"):
                removed_bytes += f.stat().st_size
                f.unlink()
                removed_count += 1
        print(f"   • 清理冗余多国语言包: 移除 {removed_count} 个文件 (释放 {removed_bytes / 1024 / 1024:.2f} MB)")

    # 清理未使用的 Qt 插件 (如虚拟键盘、PDF 查看器等)
    plugins_dir = bundle_dir / "_internal" / "PySide6" / "Qt" / "plugins"
    if plugins_dir.exists():
        plugin_pruned = 0
        for p in list(plugins_dir.rglob("*")):
            if p.is_file() and any(k in p.name.lower() for k in ("virtualkeyboard", "pdf")):
                p.unlink()
                plugin_pruned += 1
        if plugin_pruned > 0:
            print(f"   • 清理冗余 Qt 插件: 移除 {plugin_pruned} 个组件")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist"
    version = get_version(project_root)
    is_win = sys.platform.startswith("win")
    platform_name = "windows-x86_64" if is_win else "linux-x86_64"

    print("=" * 60)
    print(f"🚀 开始构建 言蹊翻译 (YanXi Trans) v{version} [{platform_name}]")
    print("=" * 60)

    # 1. 确保图标就绪
    print("\n[1/4] 检查高清多尺寸应用图标...")
    assets_dir = project_root / "assets"
    png_icon = assets_dir / "icon.png"
    ico_icon = assets_dir / "icon.ico"
    if not (png_icon.exists() and ico_icon.exists()):
        print("   • 未检测到预置图标，正在生成...")
        gen_icon_script = project_root / "scripts" / "generate_icons.py"
        try:
            subprocess.run([sys.executable, str(gen_icon_script)], check=True)
        except Exception as e:
            print(f"⚠️ 图标生成跳过 (环境缺失图形渲染库): {e}")
    else:
        print(f"   • 使用已有静态高清图标: {png_icon.name}, {ico_icon.name}")

    # 2. 运行 PyInstaller
    print("\n[2/4] 运行 PyInstaller 构建独立程序目录...")
    spec_file = project_root / "yanxi.spec"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "-y", str(spec_file)],
        cwd=project_root,
        check=True,
    )

    bundle_dir = dist_dir / "yanxi"
    if not bundle_dir.exists():
        print(f"❌ 错误: 未找到打包产物目录 {bundle_dir}")
        sys.exit(1)

    # 3. 注入平台辅助文件
    print("\n[3/4] 注入平台专属辅助文件与说明...")
    dist_assets = bundle_dir / "assets"
    dist_assets.mkdir(parents=True, exist_ok=True)
    if assets_dir.exists():
        for f in assets_dir.glob("*"):
            if f.is_file():
                shutil.copy2(f, dist_assets / f.name)

    if is_win:
        generate_windows_helpers(bundle_dir)
        archive_name = f"yanxi-v{version}-{platform_name}.zip"
    else:
        generate_linux_desktop_files(bundle_dir)
        archive_name = f"yanxi-v{version}-{platform_name}.tar.gz"

    # 深度体积瘦身
    prune_bundle(bundle_dir)

    # 4. 生成压缩归档包
    print("\n[4/4] 生成可供直接下载的发布压缩包...")
    out_archive = dist_dir / archive_name
    create_archive(bundle_dir, out_archive, is_win)

    archive_size_mb = out_archive.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(f"🎉 构建完成！")
    print(f"📁 发布文件: {out_archive}")
    print(f"📊 文件大小: {archive_size_mb:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
