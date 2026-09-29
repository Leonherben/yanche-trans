"""CLI 命令行功能单元测试"""

from unittest.mock import patch
import pytest
from quicktrans.cli.main import parse_args, do_translate
from quicktrans.core.config import AppConfig
from quicktrans.core.models import TranslationResult
from quicktrans.core.cache.sqlite_cache import SQLiteCache


def test_parse_args():
    with patch("sys.argv", ["quicktrans-cli", "hello", "-s", "en", "-t", "zh-CN"]):
        args = parse_args()
        assert args.text == "hello"
        assert args.source == "en"
        assert args.target == "zh-CN"


def test_cli_cache_hit(capsys, tmp_path):
    cache = SQLiteCache(tmp_path / "cache.db")
    item = TranslationResult(
        original_text="dog",
        translated_text="狗",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
    )
    cache.put(item)

    config = AppConfig()
    config.enable_cache = True
    do_translate("dog", config, cache, "en", "zh-CN", "deepseek")

    captured = capsys.readouterr()
    assert "[Cache]" in captured.out
    assert "狗" in captured.out
