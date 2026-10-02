"""发音服务与本地缓存模块 (TTS / Pronunciation Service)

提供单词、短语与句子的英音 (UK) 与美音 (US) 发音拉取，并在本地目录缓存 MP3 文件以实现极速秒播。
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Literal, Optional

import httpx

logger = logging.getLogger(__name__)

AccentType = Literal["uk", "us"]


def get_default_audio_cache_dir() -> Path:
    """获取跨平台音频缓存目录 (~/.config/yanxi/audio_cache 或 %APPDATA%/yanxi/audio_cache)"""
    if sys.platform == "win32":
        base_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    cache_dir = base_dir / "yanxi" / "audio_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


class TTSManager:
    """TTS 音频管理器：下载、本地缓存与音源调度"""

    def __init__(self, cache_dir: Optional[Path] = None, timeout_seconds: float = 6.0) -> None:
        self.cache_dir = cache_dir or get_default_audio_cache_dir()
        self.timeout_seconds = timeout_seconds

    def get_cache_path(self, text: str, accent: AccentType) -> Path:
        """根据文本和口音计算本地缓存文件路径"""
        clean = " ".join(text.strip().split())
        key = hashlib.sha256(f"{clean}:{accent.lower()}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.mp3"

    def get_cached_audio_path(self, text: str, accent: AccentType) -> Optional[Path]:
        """如果本地存在有效缓存则返回路径，否则返回 None"""
        path = self.get_cache_path(text, accent)
        if path.exists() and path.stat().st_size > 0:
            return path
        return None

    def get_audio_url_youdao(self, text: str, accent: AccentType) -> str:
        """有道词典真人发音接口 (type=1: 英音, type=2: 美音)"""
        encoded = urllib.parse.quote(text.strip())
        accent_code = "1" if accent.lower() == "uk" else "2"
        return f"https://dict.youdao.com/dictvoice?audio={encoded}&type={accent_code}"

    def get_audio_url_google(self, text: str, accent: AccentType) -> str:
        """Google Translate TTS 接口 (en-GB: 英音, en-US: 美音)"""
        encoded = urllib.parse.quote(text.strip())
        lang_code = "en-GB" if accent.lower() == "uk" else "en-US"
        return f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl={lang_code}&q={encoded}"

    def fetch_audio_file(self, text: str, accent: AccentType = "us") -> Optional[Path]:
        """拉取指定文本的音频并缓存到本地。若已有缓存则直接返回缓存文件。"""
        clean_text = " ".join(text.strip().split())
        if not clean_text:
            return None

        # 检查缓存
        cached = self.get_cached_audio_path(clean_text, accent)
        if cached:
            return cached

        target_file = self.get_cache_path(clean_text, accent)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        # 策略：短文本（<= 8 词且 <= 60 字符）优先使用有道词典原生真人发音；长句优先 Google TTS
        words = clean_text.split()
        if len(words) <= 8 and len(clean_text) <= 60:
            candidate_urls = [
                self.get_audio_url_youdao(clean_text, accent),
                self.get_audio_url_google(clean_text, accent),
            ]
        else:
            candidate_urls = [
                self.get_audio_url_google(clean_text, accent),
                self.get_audio_url_youdao(clean_text, accent),
            ]

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                for url in candidate_urls:
                    try:
                        resp = client.get(url, headers=headers)
                        # 必须是 200 且数据量大于 500 字节（过滤错误提示空音频）
                        if resp.status_code == 200 and len(resp.content) > 500:
                            tmp_file = target_file.with_suffix(".tmp")
                            tmp_file.write_bytes(resp.content)
                            tmp_file.replace(target_file)
                            return target_file
                    except Exception as err:
                        logger.debug("Fetch TTS candidate url failed (%s): %s", url, err)
                        continue
        except Exception as e:
            logger.warning("Fetch TTS audio error: %s", e)

        return None

    def clear_cache(self) -> int:
        """清理本地音频缓存文件，返回删除的文件个数"""
        deleted_count = 0
        if not self.cache_dir.exists():
            return 0
        for item in self.cache_dir.glob("*.mp3"):
            try:
                item.unlink(missing_ok=True)
                deleted_count += 1
            except Exception:
                pass
        return deleted_count
