"""无焦点悬浮窗 PopupBubble 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pytest
from PySide6.QtWidgets import QApplication
from yanche.core.config import UIConfig
from yanche.core.models import TranslationResult
from yanche.adapters.gui.popup import PopupBubble


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_popup_init(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    assert popup.width() >= 320
    assert not popup.isVisible()
    popup.close()


def test_popup_display_success_markdown(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    result = TranslationResult(
        original_text="test text",
        translated_text="**测试加粗**\n- 列表项1\n- 列表项2",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
        latency_ms=120.0,
    )
    popup.display_result(result)
    assert popup.isVisible()
    assert popup.provider_label.text() == "🤖 deepseek"
    assert "120" in popup.latency_label.text()
    assert popup.original_label.text() == "test text"
    rendered_html = popup.text_browser.toHtml()
    assert "<b>" in rendered_html or "font-weight" in rendered_html or "strong" in rendered_html
    popup.close()


def test_popup_display_error(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    result = TranslationResult(
        original_text="error text",
        translated_text="[Error] 认证失败 (401)",
        source_lang="en",
        target_lang="zh-CN",
        provider="openai",
        latency_ms=80.0,
    )
    popup.display_result(result)
    assert popup.isVisible()
    rendered_html = popup.text_browser.toHtml()
    assert "401" in rendered_html
    popup.close()


def test_popup_dismiss_if_outside(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    popup.resize(320, 150)
    popup.move(100, 100)
    popup.show()

    # 1. 点击窗口外部 (500, 500)，未钉住状态下应自动收起
    popup.dismiss_if_outside(500, 500)
    assert not popup.isVisible()

    # 2. 重新显示并钉住 (pin)
    popup.show()
    popup._is_pinned = True
    popup.dismiss_if_outside(500, 500)
    # 钉住状态下即便点击外部也不收起
    assert popup.isVisible()

    popup.close()


def test_popup_closed_signal(qapp):
    config = UIConfig()
    popup = PopupBubble(config)
    popup.show()

    closed_fired = []
    popup.closed.connect(lambda: closed_fired.append(True))

    popup.hide()
    assert len(closed_fired) == 1
    popup.close()
