import io
import sys

from yanxi.adapters.console import configure_console_output


def test_redirected_output_uses_utf8_for_chinese_and_symbols(monkeypatch):
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="gbk")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", stream)
        configure_console_output()
        print("言蹊翻译 ✖ ⚠")
        stream.flush()
    assert buffer.getvalue().decode("utf-8").splitlines() == ["言蹊翻译 ✖ ⚠"]


def test_legacy_console_replaces_unsupported_symbols(monkeypatch):
    class LegacyConsole(io.TextIOWrapper):
        def isatty(self):
            return True
    buffer = io.BytesIO()
    stream = LegacyConsole(buffer, encoding="gbk")
    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", stream)
        configure_console_output()
        print("言蹊翻译 ✖ ⚠")
        stream.flush()
    assert buffer.getvalue().decode("gbk").startswith("言蹊翻译")
