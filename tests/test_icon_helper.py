import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QIcon, QPixmap
from yanxi.adapters.gui.icon_helper import (
    find_icon_path,
    find_icon_paths,
    get_app_icon,
    get_tray_icon,
    create_fallback_icon_pixmap,
    configure_windows_app_id,
)


def test_fallback_icon_pixmap(qapp):
    pix = create_fallback_icon_pixmap(64)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()
    assert pix.width() == 64
    assert pix.height() == 64


def test_find_icon_paths_and_path():
    paths = find_icon_paths()
    assert len(paths) >= 1
    names = [p.name for p in paths]
    assert "icon.png" in names or "icon.ico" in names

    path = find_icon_path()
    assert path is not None
    assert path.exists()


def test_get_app_icon_and_tray_icon(qapp):
    app_icon = get_app_icon()
    assert isinstance(app_icon, QIcon)
    assert not app_icon.isNull()

    tray_icon = get_tray_icon()
    assert isinstance(tray_icon, QIcon)
    assert not tray_icon.isNull()


def test_configure_windows_app_id():
    # 在非 Windows 平台无害执行，在 Windows 平台调用 Windows API
    configure_windows_app_id("test.app.id")

