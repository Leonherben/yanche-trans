"""领域数据模型 (Domain Models)

定义核心翻译请求与响应实体，保持与操作系统及 GUI 框架的完全解耦。
"""

from __future__ import annotations
import re
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
        """清洗文本：合并多余空行与换行符，便于句意翻译；自动修复 PDF 跨行英文断词与连字符"""
        if not self.text:
            return ""
        # 统一跨平台换行符
        text = self.text.replace("\r\n", "\n").replace("\r", "\n")
        # 1. 修复学术论文 PDF 双栏排版跨行连字符截断 (如 convo-\n lutional -> convolutional)
        text = re.sub(r'([a-zA-Z]+)-\s*\n\s*([a-zA-Z]+)', r'\1\2', text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
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
