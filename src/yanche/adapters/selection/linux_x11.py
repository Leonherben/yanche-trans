"""Linux X11 原生划词监听器 (X11 Primary Selection Listener)

基于 Linux X11 桌面 Primary Selection 机制与鼠标左键/侧键释放事件。
支持模式 B（划选自动弹出开关）与鼠标侧键（X1/X2 前进后退键）一键极速取词。
"""

from __future__ import annotations
import subprocess
import threading
import time
from typing import Optional, Tuple, Callable
from pynput import mouse
from yanche.adapters.selection.base import BaseSelectionListener, SelectionCallback


class LinuxX11SelectionListener(BaseSelectionListener):
    """基于鼠标释放、侧键与 X11 Primary Selection 的零侵入取词器"""

    def __init__(
        self,
        callback: SelectionCallback,
        min_length: int = 1,
        max_length: int = 3000,
        debounce_ms: int = 200,
        repeat_threshold_seconds: float = 1.5,
        auto_popup: bool = True,
        enable_mouse_side_button: bool = True,
        on_empty_click: Optional[Callable[[Tuple[int, int]], None]] = None,
    ) -> None:
        super().__init__(callback, min_length, max_length, on_empty_click=on_empty_click)
        self.debounce_ms = debounce_ms
        self.repeat_threshold_seconds = repeat_threshold_seconds
        self.auto_popup = auto_popup
        self.enable_mouse_side_button = enable_mouse_side_button
        self._last_selected_text: str = ""
        self._last_trigger_time: float = 0.0
        self._mouse_controller = mouse.Controller()
        self._mouse_listener: Optional[mouse.Listener] = None
        self._stop_event = threading.Event()


    def reset_last_selection(self) -> None:
        """重置上次选词记录与时间戳"""
        self._last_selected_text = ""
        self._last_trigger_time = 0.0

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

    def get_current_selection(self) -> str:
        """公开只读探测当前 X11 选中文本（供快捷键直接复用）"""
        raw = self._get_primary_selection()
        return self.sanitize_text(raw)

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """鼠标按键释放与点击事件派发"""
        if not self._is_running:
            return

        # 1. 鼠标侧键 (X1 / X2 / 后退 / 前进，X11 下对应 button8/button9) 零延迟取词翻译
        side_buttons = {
            b for b in (
                getattr(mouse.Button, "x1", None),
                getattr(mouse.Button, "x2", None),
                getattr(mouse.Button, "button8", None),
                getattr(mouse.Button, "button9", None),
            ) if b is not None
        }
        is_side = button in side_buttons or str(button) in (
            "Button.x1",
            "Button.x2",
            "Button.button8",
            "Button.button9",
            "<8>",
            "<9>",
        )
        if self.enable_mouse_side_button and is_side and not pressed:
            threading.Thread(
                target=self._process_selection, args=(x, y, True), daemon=True
            ).start()
            return

        # 2. 鼠标左键释放事件
        if button == mouse.Button.left and not pressed:
            if self.auto_popup:
                # 模式 B 开启：划选松开自动翻译
                threading.Thread(
                    target=self._process_selection, args=(x, y, False), daemon=True
                ).start()
            else:
                # 模式 B 关闭：仅在普通单击空白处时触发收起检测，不自动弹窗
                threading.Thread(
                    target=self._process_empty_click_only, args=(x, y), daemon=True
                ).start()

    def _process_empty_click_only(self, x: int, y: int) -> None:
        """在关闭自动划词时，仅检测普通单击以便收起浮窗"""
        if self.debounce_ms > 0:
            time.sleep(self.debounce_ms / 1000.0)
        if self._stop_event.is_set():
            return
        raw_text = self._get_primary_selection()
        sanitized = self.sanitize_text(raw_text)
        if not sanitized and self.on_empty_click:
            self.on_empty_click((int(x), int(y)))

    def _process_selection(self, x: int, y: int, force: bool = False) -> None:
        """核心选词提取与消抖流程"""
        if not force and self.debounce_ms > 0:
            time.sleep(self.debounce_ms / 1000.0)
        if self._stop_event.is_set():
            return


        if not force and not self.auto_popup:
            # 模式 B 关闭时，松开左键绝不主动弹窗
            raw_text = self._get_primary_selection()
            sanitized = self.sanitize_text(raw_text)
            if not sanitized and self.on_empty_click:
                self.on_empty_click((int(x), int(y)))
            return

        raw_text = self._get_primary_selection()
        sanitized = self.sanitize_text(raw_text)
        now = time.time()


        if sanitized:
            # 文本不同、超过重复判定时间、或是侧键主动强制触发
            if (
                force
                or sanitized != self._last_selected_text
                or (now - self._last_trigger_time) >= self.repeat_threshold_seconds
            ):
                self._last_selected_text = sanitized
                self._last_trigger_time = now
                self.callback(sanitized, (int(x), int(y)))
        else:
            if self.on_empty_click and not force:
                self.on_empty_click((int(x), int(y)))

    def start(self) -> None:
        """启动监听器"""
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()

        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()

    def stop(self) -> None:
        """安全停止监听"""
        self._is_running = False
        self._stop_event.set()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None
