"""翻译器工厂 (Translator Factory)

根据 ProviderConfig 动态创建对应的 BaseTranslator 实例。
"""

from __future__ import annotations
from yanxi.core.config import ProviderConfig
from yanxi.core.translator.base import BaseTranslator
from yanxi.core.translator.openai_compatible import OpenAICompatibleTranslator
from yanxi.core.translator.microsoft import MicrosoftTranslator


def create_translator(config: ProviderConfig) -> BaseTranslator:
    """创建翻译器实例"""
    if config.provider_type in ("microsoft", "bing") or config.name.lower() in ("microsoft", "bing"):
        return MicrosoftTranslator(config)
    elif config.provider_type == "openai_compatible":
        return OpenAICompatibleTranslator(config)
    else:
        # 默认回退为 OpenAI 兼容适配器
        return OpenAICompatibleTranslator(config)
