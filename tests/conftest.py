"""测试只使用临时配置和模拟剪贴板，不影响正在运行的软件。"""

import os
import importlib
import gc

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyperclip
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent

from yanxi.core.config import AppConfig


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    gc.collect()


@pytest.fixture
def controller(qapp, monkeypatch):
    main_module = importlib.import_module("yanxi.main")

    class FakeListener:
        def __init__(self, *args, **kwargs):
            self.options = kwargs
            self.running = False
        def start(self):
            self.running = True
        def stop(self):
            self.running = False
        def on_popup_closed(self):
            pass

    config = AppConfig()
    config.ui.open_on_startup = False
    config.update.auto_check_update = False
    config.ui.is_pinned = False
    config.ui.auto_translate_input = True
    monkeypatch.setattr(main_module.AppConfig, "load", classmethod(lambda cls: config))
    for name in ("WindowsSelectionListener", "LinuxX11SelectionListener", "HotkeySelectionListener"):
        monkeypatch.setattr(main_module, name, FakeListener)
    monkeypatch.setattr(main_module.YanXiApp, "_init_panic_failsafe", lambda self: None)
    monkeypatch.setattr(main_module.atexit, "register", lambda callback: None)
    monkeypatch.setattr(main_module.signal, "signal", lambda *args: None)
    app = main_module.YanXiApp(qapp)
    yield app
    app.shutdown()
    app.tray.setContextMenu(None)
    app.tray.deleteLater()


@pytest.fixture(autouse=True)
def isolated_user_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        AppConfig, "get_default_config_path",
        classmethod(lambda cls: tmp_path / "user-config" / "config.json"),
    )
    clipboard = {"text": ""}
    monkeypatch.setattr(pyperclip, "paste", lambda: clipboard["text"])
    monkeypatch.setattr(pyperclip, "copy", lambda text: clipboard.update(text=text))


@pytest.fixture(autouse=True)
def clean_qt_widgets(qapp, isolated_user_state):
    yield
    # 保持顶层窗口的 Python 强引用到 Qt 完成子菜单释放，避免析构时重入父窗口。
    widgets = list(qapp.topLevelWidgets())
    for widget in widgets:
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    gc.collect()
