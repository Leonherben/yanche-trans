"""桌面无焦点悬浮窗独立沙盒测试 (Isolated Sandbox GUI)

运行该沙盒可独立验证：
1. 浮窗弹出时，主测试输入框中的打字焦点是否保持不丢失（Focus Stealing Prevention）；
2. 浮窗阴影、样式排版、Markdown 多行换行、一键复制到剪贴板等交互体验。
"""

import os
import sys

def ensure_xcb_cursor_loaded() -> None:
    """Linux 平台下若缺少 libxcb-cursor0 则自动从 ~/.local/lib 加载并自愈重启"""
    if sys.platform.startswith("linux"):
        _user_lib = os.path.expanduser("~/.local/lib")
        if os.path.exists(os.path.join(_user_lib, "libxcb-cursor.so.0")):
            _ld = os.environ.get("LD_LIBRARY_PATH", "")
            if _user_lib not in _ld.split(":"):
                os.environ["LD_LIBRARY_PATH"] = f"{_user_lib}:{_ld}" if _ld else _user_lib
                if not os.environ.get("_YANCHE_RESTARTED"):
                    os.environ["_YANCHE_RESTARTED"] = "1"
                    os.execv(sys.executable, [sys.executable] + sys.argv)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
)
from PySide6.QtCore import Qt, QPoint
from yanche.core.config import UIConfig
from yanche.core.models import TranslationResult
from yanche.adapters.gui.popup import PopupBubble


class SandboxWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("言蹊翻译 GUI Sandbox (无焦点测试沙盒)")
        self.resize(500, 320)

        self.ui_config = UIConfig()
        self.popup = PopupBubble(self.ui_config)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)

        desc = QLabel(
            "<h3>🎯 防焦点窃取测试说明</h3>"
            "<p>1. 在下方的输入框中持续打字；<br>"
            "2. 点击下方测试按钮或按回车触发浮窗；<br>"
            "3. <b>观察焦点：</b>若光标仍停留在输入框且打字不中断，则防抢占机制生效！</p>",
            self
        )
        layout.addWidget(desc)

        self.text_input = QLineEdit(self)
        self.text_input.setPlaceholderText("请在此输入测试文字，如：Artificial Intelligence...")
        self.text_input.setText("Artificial Intelligence is reshaping software development.")
        self.text_input.returnPressed.connect(self._trigger_mock_popup)
        layout.addWidget(self.text_input)

        btn_bar = QHBoxLayout()
        test_btn = QPushButton("🚀 模拟划词弹出 (深色模式)", self)
        test_btn.clicked.connect(self._trigger_mock_popup)
        btn_bar.addWidget(test_btn)

        cache_btn = QPushButton("⚡ 模拟缓存命中", self)
        cache_btn.clicked.connect(self._trigger_mock_cache)
        btn_bar.addWidget(cache_btn)

        err_btn = QPushButton("⚠️ 模拟错误提示", self)
        err_btn.clicked.connect(self._trigger_mock_error)
        btn_bar.addWidget(err_btn)

        layout.addLayout(btn_bar)

        theme_bar = QHBoxLayout()
        theme_label = QLabel("🎨 主题快速切换:", self)
        theme_bar.addWidget(theme_label)

        for code, label in [("auto", "跟随系统"), ("dark", "🌙 深色"), ("light", "☀️ 浅色"), ("glass", "🪟 玻璃")]:
            btn = QPushButton(label, self)
            btn.clicked.connect(lambda checked, t=code: self.popup.apply_theme(theme_name=t))
            theme_bar.addWidget(btn)

        layout.addLayout(theme_bar)
        self.setCentralWidget(central)

    def _get_target_pos(self) -> tuple[int, int]:
        p = self.mapToGlobal(QPoint(50, 100))
        return p.x(), p.y()

    def _trigger_mock_popup(self) -> None:
        x, y = self._get_target_pos()
        self.popup.display_loading(self.text_input.text(), x, y)
        # 模拟 300ms 后 API 返回
        result = TranslationResult(
            original_text=self.text_input.text(),
            translated_text="**人工智能**正在重塑现代软件开发范式。\n\n- **核心特征**：代码自动补全与架构感知\n- **技术底座**：`Python 3.12` + `PySide6`\n- **音标参考**：/ˌɑːtɪˈfɪʃl ɪnˈtelɪdʒəns/",
            source_lang="en",
            target_lang="zh-CN",
            provider="deepseek-chat",
            latency_ms=315.6,
            from_cache=False,
        )
        self.popup.display_result(result)

    def _trigger_mock_cache(self) -> None:
        x, y = self._get_target_pos()
        result = TranslationResult(
            original_text="Hello world",
            translated_text="你好，世界！",
            source_lang="en",
            target_lang="zh-CN",
            provider="deepseek",
            latency_ms=0.0,
            from_cache=True,
        )
        if not self.popup._is_pinned:
            self.popup.adjust_position(x, y)
        self.popup.display_result(result)

    def _trigger_mock_error(self) -> None:
        x, y = self._get_target_pos()
        result = TranslationResult(
            original_text="Error sample",
            translated_text="[Error] 认证失败 (401)：API 密钥无效或未授权。",
            source_lang="en",
            target_lang="zh-CN",
            provider="openai",
            latency_ms=120.0,
            from_cache=False,
        )
        if not self.popup._is_pinned:
            self.popup.adjust_position(x, y)
        self.popup.display_result(result)

    def closeEvent(self, event) -> None:
        self.popup.close()
        super().closeEvent(event)


def main() -> None:
    ensure_xcb_cursor_loaded()
    app = QApplication(sys.argv)
    window = SandboxWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
