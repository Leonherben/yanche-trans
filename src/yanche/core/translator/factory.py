"""翻译器工厂 (Translator Factory)

根据 ProviderConfig 动态创建对应的 BaseTranslator 实例。
"""

from __future__ import annotations
from yanche.core.config import ProviderConfig
from yanche.core.translator.base import BaseTranslator
from yanche.core.translator.openai_compatible import OpenAICompatibleTranslator


def create_translator(config: ProviderConfig) -> BaseTranslator:
    """创建翻译器实例"""
    if config.provider_type == "openai_compatible":
        return OpenAICompatibleTranslator(config)
    else:
        # 默认回退为 OpenAI 兼容适配器
        return OpenAICompatibleTranslator(config)
