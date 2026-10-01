"""选词清洗逻辑单测"""

import pytest
from yanche.adapters.selection.base import BaseSelectionListener


class DummySelectionListener(BaseSelectionListener):
    def start(self) -> None:
        pass
    def stop(self) -> None:
        pass


def test_sanitize_valid_text():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=100)
    assert listener.sanitize_text("  hello world  ") == "hello world"
    assert listener.sanitize_text("Python3") == "Python3"


def test_sanitize_too_short_or_empty():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=10)
    assert listener.sanitize_text("") is None
    assert listener.sanitize_text("   ") is None
    assert listener.sanitize_text("a") is None


def test_sanitize_pure_symbols():
    listener = DummySelectionListener(lambda text, pos: None, min_length=2, max_length=100)
    assert listener.sanitize_text("---") is None
    assert listener.sanitize_text("!@#$%^&*()") is None
    assert listener.sanitize_text(" \n\t  ") is None


def test_sanitize_too_long():
    listener = DummySelectionListener(lambda text, pos: None, min_length=1, max_length=10)
    assert listener.sanitize_text("this is too long text") is None
