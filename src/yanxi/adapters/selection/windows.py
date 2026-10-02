"""Windows 原生划词与鼠标手势监听器 (Windows Selection Listener)

基于 Windows 鼠标低级钩子 (Low-Level Mouse Hook) 与智能剪贴板保护提取机制。
支持划选松开自动翻译 (模式 B)、鼠标侧键 (X1/X2) 零延迟取词与空白点击智能收起。
"""

from __future__ import annotations
import math
import sys
import threading
import time
from typing import Callable, Optional, Tuple
from pynput import keyboard, mouse
import pyperclip

from yanxi.adapters.selection.base import BaseSelectionListener, SelectionCallback


class WindowsSelectionListener(BaseSelectionListener):
    """Windows 平台高精度划词与鼠标手势监听器"""

    def __init__(
        self,
        callback: SelectionCallback,
        min_length: int = 1,
        max_length: int = 3000,
        debounce_ms: int = 150,
        repeat_threshold_seconds: float = 1.2,
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
        self._last_right_click_time: float = 0.0
        self._cancel_selection_flag = threading.Event()

        # 手势识别追踪
        self._press_pos: Optional[Tuple[int, int]] = None
        self._press_time: float = 0.0
        self._last_click_pos: Optional[Tuple[int, int]] = None
        self._last_click_time: float = 0.0
        self._click_count: int = 0

        self._keyboard_controller = keyboard.Controller()
        self._mouse_listener: Optional[mouse.Listener] = None
        self._stop_event = threading.Event()

    @staticmethod
    def _is_context_menu_active() -> bool:
        """检查 Windows 系统当前是否正处于右键菜单/弹出菜单模式"""
        if sys.platform != "win32":
            return False
        try:
            import ctypes, ctypes.wintypes
            user32 = ctypes.windll.user32
            # 1. 检查是否存在系统菜单窗口 (Windows 内部类名 #32768)
            if user32.FindWindowW("#32768", None) != 0:
                return True
            # 2. 检查前台线程是否处于菜单模式 (GUI_POPUPMENUMODE = 0x10, GUI_INMENUMODE = 0x4)
            class GUITHREADINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.wintypes.DWORD),
                    ("flags", ctypes.wintypes.DWORD),
                    ("hwndActive", ctypes.wintypes.HWND),
                    ("hwndFocus", ctypes.wintypes.HWND),
                    ("hwndCapture", ctypes.wintypes.HWND),
                    ("hwndMenuOwner", ctypes.wintypes.HWND),
                    ("hwndMoveSize", ctypes.wintypes.HWND),
                    ("hwndCaret", ctypes.wintypes.HWND),
                    ("rcCaret", ctypes.wintypes.RECT),
                ]
            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if user32.GetGUIThreadInfo(0, ctypes.byref(gti)):
                if gti.flags & 0x14:
                    return True
        except Exception:
            pass
        return False

    def on_popup_closed(self) -> None:
        """当浮窗被用户关闭/收起时进入冷却，避免点击关闭按钮的动作误触发选词"""
        super().on_popup_closed()
        self._press_pos = None

    def reset_last_selection(self) -> None:
        """重置选词状态并激活关闭冷却"""
        self.on_popup_closed()

    def _release_modifier_keys(self) -> None:
        """若 Alt 被物理按住则显式释放，防止激活系统菜单栏；绝不随意释放 Ctrl/Shift 破坏用户复制与选区"""
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # VK_MENU (Alt) = 0x12
                if user32.GetAsyncKeyState(0x12) & 0x8000:
                    user32.keybd_event(0x12, 0, 0x0002, 0)
            except Exception:
                pass

    def _send_ctrl_c(self) -> None:
        """Windows 下发送标准的 Ctrl+C 复制按键序列，智能感知物理按键状态并彻底杜绝按键粘连"""
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                # 若鼠标右键正被按住，或系统正处于右键菜单中，或最近触发了右键，绝不发送按键破坏菜单
                if (
                    (user32.GetAsyncKeyState(0x02) & 0x8000)
                    or (time.time() - self._last_right_click_time < 0.8)
                    or self._cancel_selection_flag.is_set()
                    or self._is_context_menu_active()
                ):
                    return

                vk_ctrl = 0x11
                vk_c = 0x43
                scan_ctrl = user32.MapVirtualKeyW(vk_ctrl, 0)
                scan_c = user32.MapVirtualKeyW(vk_c, 0)

                user32.keybd_event(vk_ctrl, scan_ctrl, 0, 0)
                user32.keybd_event(vk_c, scan_c, 0, 0)
                time.sleep(0.01)
                user32.keybd_event(vk_c, scan_c, 0x0002, 0)
                user32.keybd_event(vk_ctrl, scan_ctrl, 0x0002, 0)
                return
            except Exception:
                pass

        try:
            self._keyboard_controller.press(keyboard.Key.ctrl)
            self._keyboard_controller.press("c")
            self._keyboard_controller.release("c")
            self._keyboard_controller.release(keyboard.Key.ctrl)
        except Exception:
            pass

    def _capture_selected_text_via_clipboard(self) -> str:
        """通过剪贴板高效捕获当前选中文本，绝不回写覆盖用户的剪贴板"""
        if (
            self._cancel_selection_flag.is_set()
            or (time.time() - self._last_right_click_time < 0.8)
            or self._is_context_menu_active()
        ):
            return ""

        old_text = ""
        try:
            old_text = pyperclip.paste()
        except Exception:
            pass

        if (
            self._cancel_selection_flag.is_set()
            or (time.time() - self._last_right_click_time < 0.8)
            or self._is_context_menu_active()
        ):
            return ""

        self._release_modifier_keys()
        time.sleep(0.015)

        if (
            self._cancel_selection_flag.is_set()
            or (time.time() - self._last_right_click_time < 0.8)
            or self._is_context_menu_active()
        ):
            return ""

        self._send_ctrl_c()

        # 动态轮询等待剪贴板刷新 (最多 180ms)
        new_text = ""
        for _ in range(6):
            if (
                self._cancel_selection_flag.is_set()
                or (time.time() - self._last_right_click_time < 0.8)
            ):
                return ""
            time.sleep(0.03)
            try:
                curr = pyperclip.paste()
                if curr and curr != old_text:
                    new_text = curr
                    break
            except Exception:
                pass
        else:
            try:
                new_text = pyperclip.paste()
            except Exception:
                new_text = ""

        return new_text

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """处理鼠标点击与释放事件"""
        if not self._is_running:
            return

        # 0. 鼠标右键：最高优先级拦截！无论任何状态，右键发生时立即记录时间戳并打断提取流程
        if button == mouse.Button.right:
            self._last_right_click_time = time.time()
            self._cancel_selection_flag.set()
            return

        # 1. 冷却保护期内（例如刚关闭了窗口），不响应
        if time.time() < self._close_cooldown_until:
            return

        # 2. 如果点击落在悬浮窗内部，属于浮窗自身交互，不触发划词
        if self.is_inside_popup and self.is_inside_popup((int(x), int(y))):
            self._press_pos = None
            return

        # 3. 鼠标侧键 (X1 / X2 / 后退 / 前进) 零延迟取词
        side_buttons = {
            b for b in (
                getattr(mouse.Button, "x1", None),
                getattr(mouse.Button, "x2", None),
            ) if b is not None
        }
        is_side = button in side_buttons or str(button) in ("Button.x1", "Button.x2", "<x1>", "<x2>")
        if self.enable_mouse_side_button and is_side and not pressed:
            threading.Thread(
                target=self._process_selection, args=(x, y, True), daemon=True
            ).start()
            return

        # 4. 鼠标左键划选与双击手势
        if button == mouse.Button.left:
            if pressed:
                self._cancel_selection_flag.clear()
                self._press_pos = (int(x), int(y))
                self._press_time = time.time()
            else:
                now = time.time()
                press_x, press_y = self._press_pos if self._press_pos is not None else (int(x), int(y))
                self._press_pos = None

                drag_distance = math.hypot(x - press_x, y - press_y)

                # 双击检测 (400ms 内且坐标距离小于 8px)
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
                    # 若刚刚发生了右键点击或系统菜单处于激活状态，坚决不启动划词提取
                    if (
                        self._cancel_selection_flag.is_set()
                        or (now - self._last_right_click_time < 0.8)
                        or self._is_context_menu_active()
                    ):
                        return
                    if self.auto_popup:
                        # 伴随阅读模式：仅在浮窗可见时才自动划词翻译
                        if self.auto_popup_only_when_visible and self.is_popup_visible and not self.is_popup_visible():
                            return
                        threading.Thread(
                            target=self._process_selection, args=(x, y, False), daemon=True
                        ).start()
                else:
                    # 单击空白处：若用户最近 1.5s 正在使用右键菜单或系统正处于右键菜单中，绝不收起
                    if (now - self._last_right_click_time >= 1.5) and not self._is_context_menu_active():
                        if self.on_empty_click:
                            self.on_empty_click((int(x), int(y)))

    def _process_selection(self, x: int, y: int, force: bool = False) -> None:
        """执行选词提取流水线"""
        # 1. 渐进式防抖轮询：一旦用户在防抖期内按下右键，立即退出，零按键干扰
        if not force and self.debounce_ms > 0:
            steps = max(1, int(self.debounce_ms / 20))
            for _ in range(steps):
                if (
                    self._stop_event.is_set()
                    or self._cancel_selection_flag.is_set()
                    or (time.time() - self._last_right_click_time < 0.8)
                    or self._is_context_menu_active()
                ):
                    return
                time.sleep(0.02)

        if (
            self._stop_event.is_set()
            or self._cancel_selection_flag.is_set()
            or (time.time() - self._last_right_click_time < 0.8)
            or self._is_context_menu_active()
        ):
            return
        if time.time() < self._close_cooldown_until:
            return
        if self.is_inside_popup and self.is_inside_popup((int(x), int(y))):
            return
        if not force and self.auto_popup_only_when_visible and self.is_popup_visible and not self.is_popup_visible():
            return

        # 2. 检查右键操作与系统右键菜单状态
        if not force:
            if (time.time() - self._last_right_click_time < 0.8) or self._is_context_menu_active():
                return
            if sys.platform == "win32":
                try:
                    import ctypes
                    if ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000:
                        return
                except Exception:
                    pass

        raw_text = self._capture_selected_text_via_clipboard()
        if (
            self._cancel_selection_flag.is_set()
            or (time.time() - self._last_right_click_time < 0.8)
            or self._is_context_menu_active()
        ):
            return

        sanitized = self.sanitize_text(raw_text)
        now = time.time()

        if not force and not self.auto_popup:
            if not sanitized and self.on_empty_click:
                self.on_empty_click((int(x), int(y)))
            return

        if sanitized:
            if (
                force
                or sanitized != self._last_selected_text
                or (now - self._last_trigger_time) >= self.repeat_threshold_seconds
            ):
                if not force and (
                    self._cancel_selection_flag.is_set()
                    or (time.time() - self._last_right_click_time < 0.8)
                    or self._is_context_menu_active()
                ):
                    return
                self._last_selected_text = sanitized
                self._last_trigger_time = now
                self.callback(sanitized, (int(x), int(y)))


    def start(self) -> None:
        """启动 Windows 鼠标监听器"""
        if self._is_running:
            return
        self._is_running = True
        self._stop_event.clear()
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()

    def stop(self) -> None:
        """停止监听器"""
        self._is_running = False
        self._stop_event.set()
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None
