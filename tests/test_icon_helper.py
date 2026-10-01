import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QPixmap
from yanxi.adapters.gui.icon_helper import (
    find_icon_path,
    get_app_icon,
    get_tray_icon,
    create_fallback_icon_pixmap,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_fallback_icon_pixmap(qapp):
    pix = create_fallback_icon_pixmap(64)
    assert isinstance(pix, QPixmap)
    assert not pix.isNull()
    assert pix.width() == 64
    assert pix.height() == 64


def test_find_icon_path():
    path = find_icon_path()
    assert path is not None
    assert path.exists()
    assert path.name == "icon.png"


def test_get_app_icon_and_tray_icon(qapp):
    app_icon = get_app_icon()
    assert isinstance(app_icon, QIcon)
    assert not app_icon.isNull()

    tray_icon = get_tray_icon()
    assert isinstance(tray_icon, QIcon)
    assert not tray_icon.isNull()
