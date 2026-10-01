"""Linux X11 原生划词监听器 (X11 Primary Selection Listener)

基于 Linux X11 桌面 Primary Selection 机制与鼠标左键释放事件（ButtonRelease）。
在任何窗口（终端、浏览器、编辑器）中划词松开鼠标即可无感触发，完全不污染剪贴板。
"""

from __future__ import annotations
import subprocess
import threading
import time
from typing import Optional, Tuple
from pynput import mouse
from yanche.adapters.selection.base import BaseSelectionListener, SelectionCallback


class LinuxX11SelectionListener(BaseSelectionListener):
    """基于鼠标释放与 X11 Primary Selection 的零侵入取词器"""

    def __init__(
        self,
        callback: SelectionCallback,
        min_length: int = 1,
        max_length: int = 3000,
        debounce_ms: int = 200,
    ) -> None:
        super().__init__(callback, min_length, max_length)
        self.debounce_ms = debounce_ms
        self._last_selected_text: str = ""
        self._mouse_controller = mouse.Controller()
        self._mouse_listener: Optional[mouse.Listener] = None
        self._stop_event = threading.Event()

    def _get_primary_selection(self) -> str:
        """从 X11 Primary 剪贴板获取选中文本"""
        try:
            # 优先使用 xsel -o (快速且非阻塞)
            res = subprocess.run(
                ["xsel", "-o"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=0.3,
            )
            return res.stdout
        except Exception:
            try:
                # 备用方案：xclip -o
                res = subprocess.run(
                    ["xclip", "-o"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=0.3,
                )
                return res.stdout
            except Exception:
                return ""

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """鼠标松开时触发选词判定"""
        if not self._is_running:
            return

        # 仅在鼠标左键松开时检测划词
        if button == mouse.Button.left and not pressed:
            # 异步启动消抖检测线程，避免阻塞输入钩子
            threading.Thread(target=self._process_selection, args=(x, y), daemon=True).start()

    def _process_selection(self, x: int, y: int) -> None:
        # 短暂消抖等待 X11 选区更新
        time.sleep(self.debounce_ms / 1000.0)
        if self._stop_event.is_set():
            return

        raw_text = self._get_primary_selection()
        sanitized = self.sanitize_text(raw_text)

        if sanitized and sanitized != self._last_selected_text:
            self._last_selected_text = sanitized
            # 触发业务回调
            self.callback(sanitized, (int(x), int(y)))

    def start(self) -> None:
        """启动监听器"""
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()

        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()

    def stop(self) -> None:
        """安全停止监听器"""
        self._is_running = False
        self._stop_event.set()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None
