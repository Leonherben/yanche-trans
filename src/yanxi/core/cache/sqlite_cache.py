"""轻量级 SQLite 本地缓存引擎 (Local Cache Engine)

避免重复请求相同词句，极速秒开（0ms 响应），保护网络与 API 资费。
"""

from __future__ import annotations
import hashlib
from contextlib import contextmanager
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from yanxi.core.config import AppConfig
from yanxi.core.models import TranslationResult


class SQLiteCache:
    """基于 SQLite 的紧凑键值与翻译历史缓存"""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            config_dir = AppConfig.get_default_config_path().parent
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "cache.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translation_cache (
                    hash_key TEXT PRIMARY KEY,
                    original_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash_key ON translation_cache(hash_key)")
            conn.commit()

    @staticmethod
    def compute_key(text: str, source_lang: str, target_lang: str, provider: str) -> str:
        """根据标准化的待翻译文本和语种生成 SHA256 指纹"""
        normalized = text.strip()
        raw = f"{source_lang}|{target_lang}|{provider}|{normalized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, text: str, source_lang: str, target_lang: str, provider: str) -> Optional[TranslationResult]:
        """查询缓存，若命中则更新访问计数并返回 TranslationResult"""
        key = self.compute_key(text, source_lang, target_lang, provider)
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT original_text, translated_text, source_lang, target_lang, provider, latency_ms, created_at
                FROM translation_cache
                WHERE hash_key = ?
                """,
                (key,)
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE translation_cache
                    SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP
                    WHERE hash_key = ?
                    """,
                    (key,)
                )
                conn.commit()
                return TranslationResult(
                    original_text=row["original_text"],
                    translated_text=row["translated_text"],
                    source_lang=row["source_lang"],
                    target_lang=row["target_lang"],
                    provider=row["provider"],
                    latency_ms=0.0,
                    from_cache=True,
                )
        return None

    def put(self, result: TranslationResult) -> None:
        """将成功翻译的结果写入缓存"""
        if not result.is_success():
            return

        key = self.compute_key(
            result.original_text,
            result.source_lang,
            result.target_lang,
            result.provider,
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO translation_cache (
                    hash_key, original_text, translated_text, source_lang, target_lang, provider, latency_ms, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(hash_key) DO UPDATE SET
                    translated_text = excluded.translated_text,
                    latency_ms = excluded.latency_ms,
                    last_accessed_at = CURRENT_TIMESTAMP
                """,
                (
                    key,
                    result.original_text,
                    result.translated_text,
                    result.source_lang,
                    result.target_lang,
                    result.provider,
                    result.latency_ms,
                ),
            )
            conn.commit()

    def clear(self) -> None:
        """清空缓存"""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM translation_cache")
            conn.commit()
