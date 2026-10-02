"""发音模块 (TTS & AudioPlayer) 单元测试"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from yanxi.core.tts import TTSManager
from yanxi.adapters.gui.audio_player import AudioPlayer
from yanxi.adapters.gui.popup import PopupBubble
from yanxi.core.config import UIConfig
from yanxi.core.models import TranslationResult


@pytest.fixture
def temp_cache_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def test_tts_manager_url_generation(temp_cache_dir):
    manager = TTSManager(cache_dir=temp_cache_dir)
    
    # 有道词典 URL 检验
    uk_url = manager.get_audio_url_youdao("apple", "uk")
    us_url = manager.get_audio_url_youdao("apple", "us")
    assert "audio=apple" in uk_url
    assert "type=1" in uk_url
    assert "type=2" in us_url

    # Google TTS URL 检验
    google_uk = manager.get_audio_url_google("good morning", "uk")
    google_us = manager.get_audio_url_google("good morning", "us")
    assert "tl=en-GB" in google_uk
    assert "tl=en-US" in google_us


def test_tts_manager_caching(temp_cache_dir):
    manager = TTSManager(cache_dir=temp_cache_dir)
    
    # 模拟写入假缓存
    fake_audio = b"\x00\x01\x02" * 200
    cache_path = manager.get_cache_path("hello", "us")
    cache_path.write_bytes(fake_audio)
    
    # 命中缓存
    cached = manager.get_cached_audio_path("hello", "us")
    assert cached == cache_path
    
    # fetch_audio_file 直接返回已有缓存，不发网络请求
    res = manager.fetch_audio_file("hello", "us")
    assert res == cache_path

    # 清空缓存
    count = manager.clear_cache()
    assert count == 1
    assert not cache_path.exists()


def test_tts_manager_fetch_mocked_network(temp_cache_dir):
    manager = TTSManager(cache_dir=temp_cache_dir)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake_mp3_content" * 100

    with patch("httpx.Client.get", return_value=mock_resp):
        path = manager.fetch_audio_file("dictionary", "uk")
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == mock_resp.content


def test_audio_player_init(qapp, temp_cache_dir):
    manager = TTSManager(cache_dir=temp_cache_dir)
    player = AudioPlayer(tts_manager=manager)
    assert player.tts_manager == manager

    # 空文本播放不应崩溃
    player.play("", "us")
    player.play("   ", "uk")
    player.stop()


def test_popup_tts_buttons_lifecycle(qapp, temp_cache_dir):
    config = UIConfig()
    popup = PopupBubble(config)

    # 初始状态：按钮应隐藏
    assert popup.tts_uk_btn.text() == "英 🔊"
    assert popup.tts_us_btn.text() == "美 🔊"
    assert popup.trans_tts_uk_btn.text() == "英 🔊"
    assert popup.trans_tts_us_btn.text() == "美 🔊"
    assert popup.tts_uk_btn.isHidden()
    assert popup.tts_us_btn.isHidden()
    assert popup.trans_tts_uk_btn.isHidden()
    assert popup.trans_tts_us_btn.isHidden()

    # 场景 1：英译中（原文是英文，译文是中文）
    popup.original_edit.setPlainText("schedule")
    assert not popup.tts_uk_btn.isHidden()
    assert not popup.tts_us_btn.isHidden()
    assert popup.trans_tts_uk_btn.isHidden()
    assert popup.trans_tts_us_btn.isHidden()

    result_en_to_zh = TranslationResult(
        original_text="schedule",
        translated_text="时刻表",
        source_lang="en",
        target_lang="zh-CN",
        provider="microsoft",
        latency_ms=100.0,
    )
    popup.display_result(result_en_to_zh)
    # 原文含英文：显示
    assert not popup.tts_uk_btn.isHidden()
    assert not popup.tts_us_btn.isHidden()
    # 译文为纯中文：智能隐藏！
    assert popup.trans_tts_uk_btn.isHidden()
    assert popup.trans_tts_us_btn.isHidden()

    # 场景 2：中译英（原文是纯中文，译文是英文）
    result_zh_to_en = TranslationResult(
        original_text="苹果",
        translated_text="apple",
        source_lang="zh-CN",
        target_lang="en",
        provider="microsoft",
        latency_ms=100.0,
    )
    popup.display_result(result_zh_to_en)
    # 原文纯中文：智能隐藏！
    assert popup.tts_uk_btn.isHidden()
    assert popup.tts_us_btn.isHidden()
    # 译文含英文：智能显示！
    assert not popup.trans_tts_uk_btn.isHidden()
    assert not popup.trans_tts_us_btn.isHidden()

    # 点击清空后全部隐藏
    popup._clear_input()
    assert popup.tts_uk_btn.isHidden()
    assert popup.tts_us_btn.isHidden()
    assert popup.trans_tts_uk_btn.isHidden()
    assert popup.trans_tts_us_btn.isHidden()

    popup.close()


def test_popup_tts_click_feedback(qapp, temp_cache_dir):
    config = UIConfig()
    popup = PopupBubble(config)
    popup.original_edit.setPlainText("banana")

    # 点击英音按钮
    with patch.object(popup.audio_player, "play") as mock_play:
        popup.tts_uk_btn.click()
        mock_play.assert_called_once_with("banana", accent="uk", channel="orig")
        assert "⏳" in popup.tts_uk_btn.text()

    # 模拟播放完成事件恢复文本
    popup._on_audio_playback_finished("uk")
    assert popup.tts_uk_btn.text() == "英 🔊"

    popup.close()
