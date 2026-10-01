"""通用全局热键划词监听器 (Hotkey Selection Listener)

支持多快捷键并行注册（如主热键 Alt+D 与自定义额外热键）。
在 Linux X11 下优先读取 Primary 选区（无延迟且不污染剪贴板），其他平台或空选区时自动执行剪贴板保护式提取。
"""

from __future__ import annotations
import threading
import time
from typing import Optional, Tuple, Callable, List
from pynput import keyboard, mouse
import pyperclip
from yanche.adapters.selection.base import BaseSelectionListener, SelectionCallback


class HotkeySelectionListener(BaseSelectionListener):
    """支持多热键绑定与高灵敏选区提取的热键取词器"""

    def __init__(
        self,
        callback: SelectionCallback,
        hotkey_str: str = "<alt>+d",
        extra_hotkeys: Optional[List[str]] = None,
        min_length: int = 1,
        max_length: int = 3000,
        on_empty_click: Optional[Callable[[Tuple[int, int]], None]] = None,
        get_x11_selection_fn: Optional[Callable[[], str]] = None,
    ) -> None:
        super().__init__(callback, min_length, max_length, on_empty_click=on_empty_click)
        self.hotkey_str = hotkey_str
        self.extra_hotkeys = extra_hotkeys or []
        self.get_x11_selection_fn = get_x11_selection_fn
        self._keyboard_controller = keyboard.Controller()
        self._mouse_controller = mouse.Controller()
        self._hotkey_listener: Optional[keyboard.GlobalHotKeys] = None

    def reset_last_selection(self) -> None:
        pass

    def _trigger_capture(self) -> None:
        """热键激活后的极速文本捕获流水线"""
        try:
            mx, my = self._mouse_controller.position
        except Exception:
            mx, my = 100, 100

        # 1. 优先尝试无感读取当前已划选的 Primary 选区（无需模拟按键，零剪贴板污染）
        if self.get_x11_selection_fn:
            try:
                x11_text = self.get_x11_selection_fn()
                sanitized_x11 = self.sanitize_text(x11_text)
                if sanitized_x11:
                    self.callback(sanitized_x11, (int(mx), int(my)))
                    return
            except Exception:
                pass

        # 2. 备用提取：模拟 Ctrl+C 并做剪贴板保护与恢复
        old_text = ""
        try:
            old_text = pyperclip.paste()
        except Exception:
            pass

        try:
            self._keyboard_controller.press(keyboard.Key.ctrl)
            self._keyboard_controller.press("c")
            self._keyboard_controller.release("c")
            self._keyboard_controller.release(keyboard.Key.ctrl)
        except Exception:
            pass

        time.sleep(0.12)

        new_text = ""
        try:
            new_text = pyperclip.paste()
        except Exception:
            pass

        # 恢复剪贴板原文本，避免污染用户私密剪贴历史
        def _restore_clipboard():
            time.sleep(0.5)
            try:
                if old_text and old_text != new_text:
                    pyperclip.copy(old_text)
            except Exception:
                pass

        threading.Thread(target=_restore_clipboard, daemon=True).start()

        sanitized = self.sanitize_text(new_text)
        if sanitized:
            self.callback(sanitized, (int(mx), int(my)))

    def _on_hotkey_activated(self) -> None:
        threading.Thread(target=self._trigger_capture, daemon=True).start()

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True

        all_keys = [self.hotkey_str] + self.extra_hotkeys
        hotkey_map = {}
        for hk in all_keys:
            cleaned = hk.strip()
            if cleaned:
                hotkey_map[cleaned] = self._on_hotkey_activated

        if not hotkey_map:
            return

        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self._hotkey_listener.start()
        except Exception as e:
            print(f"⚠️ 全局快捷键监听注册失败 ({hotkey_map.keys()}): {e}")

    def stop(self) -> None:
        self._is_running = False
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
