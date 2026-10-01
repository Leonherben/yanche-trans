"""言蹊翻译 桌面划词翻译主服务 (System Daemon & Entrypoint)

整合系统托盘、无焦点悬浮窗、X11/热键选词监听器与 Panic Failsafe 逃生通道。
"""

from __future__ import annotations
import os
import sys

def ensure_xcb_cursor_loaded() -> None:
    """Linux 平台下若缺少 libxcb-cursor0 则自动从 ~/.local/lib 加载并自愈重启"""
    if getattr(sys, "frozen", False):
        return
    if sys.platform.startswith("linux"):
        _user_lib = os.path.expanduser("~/.local/lib")
        if os.path.exists(os.path.join(_user_lib, "libxcb-cursor.so.0")):
            _ld = os.environ.get("LD_LIBRARY_PATH", "")
            if _user_lib not in _ld.split(":"):
                os.environ["LD_LIBRARY_PATH"] = f"{_user_lib}:{_ld}" if _ld else _user_lib
                if not os.environ.get("_YANCHE_RESTARTED"):
                    os.environ["_YANCHE_RESTARTED"] = "1"
                    os.execv(sys.executable, [sys.executable] + sys.argv)

import atexit
import signal
import threading
from typing import Optional, Tuple
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication
from pynput import keyboard

from yanche.core.config import AppConfig
from yanche.core.models import TranslationRequest, TranslationResult
from yanche.core.translator.factory import create_translator
from yanche.core.cache.sqlite_cache import SQLiteCache
from yanche.adapters.gui.popup import PopupBubble
from yanche.adapters.gui.tray import 言蹊翻译Tray, 言澈翻译Tray
from yanche.adapters.selection.base import BaseSelectionListener
from yanche.adapters.selection.linux_x11 import LinuxX11SelectionListener
from yanche.adapters.selection.hotkey_fallback import HotkeySelectionListener


