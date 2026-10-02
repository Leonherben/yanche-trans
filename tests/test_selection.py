"""选词清洗逻辑单测"""

import pytest
from yanxi.adapters.selection.base import BaseSelectionListener


class DummySelectionListener(BaseSelectionListener):
    def start(self) -> None:
        pass
    def stop(self) -> None:
        pass


def test_sanitize_valid_text():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=100)
    assert listener.sanitize_text("  hello world  ") == "hello world"
    assert listener.sanitize_text("Python3") == "Python3"


def test_sanitize_too_short_or_empty():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=10)
    assert listener.sanitize_text("") is None
    assert listener.sanitize_text("   ") is None
    assert listener.sanitize_text("a") is None


def test_sanitize_pure_symbols():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=100)
    assert listener.sanitize_text("---") is None
    assert listener.sanitize_text("!@#$%^&*()") is None
    assert listener.sanitize_text(" \n\t  ") is None


def test_sanitize_too_long():
    listener = DummySelectionListener(lambda text, pos: None, min_length=1, max_length=10)
    assert listener.sanitize_text("this is too long text") is None


def test_linux_x11_repeat_selection_and_reset(mocker):
    from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener

    callbacks = []
    empty_clicks = []

    listener = LinuxX11SelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        repeat_threshold_seconds=1.5,
        debounce_ms=0,
        on_empty_click=lambda pos: empty_clicks.append(pos),
    )

    # 1. 模拟第一次划词 "hello"
    mocker.patch.object(listener, "_get_primary_selection", return_value="hello")
    mocker.patch("time.time", side_effect=[100.0, 100.0, 100.0])
    listener._process_selection(100, 200)
    assert len(callbacks) == 1
    assert callbacks[0] == ("hello", (100, 200))

    # 2. 紧接着在阈值内划选相同内容 "hello"（应忽略）
    mocker.patch("time.time", side_effect=[100.5, 100.5])
    listener._process_selection(100, 200)
    assert len(callbacks) == 1

    # 3. 超过 1.5 秒阈值后再次划选相同内容 "hello"（应允许再次触发）
    mocker.patch("time.time", side_effect=[102.0, 102.0])
    listener._process_selection(110, 210)
    assert len(callbacks) == 2
    assert callbacks[1] == ("hello", (110, 210))

    # 4. 手动重置后划选相同内容（应立即触发）
    listener.reset_last_selection()
    mocker.patch("time.time", side_effect=[102.2, 102.2])
    listener._process_selection(120, 220)
    assert len(callbacks) == 3

    # 5. 模拟普通单击（未划选有效文本），应触发 on_empty_click
    mocker.patch.object(listener, "_get_primary_selection", return_value="")
    mocker.patch("time.time", side_effect=[105.0, 105.0])
    listener._process_selection(50, 60)
    assert len(empty_clicks) == 1
    assert empty_clicks[0] == (50, 60)


def test_linux_x11_auto_popup_false(mocker):
    from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener

    callbacks = []
    empty_clicks = []

    # 模式 B：划选不自动弹窗 (auto_popup=False)
    listener = LinuxX11SelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        auto_popup=False,
        debounce_ms=0,
        on_empty_click=lambda pos: empty_clicks.append(pos),
    )

    # 1. 划选了有效文本时，因为 auto_popup 为 False，不触发 callback
    mocker.patch.object(listener, "_get_primary_selection", return_value="hello world")
    listener._process_selection(100, 200, force=False)
    assert len(callbacks) == 0
    assert len(empty_clicks) == 0

    # 2. 模拟普通单击（未划选文本），应触发 on_empty_click 关闭已有浮窗
    mocker.patch.object(listener, "_get_primary_selection", return_value="")
    listener._process_selection(100, 200, force=False)
    assert len(callbacks) == 0
    assert len(empty_clicks) == 1
    assert empty_clicks[0] == (100, 200)


