"""主题管理与透明度调节单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from yanche.core.config import UIConfig
from yanche.adapters.gui.theme import (
    detect_system_theme,
    get_effective_theme,
    get_theme_stylesheet,
    get_theme_menu_style,
    AVAILABLE_THEMES,
    AVAILABLE_OPACITIES,
)
from yanche.adapters.gui.popup import PopupBubble


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_detect_system_theme(qapp):
    theme = detect_system_theme()
    assert theme in ("dark", "light")


def test_get_effective_theme(qapp):
    assert get_effective_theme("dark") == "dark"
    assert get_effective_theme("light") == "light"
    assert get_effective_theme("glass") == "glass"
    # auto 必须解析为具体的 dark 或 light
    auto_res = get_effective_theme("auto")
    assert auto_res in ("dark", "light")


def test_theme_stylesheets(qapp):
    dark_qss = get_theme_stylesheet("dark")
    assert "#0d1117" in dark_qss
    assert "QFrame#main_container" in dark_qss

    light_qss = get_theme_stylesheet("light")
    assert "#ffffff" in light_qss
    assert "#f6f8fa" in light_qss

    glass_qss = get_theme_stylesheet("glass")
    assert "rgba" in glass_qss


def test_popup_theme_and_opacity_switch(qapp):
    config = UIConfig(theme="auto", window_opacity=0.95)
    saved = []
    popup = PopupBubble(config, on_save_config=lambda: saved.append(True))
    popup.show()

    # 1. 切换为浅色主题
    popup.apply_theme(theme_name="light")
    assert popup._theme == "light"
    assert popup.config.theme == "light"
    assert len(saved) >= 1

    # 2. 切换为透明玻璃主题
    popup.apply_theme(theme_name="glass")
    assert popup._theme == "glass"
    assert popup.config.theme == "glass"

    # 3. 自定义透明度
    popup.apply_theme(opacity=0.75)
    assert abs(popup._opacity - 0.75) < 0.01
    assert abs(popup.config.window_opacity - 0.75) < 0.01
    assert abs(popup.windowOpacity() - 0.75) < 0.01

    # 4. 边界保护测试 (不得低于 0.4，不得高于 1.0)
    popup.apply_theme(opacity=0.1)
    assert popup._opacity == 0.4
    popup.apply_theme(opacity=1.5)
    assert popup._opacity == 1.0

    popup.close()
