"""无焦点悬浮窗 PopupBubble 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pytest
from PySide6.QtWidgets import QApplication
from yanche.core.config import UIConfig
from yanche.core.models import TranslationResult
from yanche.adapters.gui.popup import PopupBubble


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_popup_init(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    assert popup.width() >= 320
    assert not popup.isVisible()
    popup.close()


def test_popup_display_success_markdown(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    result = TranslationResult(
        original_text="test text",
        translated_text="**测试加粗**\n- 列表项1\n- 列表项2",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
        latency_ms=120.0,
    )
    popup.display_result(result)
    assert popup.isVisible()
    assert "deepseek" in popup.provider_label.text()
    assert "120" in popup.latency_label.text()
    assert popup.original_label.text() == "test text"
    rendered_html = popup.text_browser.toHtml()
    assert "<b>" in rendered_html or "font-weight" in rendered_html or "strong" in rendered_html
    popup.close()


def test_popup_switch_provider(qapp):
    switched = []
    config = UIConfig()
    popup = PopupBubble(
        config,
        on_switch_provider=lambda p, txt: switched.append((p, txt)),
        available_providers=["deepseek", "openai"],
    )
    # 模拟先展示结果
    result = TranslationResult(
        original_text="sample",
        translated_text="示例",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
    )
    popup.display_result(result)

    # 模拟用户在菜单中切换为 openai
    popup._handle_provider_switch("openai")
    assert len(switched) == 1
    assert switched[0] == ("openai", "sample")
    assert "openai" in popup.provider_btn.text()
    popup.close()


def test_popup_display_error(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    result = TranslationResult(
        original_text="error text",
        translated_text="[Error] 认证失败 (401)",
        source_lang="en",
        target_lang="zh-CN",
        provider="openai",
        latency_ms=80.0,
    )
    popup.display_result(result)
    assert popup.isVisible()
    rendered_html = popup.text_browser.toHtml()
    assert "401" in rendered_html
    popup.close()


def test_popup_dismiss_if_outside(qapp):
    from PySide6.QtGui import QCursor
    config = UIConfig()
    popup = PopupBubble(config)
    popup.resize(320, 150)
    popup.move(100, 100)
    popup.show()

    # 1. 鼠标位于窗口外部 (500, 500)，未钉住状态下应自动收起
    QCursor.setPos(500, 500)
    popup.dismiss_if_outside()
    assert not popup.isVisible()

    # 2. 重新显示并钉住 (pin)
    popup.show()
    popup._is_pinned = True
    QCursor.setPos(500, 500)
    popup.dismiss_if_outside()
    # 钉住状态下即便点击外部也不收起
    assert popup.isVisible()

    # 3. 鼠标位于窗口内部 (150, 150)，未钉住状态下也不收起
    popup._is_pinned = False
    QCursor.setPos(150, 150)
    popup.dismiss_if_outside()
    assert popup.isVisible()

    popup.close()


def test_popup_closed_signal(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    popup.show()

    closed_fired = []
    popup.closed.connect(lambda: closed_fired.append(True))

    popup.hide()
    assert len(closed_fired) == 1
    popup.close()


def test_popup_card_components(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    assert hasattr(popup, "orig_card")
    assert hasattr(popup, "trans_card")
    assert hasattr(popup, "size_grip")
    assert hasattr(popup, "copy_orig_btn")
    assert hasattr(popup, "copy_btn")
    assert hasattr(popup, "more_btn")
    assert hasattr(popup, "pin_btn")
    popup.close()


def test_popup_pin_and_fixed_position(qapp):
    config = UIConfig()
    saved = []
    popup = PopupBubble(config, on_save_config=lambda: saved.append(True))

    # 1. 移动到 (200, 300) 并固定
    popup.move(200, 300)
    assert not popup._is_pinned
    popup._toggle_pin()
    assert popup._is_pinned
    assert popup.config.is_pinned
    assert popup.config.fixed_x == 200
    assert popup.config.fixed_y == 300
    assert len(saved) >= 1

    # 2. 模拟划词选词触发 display_loading 传入新的光标位置 (800, 900)
    # 因为已锁定，窗口必须留在 (200, 300)，坚决不跟随光标
    popup.display_loading("new selected text", 800, 900)
    assert popup.x() == 200
    assert popup.y() == 300

    # 3. 再次取消固定
    popup._toggle_pin()
    assert not popup._is_pinned
    assert not popup.config.is_pinned
    assert popup.config.fixed_x is None
    assert popup.config.fixed_y is None
    popup.close()


def test_popup_copy_buttons_and_meta(qapp):
    import pyperclip
    config = UIConfig()
    popup = PopupBubble(config)

    # 测试元数据计数
    assert popup._format_meta("Hello World") == "2 词 · 11 字符"
    assert popup._format_meta("言澈划词翻译") == "6 字符"

    result = TranslationResult(
        original_text="Artificial Intelligence",
        translated_text="人工智能",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
    )
    popup.display_result(result)
    assert "2 词" in popup.orig_meta_label.text()

    # 模拟点击复制原文
    popup._copy_original()
    assert pyperclip.paste() == "Artificial Intelligence"

    # 模拟点击复制译文
    popup._copy_result()
    assert pyperclip.paste() == "人工智能"

    popup.close()


def test_popup_reset_window_geometry(qapp):
    config = UIConfig(window_width=600, window_height=500, fixed_x=100, fixed_y=100, is_pinned=True)
    saved = []
    popup = PopupBubble(config, on_save_config=lambda: saved.append(True))
    assert popup._is_pinned

    # 触发恢复默认
    popup._reset_window_geometry()
    assert not popup._is_pinned
    assert not popup.config.is_pinned
    assert popup.config.window_width == 450
    assert popup.config.window_height == 320
    assert popup.config.fixed_x is None
    assert popup.config.fixed_y is None
    assert len(saved) >= 1
    popup.close()


def test_popup_splitter_and_only_translation(qapp):
    config = UIConfig(splitter_sizes=[120, 200], only_translation=False)
    saved = []
    popup = PopupBubble(config, on_save_config=lambda: saved.append(True))
    popup.show()

    # 1. 验证垂直分割器与子控件
    assert hasattr(popup, "splitter")
    assert popup.orig_card.isVisible()
    assert popup.trans_card.isVisible()

    # 2. 模拟拖拽分割线改变高度分配比例
    popup.splitter.setSizes([80, 240])
    popup._on_splitter_moved(80, 1)
    assert popup.config.splitter_sizes == popup.splitter.sizes()

    # 3. 切换为“只显示译文”
    popup._toggle_only_translation(True)
    assert popup._only_translation
    assert popup.config.only_translation
    assert not popup.orig_card.isVisible()
    assert popup.trans_card.isVisible()

    # 4. 再次切换为显示原文与译文
    popup._toggle_only_translation(False)
    assert not popup._only_translation
    assert not popup.config.only_translation
    assert popup.orig_card.isVisible()
    popup.close()


def test_popup_four_corner_resize_regions(qapp):
    from PySide6.QtCore import QPoint, QRect
    config = UIConfig(window_width=400, window_height=300)
    popup = PopupBubble(config)
    popup.resize(400, 300)

    # 验证四个角落的感应区域识别
    assert popup._get_resize_region(QPoint(2, 2)) == "top_left"
    assert popup._get_resize_region(QPoint(398, 2)) == "top_right"
    assert popup._get_resize_region(QPoint(2, 298)) == "bottom_left"
    assert popup._get_resize_region(QPoint(398, 298)) == "bottom_right"

    # 验证四条边缘的感应区域识别
    assert popup._get_resize_region(QPoint(2, 150)) == "left"
    assert popup._get_resize_region(QPoint(398, 150)) == "right"
    assert popup._get_resize_region(QPoint(200, 2)) == "top"
    assert popup._get_resize_region(QPoint(200, 298)) == "bottom"

    # 验证窗口中心区域不触发缩放
    assert popup._get_resize_region(QPoint(200, 150)) is None

    # 验证右下角拖拽拉伸逻辑
    popup._resize_region = "bottom_right"
    popup._resize_start_pos = QPoint(500, 500)
    popup._resize_start_geom = QRect(100, 100, 400, 300)
    popup._do_resize(QPoint(550, 560))
    assert popup.width() == 450
    assert popup.height() == 360

    popup.close()


def test_popup_opacity_change(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    popup.apply_theme(opacity=0.75)
    assert popup.windowOpacity() == pytest.approx(0.75, abs=0.01)
    assert popup.config.window_opacity == pytest.approx(0.75, abs=0.01)

    # 边界保护 (40% ~ 100%)
    popup.apply_theme(opacity=0.1)
    assert popup.config.window_opacity == pytest.approx(0.4, abs=0.01)
    popup.apply_theme(opacity=1.5)
    assert popup.config.window_opacity == pytest.approx(1.0, abs=0.01)
    popup.close()


def test_popup_mode_b_and_side_button(qapp):
    from yanche.core.config import SelectionConfig
    saved = []
    sel_config = SelectionConfig(auto_popup_on_selection=False, enable_mouse_side_button=True)
    popup = PopupBubble(
        UIConfig(),
        selection_config=sel_config,
        on_save_config=lambda: saved.append("saved"),
        on_update_selection_config=lambda: saved.append("updated_selection"),
    )

    # 切换模式 B 开启
    popup._toggle_auto_popup(True)
    assert sel_config.auto_popup_on_selection is True
    assert "updated_selection" in saved

    # 切换鼠标侧键关闭
    popup._toggle_mouse_side_button(False)
    assert sel_config.enable_mouse_side_button is False
    popup.close()


def test_hotkey_settings_dialog(qapp):
    from yanche.core.config import SelectionConfig
    from yanche.adapters.gui.popup import HotkeySettingsDialog

    saved = []
    sel_config = SelectionConfig(hotkey="<alt>+d")
    dialog = HotkeySettingsDialog(
        sel_config,
        on_save=lambda: saved.append(True),
    )
    assert dialog.input_hotkey.text() == "<alt>+d"

    # 修改快捷键并保存生效
    dialog.input_hotkey.setText("<ctrl>+<alt>+x")
    dialog._save_and_apply()
    assert sel_config.hotkey == "<ctrl>+<alt>+x"
    assert len(saved) == 1
    dialog.close()