def test_linux_x11_mouse_side_buttons(mocker):
    import time
    from pynput import mouse
    from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener

    callbacks = []
    listener = LinuxX11SelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        auto_popup=False,
        enable_mouse_side_button=True,
        debounce_ms=0,
    )
    listener._is_running = True

    mocker.patch.object(listener, "_get_primary_selection", return_value="side button translation")

    # 1. 验证 force=True (侧键触发) 即使 auto_popup=False 也能立即触发翻译
    listener._process_selection(300, 400, force=True)
    assert len(callbacks) == 1
    assert callbacks[0] == ("side button translation", (300, 400))

    # 2. 验证 _on_click 派发侧键逻辑
    processed = []
    mocker.patch.object(listener, "_process_selection", lambda x, y, force=False: processed.append((x, y, force)))

    b8 = getattr(mouse.Button, "button8", getattr(mouse.Button, "x1", None))
    b9 = getattr(mouse.Button, "button9", getattr(mouse.Button, "x2", None))

    listener._on_click(300, 400, b8, False)
    time.sleep(0.05)
    assert len(processed) == 1
    assert processed[0] == (300, 400, True)

    listener._on_click(350, 450, b9, False)
    time.sleep(0.05)
    assert len(processed) == 2
    assert processed[1] == (350, 450, True)

    # 3. 若禁用侧键，则不派发
    listener.enable_mouse_side_button = False
    listener._on_click(300, 400, b8, False)
    time.sleep(0.05)
    assert len(processed) == 2



def test_hotkey_selection_listener_trigger(mocker):
    from pynput import mouse
    from yanxi.adapters.selection.hotkey_fallback import HotkeySelectionListener

    callbacks = []
    listener = HotkeySelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        hotkey_str="<alt>+d",
        extra_hotkeys=["<ctrl>+<alt>+t"],
        get_x11_selection_fn=lambda: "instant selected text",
    )

    mocker.patch.object(mouse.Controller, "position", new_callable=mocker.PropertyMock, return_value=(250, 350))
    # 模拟触发捕获流程
    listener._trigger_capture()

    assert len(callbacks) == 1
    assert callbacks[0] == ("instant selected text", (250, 350))


def test_hotkey_selection_listener_no_selection_trigger(mocker):
    from pynput import mouse
    import pyperclip
    from yanxi.adapters.selection.hotkey_fallback import HotkeySelectionListener

    callbacks = []
    no_sel_called = []
    listener = HotkeySelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        hotkey_str="<alt>+d",
        get_x11_selection_fn=lambda: "",
        on_no_selection=lambda: no_sel_called.append(True),
    )

    mocker.patch.object(mouse.Controller, "position", new_callable=mocker.PropertyMock, return_value=(250, 350))
    mocker.patch.object(pyperclip, "paste", return_value="")
    listener._trigger_capture()

    assert len(callbacks) == 0
    assert len(no_sel_called) == 1



def test_hotkey_helpers_normalize_and_display():
    from yanxi.adapters.selection.hotkey_fallback import (
        normalize_to_pynput,
        format_for_display,
        is_valid_pynput_hotkey,
    )

    # 1. 规范化测试
    assert normalize_to_pynput("Alt + D") == "<alt>+d"
    assert normalize_to_pynput("ctrl+alt+t") == "<ctrl>+<alt>+t"
    assert normalize_to_pynput("Ctrl + Shift + F2") == "<ctrl>+<shift>+<f2>"
    assert normalize_to_pynput("<alt>+d") == "<alt>+d"
    assert normalize_to_pynput("F9") == "<f9>"

    # 2. 展示格式化测试
    assert format_for_display("<alt>+d") == "Alt + D"
    assert format_for_display("<ctrl>+<alt>+t") == "Ctrl + Alt + T"
    assert format_for_display("<ctrl>+<shift>+<f2>") == "Ctrl + Shift + F2"

    # 3. 合法性校验测试
    assert is_valid_pynput_hotkey("<alt>+d") is True
    assert is_valid_pynput_hotkey("<ctrl>+<alt>+t") is True
    assert is_valid_pynput_hotkey("<f2>") is True
    assert is_valid_pynput_hotkey("invalid_combo_string") is False
    assert is_valid_pynput_hotkey("") is False


def test_linux_x11_is_inside_popup_ignored(mocker):
    from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener
    from pynput import mouse

    callbacks = []
    # 模拟悬浮窗区域在 (100, 100) 到 (300, 300)
    def inside_popup(pos):
        x, y = pos
        return 100 <= x <= 300 and 100 <= y <= 300

    listener = LinuxX11SelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        auto_popup=True,
        debounce_ms=0,
        is_inside_popup=inside_popup,
    )
    listener._is_running = True
    mocker.patch.object(listener, "_get_primary_selection", return_value="hello")

    # 点击落在浮窗内部（例如点击关闭按钮 (290, 110)），应当被完全忽略
    listener._on_click(290, 110, mouse.Button.left, True)
    listener._on_click(290, 110, mouse.Button.left, False)
    assert len(callbacks) == 0

    # 浮窗关闭冷却保护期内，同样忽略
    listener.on_popup_closed()
    listener._process_selection(400, 400)
    assert len(callbacks) == 0


