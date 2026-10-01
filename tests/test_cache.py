"""SQLite 本地缓存单测"""

import tempfile
from pathlib import Path
import pytest
from yanche.core.cache.sqlite_cache import SQLiteCache
from yanche.core.models import TranslationResult


@pytest.fixture
def temp_cache():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_cache.db"
        yield SQLiteCache(db_path)


def test_cache_miss(temp_cache):
    res = temp_cache.get("hello", "en", "zh-CN", "deepseek")
    assert res is None


def test_cache_hit(temp_cache):
    item = TranslationResult(
        original_text="apple",
        translated_text="苹果",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
        latency_ms=250.0,
    )
    temp_cache.put(item)

    cached = temp_cache.get("apple", "en", "zh-CN", "deepseek")
    assert cached is not None
    assert cached.translated_text == "苹果"
    assert cached.from_cache is True
    assert cached.latency_ms == 0.0


def test_cache_does_not_store_errors(temp_cache):
    err_item = TranslationResult(
        original_text="fail_word",
        translated_text="[Error] 401 Unauthorized",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
    )
    temp_cache.put(err_item)

    assert temp_cache.get("fail_word", "en", "zh-CN", "deepseek") is None


def test_cache_clear(temp_cache):
    item = TranslationResult(
        original_text="cat",
        translated_text="猫",
        source_lang="en",
        target_lang="zh-CN",
        provider="deepseek",
    )
    temp_cache.put(item)
    assert temp_cache.get("cat", "en", "zh-CN", "deepseek") is not None

    temp_cache.clear()
    assert temp_cache.get("cat", "en", "zh-CN", "deepseek") is None
