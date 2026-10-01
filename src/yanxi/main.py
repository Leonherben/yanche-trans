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
                if not os.environ.get("_YANXI_RESTARTED"):
                    os.environ["_YANXI_RESTARTED"] = "1"
                    os.execv(sys.executable, [sys.executable] + sys.argv)

import atexit
import signal
import threading
from typing import Optional, Tuple
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from pynput import keyboard

from yanxi.core.config import AppConfig
from yanxi.core.models import TranslationRequest, TranslationResult
from yanxi.core.translator.factory import create_translator
from yanxi.core.cache.sqlite_cache import SQLiteCache
from yanxi.core.single_instance import SingleInstance
from yanxi.core.updater import check_github_update, UpdateInfo
from yanxi.adapters.gui.popup import PopupBubble
from yanxi.adapters.gui.tray import 言蹊翻译Tray
from yanxi.adapters.gui.settings_dialog import SettingsDialog
from yanxi.adapters.gui.icon_helper import get_app_icon, configure_windows_app_id
from yanxi.adapters.selection.base import BaseSelectionListener
from yanxi.adapters.selection.linux_x11 import LinuxX11SelectionListener
from yanxi.adapters.selection.windows import WindowsSelectionListener
from yanxi.adapters.selection.hotkey_fallback import HotkeySelectionListener


class 言蹊翻译App(QObject):
    """主调度控制器"""

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self.qapp = qapp
        self.config = AppConfig.load()
        self.cache = SQLiteCache()
        self._settings_dialog: Optional[SettingsDialog] = None

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
            on_open_settings=self.open_settings,
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
            on_open_settings=self.open_settings,
            on_check_update=self.open_update_dialog,
            on_quit=self.shutdown,
        )

        # 选词监听器集合
        self.listeners: list[BaseSelectionListener] = []
        self._panic_listener: Optional[keyboard.GlobalHotKeys] = None

        self._init_listeners()
        self._init_panic_failsafe()

        # 启动时自动打开悬浮窗 (满足用户“打开应用就打开悬浮窗”的需求)
        if getattr(self.config.ui, "open_on_startup", True):
            QTimer.singleShot(150, self.popup.open_for_input)

        # 静默后台检查更新（启动 3 秒后执行，避免阻塞冷启动）
        if getattr(self.config, "update", None) and self.config.update.auto_check_update:
            QTimer.singleShot(3000, self._check_update_silently)

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
        """当浮窗隐藏或关闭时通知所有监听器进入冷却期，防止关闭动作误触划词"""
        for listener in self.listeners:
            listener.on_popup_closed()

    def is_inside_popup(self, cursor_pos: Tuple[int, int]) -> bool:
        """检查鼠标坐标是否落在当前显示的悬浮窗之内（含适度感应边缘扩充）"""
        if not self.popup.isVisible():
            return False
        x, y = cursor_pos
        # 扩展 4px 感应边距，避免用户点在边框或阴影边缘误判为外部
        geom = self.popup.frameGeometry().adjusted(-4, -4, 4, 4)
        return geom.contains(x, y)

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
                is_inside_popup=self.is_inside_popup,
            )
            self.listeners.append(x11_listener)

        # Windows 原生划词与鼠标手势监听 (模式 B 划选自动弹窗、鼠标侧键及空白点击收起)
        elif sys.platform == "win32":
            win_listener = WindowsSelectionListener(
                callback=self.on_text_selected,
                min_length=self.config.selection.min_length,
                max_length=self.config.selection.max_length,
                debounce_ms=self.config.selection.debounce_ms,
                auto_popup=self.config.selection.auto_popup_on_selection,
                enable_mouse_side_button=self.config.selection.enable_mouse_side_button,
                on_empty_click=self.on_empty_click,
                is_inside_popup=self.is_inside_popup,
            )
            self.listeners.append(win_listener)

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

    def open_settings(self) -> None:
        """打开偏好设置中心（支持 API、模型、快捷键、主题等可视化配置）"""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                config=self.config,
                on_save=self.on_settings_saved,
            )
            self._settings_dialog.finished.connect(self._on_settings_closed)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_settings_closed(self, result: int) -> None:
        self._settings_dialog = None

    def open_update_dialog(self) -> None:
        """打开偏好设置中心并定位到更新选项卡自动检查更新"""
        self.open_settings()
        if self._settings_dialog:
            self._settings_dialog.trigger_check_update()

    def _check_update_silently(self) -> None:
        """后台静默检测更新，若发现新版本则通过托盘通知"""
        def _worker():
            try:
                info = check_github_update()
                if info.has_update and info.latest_version:
                    QTimer.singleShot(0, lambda: self._notify_new_version(info))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _notify_new_version(self, info: UpdateInfo) -> None:
        try:
            self.tray.showMessage(
                "言蹊翻译 发现新版本",
                f"已检测到新版本 v{info.latest_version}，点击托盘菜单【检查更新】即可升级！",
                QSystemTrayIcon.MessageIcon.Information,
                6000,
            )
        except Exception:
            pass


    def on_settings_saved(self, new_config: AppConfig) -> None:
        """设置保存后的热重载"""
        self.config = new_config
        self.active_provider_cfg = self.config.get_active_provider()
        self.translator = create_translator(self.active_provider_cfg)

        # 同步托盘与浮窗的提供商列表与选中状态
        self.tray.update_active_provider(self.config.default_provider)
        self.popup.available_providers = list(self.config.providers.keys())
        self.popup.set_active_provider(self.config.default_provider)

        # 同步主题与透明度
        self.popup.apply_theme(
            theme_name=self.config.ui.theme,
            opacity=self.config.ui.window_opacity,
        )

        # 重新加载热键与选词监听器
        self._reload_listeners()

    def on_external_wakeup(self) -> None:
        """当外部尝试二次启动本程序时，由单实例监听服务触发唤醒"""
        # 1. 弹出浮窗并切到直接输入模式
        QTimer.singleShot(0, self.popup.open_for_input)
        # 2. 托盘气泡提示
        try:
            self.tray.showMessage(
                "言蹊翻译 已在后台运行",
                "快捷键: Alt + D | 划选文字即可极速翻译",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
        except Exception:
            pass

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


YanXiApp = 言蹊翻译App


def configure_system_font(app: QApplication) -> None:
    """为全系统所有窗口与弹窗控件设置现代标准 UI 字体"""
    font = app.font()
    if sys.platform == "win32":
        font.setFamily("Microsoft YaHei UI")
        font.setPointSize(9)
    elif sys.platform.startswith("linux"):
        font.setFamily("Noto Sans CJK SC")
        font.setPointSize(10)
    elif sys.platform == "darwin":
        font.setFamily("PingFang SC")
        font.setPointSize(12)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)