def test_windows_selection_listener(mocker):
    from yanxi.adapters.selection.windows import WindowsSelectionListener
    from pynput import mouse

    callbacks = []
    empty_clicks = []

    def inside_popup(pos):
        return pos[0] < 50

    listener = WindowsSelectionListener(
        callback=lambda text, pos: callbacks.append((text, pos)),
        auto_popup=True,
        debounce_ms=0,
        on_empty_click=lambda pos: empty_clicks.append(pos),
        is_inside_popup=inside_popup,
    )
    listener._is_running = True

    # 1. 模拟浮窗内点击，忽略
    listener._on_click(30, 30, mouse.Button.left, True)
    listener._on_click(30, 30, mouse.Button.left, False)
    assert len(callbacks) == 0

    # 2. 模拟真实划选拖拽手势 (从 100,100 拖到 200,100)
    mocker.patch.object(listener, "_capture_selected_text_via_clipboard", return_value="Windows Selected Text")
    listener._on_click(100, 100, mouse.Button.left, True)
    listener._on_click(200, 100, mouse.Button.left, False)
    # 给线程一点点调度时间
    import time
    time.sleep(0.05)

    assert len(callbacks) == 1
    assert callbacks[0] == ("Windows Selected Text", (200, 100))

    # 3. 模拟普通单击（未拖拽且非双击），触发 empty_click
    listener._on_click(300, 300, mouse.Button.left, True)
    listener._on_click(300, 300, mouse.Button.left, False)
    assert len(empty_clicks) == 1
    assert empty_clicks[0] == (300, 300)


def test_companion_reading_mode_behavior(mocker):
    import time
    from pynput import mouse
    from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener
    from yanxi.adapters.selection.windows import WindowsSelectionListener

    # 1. 验证 Linux 监听器伴随阅读模式
    linux_callbacks = []
    is_visible = False
    linux_listener = LinuxX11SelectionListener(
        callback=lambda text, pos: linux_callbacks.append((text, pos)),
        auto_popup=True,
        auto_popup_only_when_visible=True,
        is_popup_visible=lambda: is_visible,
        debounce_ms=0,
    )
    linux_listener._is_running = True
    mocker.patch.object(linux_listener, "_get_primary_selection", return_value="companion text linux")

    # 浮窗隐藏时：划选操作不触发弹窗翻译
    is_visible = False
    linux_listener._process_selection(100, 100, force=False)
    assert len(linux_callbacks) == 0

    # 快捷键 / 侧键强行触发 (force=True)：不受浮窗隐藏限制
    linux_listener._process_selection(100, 100, force=True)
    assert len(linux_callbacks) == 1
    assert linux_callbacks[0][0] == "companion text linux"

    # 浮窗展开时：划选新文本立即触发就地翻译
    mocker.patch.object(linux_listener, "_get_primary_selection", return_value="companion text linux 2")
    is_visible = True
    linux_listener._process_selection(150, 150, force=False)
    assert len(linux_callbacks) == 2
    assert linux_callbacks[1][0] == "companion text linux 2"

    # 2. 验证 Windows 监听器伴随阅读模式
    win_callbacks = []
    is_win_visible = False
    win_listener = WindowsSelectionListener(
        callback=lambda text, pos: win_callbacks.append((text, pos)),
        auto_popup=True,
        auto_popup_only_when_visible=True,
        is_popup_visible=lambda: is_win_visible,
        debounce_ms=0,
    )
    win_listener._is_running = True
    mocker.patch.object(win_listener, "_capture_selected_text_via_clipboard", return_value="companion text win")

    # 浮窗隐藏时：鼠标划选不触发翻译
    is_win_visible = False
    win_listener._on_click(100, 100, mouse.Button.left, True)
    win_listener._on_click(200, 100, mouse.Button.left, False)
    time.sleep(0.05)
    assert len(win_callbacks) == 0

    # 浮窗隐藏时：快捷键或侧键 force=True 依然可以触发
    win_listener._process_selection(100, 100, force=True)
    assert len(win_callbacks) == 1
    assert win_callbacks[0][0] == "companion text win"

    # 浮窗展开时：鼠标划选新文本立即触发翻译
    mocker.patch.object(win_listener, "_capture_selected_text_via_clipboard", return_value="companion text win 2")
    is_win_visible = True
    win_listener._on_click(100, 100, mouse.Button.left, True)
    win_listener._on_click(250, 100, mouse.Button.left, False)
    time.sleep(0.05)
    assert len(win_callbacks) == 2
    assert win_callbacks[1][0] == "companion text win 2"





