"""通用全局热键划词监听器 (Hotkey Selection Listener)

适用于 Windows 以及不支持 X11 Primary 选区的环境。
按下指定热键后，程序自动模拟复制、读取文本并保护恢复原剪贴板。
"""

from __future__ import annotations
import threading
import time
from typing import Optional, Tuple
from pynput import keyboard, mouse
import pyperclip
from quicktrans.adapters.selection.base import BaseSelectionListener, SelectionCallback


class HotkeySelectionListener(BaseSelectionListener):
    """基于全局热键与剪贴板保全机制的选词器"""

    def __init__(
        self,
        callback: SelectionCallback,
        hotkey_str: str = "<ctrl>+<alt>+t",
        min_length: int = 1,
        max_length: int = 3000,
    ) -> None:
        super().__init__(callback, min_length, max_length)
        self.hotkey_str = hotkey_str
        self._keyboard_controller = keyboard.Controller()
        self._mouse_controller = mouse.Controller()
        self._hotkey_listener: Optional[keyboard.GlobalHotKeys] = None

    def _trigger_copy_and_capture(self) -> None:
        """热键触发后的提取流水线"""
        # 1. 获取当前鼠标全局坐标
        try:
            mx, my = self._mouse_controller.position
        except Exception:
            mx, my = 100, 100

        # 2. 备份原剪贴板文本
        old_text = ""
        try:
            old_text = pyperclip.paste()
        except Exception:
            pass

        # 3. 模拟按键 Ctrl+C
        try:
            self._keyboard_controller.press(keyboard.Key.ctrl)
            self._keyboard_controller.press('c')
            self._keyboard_controller.release('c')
            self._keyboard_controller.release(keyboard.Key.ctrl)
        except Exception:
            pass

        # 4. 短暂休眠等待剪贴板同步
        time.sleep(0.12)

        # 5. 读取新剪贴板文本
        new_text = ""
        try:
            new_text = pyperclip.paste()
        except Exception:
            pass

        # 6. 延迟异步恢复原剪贴板（避免污染用户原先复制的私密数据）
        def _restore_clipboard():
            time.sleep(0.5)
            try:
                if old_text:
                    pyperclip.copy(old_text)
            except Exception:
                pass

        threading.Thread(target=_restore_clipboard, daemon=True).start()

        # 7. 文本清洗与分发
        sanitized = self.sanitize_text(new_text)
        if sanitized:
            self.callback(sanitized, (int(mx), int(my)))

    def _on_hotkey_activated(self) -> None:
        threading.Thread(target=self._trigger_copy_and_capture, daemon=True).start()

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True

        hotkey_map = {self.hotkey_str: self._on_hotkey_activated}
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self._hotkey_listener.start()
        except Exception as e:
            print(f"⚠️ 全局热键监听器启动失败: {e}")

    def stop(self) -> None:
        self._is_running = False
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