class 言蹊翻译App(QObject):
    """主调度控制器"""

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self.qapp = qapp
        self.config = AppConfig.load()
        self.cache = SQLiteCache()

        # 核心翻译引擎
        self.active_provider_cfg = self.config.get_active_provider()
        self.translator = create_translator(self.active_provider_cfg)

        # 悬浮窗与托盘
        self.popup = PopupBubble(
            config=self.config.ui,
            selection_config=self.config.selection,
            on_retranslate=self.retranslate_text,
            on_switch_provider=self.switch_provider_and_retranslate,
            on_save_config=self.config.save,
            on_clear_cache=self.cache.clear,
            on_update_selection_config=self._reload_listeners,
            available_providers=list(self.config.providers.keys()),
            default_provider=self.config.default_provider,
        )
        self.popup.closed.connect(self._on_popup_closed)
        self.tray = 言蹊翻译Tray(
            config=self.config,
            on_open_input=lambda: QTimer.singleShot(0, self.popup.open_for_input),
            on_toggle_listener=self.set_listener_enabled,
            on_provider_change=self.set_provider,
            on_target_lang_change=self.set_target_lang,
            on_theme_change=lambda t: self.popup.apply_theme(theme_name=t),
            on_opacity_change=lambda o: self.popup.apply_theme(opacity=o),
            on_toggle_auto_popup=self._on_toggle_auto_popup,
            on_clear_cache=self.cache.clear,
            on_quit=self.shutdown,
        )

        # 选词监听器集合
        self.listeners: list[BaseSelectionListener] = []
        self._panic_listener: Optional[keyboard.GlobalHotKeys] = None

        self._init_listeners()
        self._init_panic_failsafe()

        # 系统退出钩子
        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, lambda sig, frame: self.shutdown())
        signal.signal(signal.SIGTERM, lambda sig, frame: self.shutdown())

    def _on_toggle_auto_popup(self, enabled: bool) -> None:
        self.config.selection.auto_popup_on_selection = enabled
        self.config.save()
        self._reload_listeners()

    def _reload_listeners(self) -> None:
        """当用户在设置中更改快捷键或模式 B 触发方式时热重载监听器"""
        for listener in self.listeners:
            listener.stop()
        self.listeners.clear()
        self._init_listeners()

    def _on_popup_closed(self) -> None:
        """当浮窗隐藏时重置选词记录，以便用户能再次划选相同单词"""
        for listener in self.listeners:
            listener.reset_last_selection()

    def on_empty_click(self, cursor_pos: Tuple[int, int]) -> None:
        """用户在空白处点击（未产生划词）时，若浮窗处于显示状态且未钉住则自动收起"""
        x, y = cursor_pos
        self.popup.dismiss_signal.emit(x, y)

    def _init_listeners(self) -> None:
        """根据当前系统环境自适应加载取词器"""
        x11_listener = None
        # Linux X11 Primary 监听 (负责选区检测、模式 B 自动弹窗及鼠标侧键取词)
        if sys.platform.startswith("linux") and self.config.selection.enable_x11_primary:
            x11_listener = LinuxX11SelectionListener(
                callback=self.on_text_selected,
                min_length=self.config.selection.min_length,
                max_length=self.config.selection.max_length,
                debounce_ms=self.config.selection.debounce_ms,
                auto_popup=self.config.selection.auto_popup_on_selection,
                enable_mouse_side_button=self.config.selection.enable_mouse_side_button,
                on_empty_click=self.on_empty_click,
            )
            self.listeners.append(x11_listener)

        # 全局热键监听器 (Alt+D 及其他多快捷键)
        if self.config.selection.hotkey:
            hotkey_listener = HotkeySelectionListener(
                callback=self.on_text_selected,
                hotkey_str=self.config.selection.hotkey,
                extra_hotkeys=self.config.selection.extra_hotkeys,
                min_length=self.config.selection.min_length,
                max_length=self.config.selection.max_length,
                on_empty_click=self.on_empty_click,
                get_x11_selection_fn=x11_listener.get_current_selection if x11_listener else None,
                on_no_selection=lambda: QTimer.singleShot(0, self.popup.open_for_input),
            )
            self.listeners.append(hotkey_listener)

        # 启动所有选词监听器
        for listener in self.listeners:
            listener.start()

    def _init_panic_failsafe(self) -> None:
        """紧急逃生机制：按键无条件强制退出程序，解除所有系统拦截"""
        panic_key = self.config.selection.panic_hotkey
        if not panic_key:
            return

        def _emergency_exit():
            print("\n🚨 [Panic Failsafe] 捕获到紧急逃生按键，立即终止程序！")
            self.shutdown()

        try:
            self._panic_listener = keyboard.GlobalHotKeys({panic_key: _emergency_exit})
            self._panic_listener.start()
        except Exception as e:
            print(f"⚠️ Panic 逃生热键注册失败: {e}")

    def on_text_selected(self, text: str, cursor_pos: Tuple[int, int]) -> None:
        """当捕获到划词文本时的核心调度"""
        x, y = cursor_pos
        # 1. 主线程更新 UI 显示 Loading
        self.popup.show_loading_signal.emit(text, x, y)

        # 2. 异步执行查缓存或网络请求
        threading.Thread(target=self._async_translate_pipeline, args=(text,), daemon=True).start()

    def _async_translate_pipeline(self, text: str) -> None:
        src = self.config.default_source_lang
        tgt = self.config.default_target_lang
        provider_name = self.active_provider_cfg.name

        # 1. 尝试缓存
        if self.config.enable_cache:
            cached = self.cache.get(text, src, tgt, provider_name)
            if cached:
                self.popup.show_translation_signal.emit(cached)
                return

        # 2. 调用 API
        req = TranslationRequest(text=text, source_lang=src, target_lang=tgt)
        result = self.translator.translate(req)

        # 3. 写入缓存
        if result.is_success() and self.config.enable_cache:
            self.cache.put(result)

        # 4. 发送信号渲染
        self.popup.show_translation_signal.emit(result)

    def set_listener_enabled(self, enabled: bool) -> None:
        for listener in self.listeners:
            if enabled:
                listener.start()
            else:
                listener.stop()

    def set_provider(self, provider_name: str) -> None:
        self.config.default_provider = provider_name
        self.config.save()
        self.active_provider_cfg = self.config.get_active_provider()
        self.translator = create_translator(self.active_provider_cfg)
        self.tray.update_active_provider(provider_name)
        self.popup.set_active_provider(provider_name)

    def retranslate_text(self, text: str) -> None:
        """从浮窗手动编辑或即时查词触发就地重新翻译"""
        if not text:
            return
        self.popup.display_loading(text, self.popup.x(), self.popup.y())
        threading.Thread(target=self._async_translate_pipeline, args=(text,), daemon=True).start()

    def switch_provider_and_retranslate(self, provider_name: str, text: str) -> None:
        """从浮窗直接切换模型并就地重新翻译"""
        self.set_provider(provider_name)
        if text:
            # 立即在当前浮窗位置展示 loading 并异步请求新结果
            self.popup.display_loading(text, self.popup.x(), self.popup.y())
            threading.Thread(target=self._async_translate_pipeline, args=(text,), daemon=True).start()

    def set_target_lang(self, lang_code: str) -> None:
        self.config.default_target_lang = lang_code
        self.config.save()

    def shutdown(self) -> None:
        """安全释放所有资源"""
        for listener in self.listeners:
            listener.stop()
        if self._panic_listener:
            try:
                self._panic_listener.stop()
            except Exception:
                pass
            self._panic_listener = None
        self.popup.close()
        self.tray.hide()
        self.qapp.quit()


言澈翻译App = 言蹊翻译App
YanQiApp = 言蹊翻译App
YanCheApp = 言蹊翻译App


def main() -> None:
    ensure_xcb_cursor_loaded()
    # 强制无头或者有桌面环境支持
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 保持后台常驻

    controller = 言蹊翻译App(app)
    controller.tray.show()

    print(f"✨ 言蹊翻译 划词翻译已就绪！")
    print(f"   • 当前默认 Provider: {controller.config.default_provider}")
    print(f"   • 目标语言: {controller.config.default_target_lang}")
    print(f"   • 紧急逃生键: {controller.config.selection.panic_hotkey}")
    print(f"   • 选词热键: {controller.config.selection.hotkey}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
