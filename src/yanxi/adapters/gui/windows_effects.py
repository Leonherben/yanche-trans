"""Windows 原生亚克力与毛玻璃视觉效果适配器 (Windows Acrylic & Blur Effects)

基于 Windows DWM API 与 SetWindowCompositionAttribute 实现：
- Windows 11 (Build 22000+): 原生 DWM Acrylic (系统级亚克力半透明模糊)
- Windows 10: 原生 Accent Blur / Acrylic 磨砂模糊
提供安全调用与全平台平滑兜底。
"""

from __future__ import annotations
import ctypes
import sys
from typing import Optional


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId", ctypes.c_int),
    ]


class _WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


ACCENT_DISABLED = 0
ACCENT_ENABLE_GRADIENT = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

WCA_ACCENT_POLICY = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38

# DWMWA_SYSTEMBACKDROP_TYPE options (Win11 22H2+)
BACKDROP_AUTO = 0
BACKDROP_NONE = 1
BACKDROP_MAINWINDOW_MICA = 2
BACKDROP_TRANSIENT_ACRYLIC = 3
BACKDROP_TABBED_MICA_ALT = 4


def is_windows() -> bool:
    return sys.platform == "win32"


def get_windows_build() -> int:
    if not is_windows():
        return 0
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def set_dark_title_bar(hwnd: int, dark: bool = True) -> bool:
    """在 Windows 10/11 上设置暗色窗口标题栏/DWM 偏好"""
    if not is_windows():
        return False
    try:
        dwmapi = ctypes.windll.dwmapi
        val = ctypes.c_int(1 if dark else 0)
        # Windows 10 1809+ / Windows 11
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val),
            ctypes.sizeof(val),
        )
        return True
    except Exception:
        return False


def enable_blur_behind(hwnd: int, dark: bool = True) -> bool:
    """在指定窗口上启用系统级毛玻璃/亚克力模糊效果"""
    if not is_windows():
        return False

    build = get_windows_build()

    # 1. Windows 11 (Build 22000+)：优先使用官方 DWM System Backdrop (Acrylic)
    if build >= 22000:
        try:
            dwmapi = ctypes.windll.dwmapi
            set_dark_title_bar(hwnd, dark)
            backdrop = ctypes.c_int(BACKDROP_TRANSIENT_ACRYLIC)
            res = dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(backdrop),
                ctypes.sizeof(backdrop),
            )
            if res == 0:
                return True
        except Exception:
            pass

    # Windows 10 及以下版本不使用不稳定的 SetWindowCompositionAttribute（避免产生黑色矩形杂色与渲染伪影）
    return False


def disable_blur_behind(hwnd: int) -> bool:
    """禁用系统级模糊效果，恢复常规渲染"""
    if not is_windows():
        return False

    build = get_windows_build()
    if build >= 22000:
        try:
            dwmapi = ctypes.windll.dwmapi
            backdrop = ctypes.c_int(BACKDROP_NONE)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(backdrop),
                ctypes.sizeof(backdrop),
            )
        except Exception:
            pass

    try:
        user32 = ctypes.windll.user32
        set_window_composition_attribute = getattr(user32, "SetWindowCompositionAttribute", None)
        if set_window_composition_attribute:
            policy = _ACCENT_POLICY()
            policy.AccentState = ACCENT_DISABLED
            policy.AccentFlags = 0
            policy.GradientColor = 0
            policy.AnimationId = 0

            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p)
            data.SizeOfData = ctypes.sizeof(policy)

            set_window_composition_attribute(hwnd, ctypes.byref(data))
            return True
    except Exception:
        pass

    return False