def main() -> None:
    ensure_xcb_cursor_loaded()
    configure_windows_app_id()
    # 强制无头或者有桌面环境支持
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 保持后台常驻
    app.setWindowIcon(get_app_icon())
    configure_system_font(app)

    # 跨平台单实例保护：检测是否已有多开
    instance_guard = SingleInstance("yanxi_desktop_app")
    if instance_guard.is_already_running():
        print("💡 [SingleInstance] 检测到言蹊翻译已在后台运行中，已通知已有实例唤醒，本进程直接退出。")
        sys.exit(0)

    if not instance_guard.start_listen():
        print("⚠️ [SingleInstance] 警告: 本地单实例监听启动失败，将以单机模式运行。")

    controller = 言蹊翻译App(app)
    instance_guard.wakeup_received.connect(controller.on_external_wakeup)
    # 保留对 instance_guard 的引用，避免垃圾回收
    controller._instance_guard = instance_guard
    controller.tray.show()

    print(f"✨ 言蹊翻译 划词翻译已就绪！")
    print(f"   • 当前默认 Provider: {controller.config.default_provider}")
    print(f"   • 目标语言: {controller.config.default_target_lang}")
    print(f"   • 紧急逃生键: {controller.config.selection.panic_hotkey}")
    print(f"   • 选词热键: {controller.config.selection.hotkey}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
