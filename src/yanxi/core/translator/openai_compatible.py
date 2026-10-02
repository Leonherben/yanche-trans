"""OpenAI-Compatible 翻译器实现

支持 DeepSeek, OpenAI, 智谱, Moonshot, Ollama 等任意兼容 OpenAI API 的服务。
"""

from __future__ import annotations
import os
import time
from typing import Tuple
import httpx
from yanxi.core.config import ProviderConfig
from yanxi.core.provider_state import is_configured
from yanxi.core.models import TranslationRequest, TranslationResult
from yanxi.core.translator.base import BaseTranslator


def normalize_proxy_env() -> None:
    """自动将 Linux 桌面环境下常见的 socks:// 转换为 httpx 识别的 socks5:// 协议头"""
    for key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        val = os.environ.get(key)
        if val and val.startswith("socks://"):
            os.environ[key] = "socks5://" + val[len("socks://"):]


def create_safe_http_client(timeout_seconds: float, follow_redirects: bool = True) -> httpx.Client:
    """创建具备异常代理自愈能力的 HTTP 客户端（默认自动跟随重定向）"""
    normalize_proxy_env()
    try:
        return httpx.Client(timeout=timeout_seconds, follow_redirects=follow_redirects)
    except Exception:
        # 当系统代理协议不兼容或损坏时，安全降级为不读取环境代理直连
        return httpx.Client(timeout=timeout_seconds, follow_redirects=follow_redirects, trust_env=False)


class OpenAICompatibleTranslator(BaseTranslator):
    """基于 OpenAI /chat/completions 规范的通用大模型翻译适配器"""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        # 处理不同提供商 url 规范（若末尾未提供 /chat/completions 则自动补全）
        if not self.base_url.endswith("/chat/completions"):
            self.endpoint = f"{self.base_url}/chat/completions"
        else:
            self.endpoint = self.base_url

    def _build_messages(self, request: TranslationRequest) -> list[dict[str, str]]:
        clean_text = request.clean_text()
        prompt = (
            f"Please translate the following text from {request.source_lang} into {request.target_lang}.\n"
            f"Original text:\n{clean_text}"
        )
        if request.context:
            prompt += f"\n\nContext information for reference:\n{request.context}"

        return [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": prompt},
        ]

    def translate(self, request: TranslationRequest) -> TranslationResult:
        if not is_configured(self.config):
            return TranslationResult(
                original_text=request.text,
                translated_text="[Error] 未配置 API Key，请在设置中输入有效的 API 密钥。",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=0.0,
            )

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.config.model,
            "messages": self._build_messages(request),
            "temperature": 0.3,
            "stream": False,
        }

        start_time = time.perf_counter()
        try:
            with create_safe_http_client(self.config.timeout_seconds) as client:
                response = client.post(self.endpoint, headers=headers, json=payload)
                latency = (time.perf_counter() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        content = choices[0]["message"].get("content", "").strip()
                        return TranslationResult(
                            original_text=request.text,
                            translated_text=content,
                            source_lang=request.source_lang,
                            target_lang=request.target_lang,
                            provider=self.config.name,
                            latency_ms=round(latency, 1),
                        )
                    return TranslationResult(
                        original_text=request.text,
                        translated_text="[Error] 翻译响应数据格式异常",
                        source_lang=request.source_lang,
                        target_lang=request.target_lang,
                        provider=self.config.name,
                        latency_ms=round(latency, 1),
                    )
                elif response.status_code == 401:
                    return TranslationResult(
                        original_text=request.text,
                        translated_text="[Error] 认证失败 (401)：API 密钥无效或未授权。",
                        source_lang=request.source_lang,
                        target_lang=request.target_lang,
                        provider=self.config.name,
                        latency_ms=round(latency, 1),
                    )
                else:
                    return TranslationResult(
                        original_text=request.text,
                        translated_text=f"[Error] API 请求失败 HTTP {response.status_code}: {response.text[:200]}",
                        source_lang=request.source_lang,
                        target_lang=request.target_lang,
                        provider=self.config.name,
                        latency_ms=round(latency, 1),
                    )
        except httpx.TimeoutException:
            latency = (time.perf_counter() - start_time) * 1000
            return TranslationResult(
                original_text=request.text,
                translated_text=f"[Error] 请求超时 ({self.config.timeout_seconds}s)，请检查网络连接。",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            return TranslationResult(
                original_text=request.text,
                translated_text=f"[Error] 网络请求异常: {str(e)}",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=round(latency, 1),
            )

    def test_connection(self) -> Tuple[bool, str]:
        test_req = TranslationRequest(text="Hello", source_lang="en", target_lang="zh-CN")
        res = self.translate(test_req)
        if res.is_success():
            return True, f"连接成功！耗时: {res.latency_ms}ms, 结果: {res.translated_text}"
        return False, res.translated_text
