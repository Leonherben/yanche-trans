"""无焦点悬浮窗 PopupBubble 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pytest
from yanxi.core.config import UIConfig
from yanxi.core.models import TranslationResult
from yanxi.adapters.gui.popup import PopupBubble


def test_popup_init(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    assert popup.width() >= 320
    assert not popup.isVisible()
    assert popup._current_provider == "microsoft"
    popup.set_active_provider("deepseek")
    assert popup._current_provider == "deepseek"
    assert "DeepSeek" in popup.provider_btn.text()
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
    assert "DeepSeek" in popup.provider_label.text()
    assert "120" in popup.latency_label.text()
    assert popup.latency_label.isVisible()
    assert popup.orig_meta_label.isVisible()
    assert "9 字符" in popup.orig_meta_label.text()
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
    assert "OpenAI" in popup.provider_btn.text()
    popup.close()


def test_popup_open_settings_callback(qapp):
    opened = []
    config = UIConfig()
    popup = PopupBubble(config, on_open_settings=lambda: opened.append(True))
    assert popup.on_open_settings is not None
    popup.on_open_settings()
    assert len(opened) == 1
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
    from yanxi.core.config import SelectionConfig
    config = UIConfig(is_pinned=False)

    # 1. 经典非伴随模式 (auto_popup_only_when_visible=False)
    classic_sel = SelectionConfig(auto_popup_only_when_visible=False)
    popup = PopupBubble(config, selection_config=classic_sel)
    popup.resize(320, 150)
    popup.move(100, 100)
    popup.show()

    # 鼠标位于窗口外部 (500, 500)，未钉住状态下应自动收起
    QCursor.setPos(500, 500)
    popup.dismiss_if_outside()
    assert not popup.isVisible()

    # 重新显示并钉住 (pin)
    popup.show()
    popup._is_pinned = True
    QCursor.setPos(500, 500)
    popup.dismiss_if_outside()
    # 钉住状态下即便点击外部也不收起
    assert popup.isVisible()

    # 鼠标位于窗口内部 (150, 150)，未钉住状态下也不收起
    popup._is_pinned = False
    QCursor.setPos(150, 150)
    popup.dismiss_if_outside()
    assert popup.isVisible()
    popup.close()

    # 2. 伴随阅读模式 (auto_popup_only_when_visible=True)
    companion_sel = SelectionConfig(auto_popup_only_when_visible=True)
    companion_popup = PopupBubble(config, selection_config=companion_sel)
    companion_popup.resize(320, 150)
    companion_popup.move(100, 100)
    companion_popup.show()

    # 伴随阅读模式下，点击外部绝不自动收起，保障长文阅读顺畅
    QCursor.setPos(500, 500)
    companion_popup.dismiss_if_outside()
    assert companion_popup.isVisible()
    companion_popup.close()


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
    config = UIConfig(is_pinned=False)
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
    assert popup._format_meta("言蹊划词翻译") == "6 字符"

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

    # 错误不作为译文复制，提供重试入口。
    err_result = TranslationResult(
        original_text="Test Error",
        translated_text="[Error] 微软翻译错误: 动态会话失败",
        source_lang="en",
        target_lang="zh-CN",
        provider="microsoft",
    )
    popup.display_result(err_result)
    popup._copy_result()
    assert pyperclip.paste() == "人工智能"
    assert not popup.copy_btn.isEnabled()
    assert popup.retry_btn.isVisible()

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


def test_popup_selection_mode_and_side_button(qapp):
    from yanxi.core.config import SelectionConfig, SelectionMode
    saved = []
    sel_config = SelectionConfig(auto_popup_on_selection=False, enable_mouse_side_button=True)
    popup = PopupBubble(
        UIConfig(),
        selection_config=sel_config,
        on_save_config=lambda: saved.append("saved"),
        on_update_selection_config=lambda: saved.append("updated_selection"),
    )

    popup._set_selection_mode(SelectionMode.AUTOMATIC)
    assert sel_config.auto_popup_on_selection is True
    assert sel_config.auto_popup_only_when_visible is False
    assert "划选即翻译" in popup.mode_btn.text()
    assert "updated_selection" in saved

    # 切换鼠标侧键关闭
    popup._toggle_mouse_side_button(False)
    assert sel_config.enable_mouse_side_button is False
    popup.close()


def test_hotkey_settings_dialog(qapp):
    from yanxi.core.config import SelectionConfig
    from yanxi.adapters.gui.popup import HotkeySettingsDialog

    saved = []
    sel_config = SelectionConfig(hotkey="<alt>+d", extra_hotkeys=["<ctrl>+<alt>+t"])
    dialog = HotkeySettingsDialog(
        sel_config,
        on_save=lambda: saved.append(True),
    )
    assert len(dialog.rows) == 2
    assert dialog.rows[0].get_hotkey() == "<alt>+d"
    assert dialog.rows[1].get_hotkey() == "<ctrl>+<alt>+t"

    # 1. 快速添加预设 F2
    dialog._quick_add_preset("<f2>")
    assert len(dialog.rows) == 3
    assert dialog.rows[2].get_hotkey() == "<f2>"

    # 2. 模拟添加新行并录制/输入自定义快捷键
    new_row = dialog._add_row("<alt>+q")
    assert len(dialog.rows) == 4
    assert new_row.get_hotkey() == "<alt>+q"

    # 3. 模拟删除第 2 个快捷键 (Ctrl+Alt+T)
    row_to_del = dialog.rows[1]
    dialog._remove_row(row_to_del)
    assert len(dialog.rows) == 3

    # 4. 保存并生效
    dialog._save_and_apply()
    assert sel_config.hotkey == "<alt>+d"
    assert sel_config.extra_hotkeys == ["<f2>", "<alt>+q"]
    assert sel_config.get_all_hotkeys() == ["<alt>+d", "<f2>", "<alt>+q"]
    assert len(saved) == 1

    # 5. 恢复默认测试
    dialog._reset_to_default()
    assert len(dialog.rows) == 1
    assert dialog.rows[0].get_hotkey() == "<alt>+d"

    dialog.close()


def test_key_recorder_edit_and_qt_keys(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from yanxi.adapters.gui.popup import KeyRecorderEdit, qkey_to_pynput

    edit = KeyRecorderEdit("<alt>+d")
    assert edit.get_hotkey_value() == "<alt>+d"
    assert edit.text() == "Alt + D"

    # 测试 qkey_to_pynput 辅助函数
    assert qkey_to_pynput(Qt.KeyboardModifier.AltModifier, Qt.Key.Key_D) == "<alt>+d"
    assert qkey_to_pynput(Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier, Qt.Key.Key_T) == "<ctrl>+<alt>+t"
    assert qkey_to_pynput(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_F2) == "<f2>"

    # 模拟进入录制模式并按下按键
    edit.start_recording()
    assert edit._is_recording is True

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Q, Qt.KeyboardModifier.AltModifier)
    edit.keyPressEvent(event)
    assert edit._is_recording is False
    assert edit.get_hotkey_value() == "<alt>+q"
    assert edit.text() == "Alt + Q"


def test_popup_manual_input_and_editing(qapp):
    retranslated = []
    config = UIConfig()
    popup = PopupBubble(config, on_retranslate=lambda text: retranslated.append(text))

    assert hasattr(popup, "original_edit")
    assert hasattr(popup, "clear_orig_btn")
    assert hasattr(popup, "translate_btn")

    # 1. 模拟设置原文并显示
    popup.show()
    popup.original_label.setText("Hello World")
    assert popup.original_label.text() == "Hello World"
    assert popup.original_edit.toPlainText() == "Hello World"

    # 2. 模拟用户输入文本，按钮显示
    popup.original_edit.setPlainText("New manual text")
    popup._on_original_text_changed()
    assert popup.clear_orig_btn.isVisible()
    assert popup.translate_btn.isVisible()

    # 3. 模拟按键回车即时翻译
    popup._on_manual_translate_requested()
    assert len(retranslated) == 1
    assert retranslated[0] == "New manual text"

    # 4. 模拟清空按钮
    popup._clear_input()
    assert popup.original_edit.toPlainText() == ""
    assert popup.original_label.text() == ""
    assert not popup.clear_orig_btn.isVisible()
    assert not popup.translate_btn.isVisible()

    # 5. 测试 open_for_input 唤醒
    popup.open_for_input()
    qapp.processEvents()
    assert popup.isVisible()
    assert popup.original_edit.hasFocus()

    popup.close()


def test_original_text_edit_keys(qapp):
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    from yanxi.adapters.gui.popup import OriginalTextEdit

    w = QWidget()
    edit = OriginalTextEdit(w)
    w.show()
    edit.setFocus()
    qapp.processEvents()

    triggered = []
    edit.return_pressed.connect(lambda: triggered.append(True))

    # 1. Shift + Enter 换行，不触发 return_pressed
    ev_shift_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    edit.keyPressEvent(ev_shift_enter)
    assert len(triggered) == 0

    # 2. Enter 触发 return_pressed
    ev_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    edit.keyPressEvent(ev_enter)
    assert len(triggered) == 1

    # 3. Ctrl + Enter 触发 return_pressed
    ev_ctrl_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    edit.keyPressEvent(ev_ctrl_enter)
    assert len(triggered) == 2

    # 4. Escape 隐藏父窗口
    ev_esc = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    edit.keyPressEvent(ev_esc)
    assert not w.isVisible()

    w.close()






