"""翻译器抽象契约 (Base Translator Interface)

所有翻译服务适配器（包括大模型与传统翻译 API）必须实现的纯逻辑基类。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Tuple
from quicktrans.core.models import TranslationRequest, TranslationResult


class BaseTranslator(ABC):
    """翻译器基类"""

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """执行同步翻译调用

        Args:
            request: 翻译请求对象

        Returns:
            TranslationResult: 翻译结果对象
        """
        pass

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """测试服务网络连通性与 API Key 有效性

        Returns:
            Tuple[bool, str]: (是否成功, 详细诊断说明)
        """
        pass
