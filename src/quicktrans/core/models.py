"""领域数据模型 (Domain Models)

定义核心翻译请求与响应实体，保持与操作系统及 GUI 框架的完全解耦。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TranslationRequest:
    """翻译请求实体"""
    text: str
    source_lang: str = "auto"
    target_lang: str = "zh-CN"
    context: Optional[str] = None

    def clean_text(self) -> str:
        """清洗文本：合并多余空行与换行符，便于句意翻译"""
        lines = [line.strip() for line in self.text.splitlines() if line.strip()]
        return " ".join(lines)


@dataclass(frozen=True)
class TranslationResult:
    """翻译结果实体"""
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    provider: str
    latency_ms: float = 0.0
    from_cache: bool = False
    phonetic: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def is_success(self) -> bool:
        return bool(self.translated_text and not self.translated_text.startswith("[Error]"))
