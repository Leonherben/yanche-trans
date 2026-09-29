"""选词监听器抽象基类 (Base Selection Listener)

定义跨平台划词取词与鼠标坐标捕获的标准接口。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, Optional, Tuple


SelectionCallback = Callable[[str, Tuple[int, int]], None]


class BaseSelectionListener(ABC):
    """跨平台选词监听器基类"""

    def __init__(self, callback: SelectionCallback, min_length: int = 1, max_length: int = 3000) -> None:
        self.callback = callback
        self.min_length = min_length
        self.max_length = max_length
        self._is_running = False

    def sanitize_text(self, text: str) -> Optional[str]:
        """对获取到的选中文本进行合规性清洗与边界过滤"""
        if not text:
            return None
        cleaned = text.strip()
        if len(cleaned) < self.min_length or len(cleaned) > self.max_length:
            return None
        # 过滤全是不可见字符或纯特殊符号
        if not any(c.isalnum() for c in cleaned):
            return None
        return cleaned

    @abstractmethod
    def start(self) -> None:
        """启动监听线程/事件循环"""
        pass

    @abstractmethod
    def stop(self) -> None:
        """安全停止监听，释放所有系统钩子"""
        pass

    @property
    def is_running(self) -> bool:
        return self._is_running
