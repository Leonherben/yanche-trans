"""核心翻译引擎单元测试 (Mock HTTP Requests)"""

from unittest.mock import MagicMock, patch
import pytest
import httpx
from yanche.core.config import ProviderConfig
from yanche.core.models import TranslationRequest
from yanche.core.translator.openai_compatible import OpenAICompatibleTranslator


@pytest.fixture
def mock_provider_config():
    return ProviderConfig(
        name="test-llm",
        provider_type="openai_compatible",
        base_url="https://api.test.com/v1",
        api_key="sk-test-secret-key",
        model="gpt-test-model",
        timeout_seconds=5.0,
    )


def test_missing_api_key():
    config = ProviderConfig(
        name="test-empty",
        provider_type="openai_compatible",
        base_url="https://api.test.com/v1",
        api_key="",
    )
    translator = OpenAICompatibleTranslator(config)
    req = TranslationRequest(text="Hello world")
    res = translator.translate(req)

    assert not res.is_success()
    assert "未配置 API Key" in res.translated_text


@patch("httpx.Client.post")
def test_successful_translation(mock_post, mock_provider_config):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "你好，世界",
                }
            }
        ]
    }
    mock_post.return_value = mock_resp

    translator = OpenAICompatibleTranslator(mock_provider_config)
    req = TranslationRequest(text="Hello world", source_lang="en", target_lang="zh-CN")
    res = translator.translate(req)

    assert res.is_success()
    assert res.translated_text == "你好，世界"
    assert res.provider == "test-llm"
    assert res.latency_ms >= 0


@patch("httpx.Client.post")
def test_unauthorized_401(mock_post, mock_provider_config):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_post.return_value = mock_resp

    translator = OpenAICompatibleTranslator(mock_provider_config)
    req = TranslationRequest(text="Hello world")
    res = translator.translate(req)

    assert not res.is_success()
    assert "401" in res.translated_text


@patch("httpx.Client.post")
def test_timeout_handling(mock_post, mock_provider_config):
    mock_post.side_effect = httpx.TimeoutException("Timeout")

    translator = OpenAICompatibleTranslator(mock_provider_config)
    req = TranslationRequest(text="Hello world")
    res = translator.translate(req)

    assert not res.is_success()
    assert "请求超时" in res.translated_text


def test_socks_proxy_scheme_healing(monkeypatch):
    from yanche.core.translator.openai_compatible import create_safe_http_client

    # 模拟 Linux Mint/GNOME 桌面环境设置的 socks:// 协议头
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:7890/")
    monkeypatch.setenv("all_proxy", "socks://127.0.0.1:7890/")

    # 验证客户端创建不会因为未知协议头崩溃
    client = create_safe_http_client(timeout_seconds=5.0)
    assert client is not None
    client.close()
