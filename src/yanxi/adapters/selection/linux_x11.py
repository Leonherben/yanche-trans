"""Linux X11 原生划词监听器 (X11 Primary Selection Listener)

基于 Linux X11 桌面 Primary Selection 机制与鼠标左键/侧键释放事件。
支持模式 B（划选自动弹出开关）与鼠标侧键（X1/X2 前进后退键）一键极速取词。
"""

from __future__ import annotations
import math
import subprocess
import threading
import time
from typing import Optional, Tuple, Callable
from pynput import mouse
from yanxi.adapters.selection.base import BaseSelectionListener, SelectionCallback


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
        is_inside_popup: Optional[Callable[[Tuple[int, int]], bool]] = None,
        is_popup_visible: Optional[Callable[[], bool]] = None,
        auto_popup_only_when_visible: bool = True,
    ) -> None:
        super().__init__(
            callback,
            min_length,
            max_length,
            on_empty_click=on_empty_click,
            is_inside_popup=is_inside_popup,
            is_popup_visible=is_popup_visible,
            auto_popup_only_when_visible=auto_popup_only_when_visible,
        )
        self.debounce_ms = debounce_ms
        self.repeat_threshold_seconds = repeat_threshold_seconds
        self.auto_popup = auto_popup
        self.enable_mouse_side_button = enable_mouse_side_button
        self._last_selected_text: str = ""
        self._last_trigger_time: float = 0.0

        # 鼠标拖拽与双击手势识别
        self._press_pos: Optional[Tuple[int, int]] = None
        self._press_time: float = 0.0
        self._last_click_pos: Optional[Tuple[int, int]] = None
        self._last_click_time: float = 0.0
        self._click_count: int = 0

        self._mouse_controller = mouse.Controller()
        self._mouse_listener: Optional[mouse.Listener] = None
        self._stop_event = threading.Event()

    def on_popup_closed(self) -> None:
        """当浮窗被用户关闭/收起时进入冷却，避免点击关闭按钮的动作误触发选词"""
        super().on_popup_closed()
        self._press_pos = None

    def reset_last_selection(self) -> None:
        """重置选词记录与时间戳"""
        self._last_selected_text = ""
        self._last_trigger_time = 0.0
        self._press_pos = None

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
        """鼠标按键释放与点击事件派发（带拖选识别与悬浮窗坐标防误触）"""
        if not self._is_running:
            return

        # 1. 冷却保护期内（例如刚点击了关闭按钮），忽略一切鼠标事件
        if time.time() < self._close_cooldown_until:
            return

        # 2. 如果点击发生在悬浮窗自身内部（例如点击关闭 '✕' 或卡片按钮），绝对不触发选词或收起
        if self.is_inside_popup and self.is_inside_popup((int(x), int(y))):
            self._press_pos = None
            return

        # 3. 鼠标侧键 (X1 / X2 / 后退 / 前进) 零延迟取词翻译
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

        # 4. 鼠标左键按下与释放检测（区分真实划选/双击与普通单击）
        if button == mouse.Button.left:
            if pressed:
                self._press_pos = (int(x), int(y))
                self._press_time = time.time()
            else:
                # 释放事件
                now = time.time()
                press_x, press_y = self._press_pos if self._press_pos is not None else (int(x), int(y))
                self._press_pos = None

                drag_distance = math.hypot(x - press_x, y - press_y)

                # 双击检测 (400ms 内且距离小于 8px)
                is_double_click = False
                if (
                    self._last_click_pos is not None
                    and (now - self._last_click_time) < 0.45
                    and math.hypot(x - self._last_click_pos[0], y - self._last_click_pos[1]) < 8
                ):
                    self._click_count += 1
                    if self._click_count >= 2:
                        is_double_click = True
                else:
                    self._click_count = 1

                self._last_click_pos = (int(x), int(y))
                self._last_click_time = now

                is_drag_selection = (drag_distance >= 6)

                if is_drag_selection or is_double_click:
                    # 确认为真实划词手势（拖拽或双击单词）
                    if self.auto_popup:
                        # 伴随阅读模式：仅在浮窗可见时才自动划词翻译
                        if self.auto_popup_only_when_visible and self.is_popup_visible and not self.is_popup_visible():
                            return
                        threading.Thread(
                            target=self._process_selection, args=(x, y, False), daemon=True
                        ).start()
                else:
                    # 普通单击空白处（非划词动作）：仅负责收起未钉住的悬浮窗，绝不误触划词
                    if self.on_empty_click:
                        self.on_empty_click((int(x), int(y)))

    def _process_selection(self, x: int, y: int, force: bool = False) -> None:
        """核心选词提取与消抖流程"""
        if not force and self.debounce_ms > 0:
            time.sleep(self.debounce_ms / 1000.0)
        if self._stop_event.is_set():
            return
        if time.time() < self._close_cooldown_until:
            return
        if self.is_inside_popup and self.is_inside_popup((int(x), int(y))):
            return
        if not force and self.auto_popup_only_when_visible and self.is_popup_visible and not self.is_popup_visible():
            return

        raw_text = self._get_primary_selection()
        sanitized = self.sanitize_text(raw_text)
        now = time.time()

        if not force and not self.auto_popup:
            if not sanitized and self.on_empty_click:
                self.on_empty_click((int(x), int(y)))
            return

        if sanitized:
            # 文本变更、侧键主动强制、或同词二次划选
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
