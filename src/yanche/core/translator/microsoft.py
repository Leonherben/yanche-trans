"""Microsoft Translator (微软翻译) 适配器实现

支持自适应双模架构：
1. 默认免 API Key 免费极速通道：模拟官方 Bing Translator / Edge 引擎，自动解析 AbusePreventionHelper 凭证并维持内存级会话缓存；
2. 官方 Azure F0 专线（可选）：当配置了 api_key 时，无缝切换为 Azure 认知服务官方 REST API。
"""

from __future__ import annotations
import re
import time
import threading
from typing import Optional, Tuple, Dict, Any
import httpx

from yanche.core.config import ProviderConfig
from yanche.core.models import TranslationRequest, TranslationResult
from yanche.core.translator.base import BaseTranslator
from yanche.core.translator.openai_compatible import create_safe_http_client


# 语言代码映射字典 (言蹊内部代码 -> 微软 API 代码)
_LANG_MAP: Dict[str, str] = {
    "zh-CN": "zh-Hans",
    "zh": "zh-Hans",
    "zh-TW": "zh-Hant",
    "zh-HK": "zh-Hant",
    "auto": "auto-detect",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "ru": "ru",
    "it": "it",
    "pt": "pt",
    "vi": "vi",
    "th": "th",
    "ar": "ar",
    "id": "id",
}


class _BingSession:
    """必应翻译免 Key 网页会话凭证"""

    def __init__(
        self,
        ig: str,
        iid: str,
        key: str,
        token: str,
        expires_at: float,
        base_host: str = "cn.bing.com",
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        self.ig = ig
        self.iid = iid
        self.key = key
        self.token = token
        self.expires_at = expires_at
        self.base_host = base_host
        self.cookies = cookies or {}

    def is_valid(self) -> bool:
        return time.time() < self.expires_at


class MicrosoftTranslator(BaseTranslator):
    """微软翻译适配器（免 Key 免费通道 + Azure 官方通道双模）"""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._session: Optional[_BingSession] = None
        self._session_lock = threading.Lock()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.bing.com/translator",
        }

    def _map_lang(self, lang: str, is_source: bool = False) -> str:
        """映射语言代号至微软规范"""
        if not lang:
            return "auto-detect" if is_source else "zh-Hans"
        clean = lang.strip()
        if clean in _LANG_MAP:
            return _LANG_MAP[clean]
        if is_source and clean == "auto":
            return "auto-detect"
        return clean

    def _get_bing_session(self, force_refresh: bool = False) -> _BingSession:
        """获取或自动刷新必应翻译的会话凭证"""
        with self._session_lock:
            if not force_refresh and self._session and self._session.is_valid():
                return self._session

            candidate_urls = [
                "https://cn.bing.com/translator",
                "https://www.bing.com/translator",
            ]
            client = create_safe_http_client(self.config.timeout_seconds, follow_redirects=True)
            try:
                last_err = None
                for page_url in candidate_urls:
                    try:
                        resp = client.get(page_url, headers=self._headers)
                        resp.raise_for_status()
                        html = resp.text

                        ig_match = re.search(r'IG:"([A-Fa-f0-9]+)"', html)
                        iid_match = re.search(r'data-iid="([^"]+)"', html)
                        abuse_match = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)",(\d+)\]', html)

                        if ig_match and iid_match and abuse_match:
                            ig = ig_match.group(1)
                            iid = iid_match.group(1)
                            key = abuse_match.group(1)
                            token = abuse_match.group(2)
                            interval_ms = int(abuse_match.group(3))

                            # 会话通常有效期 1 小时，提前 5 分钟过期
                            expires_at = time.time() + max(300, (interval_ms / 1000) - 300)

                            base_host = "cn.bing.com"
                            if hasattr(resp, "url") and getattr(resp.url, "host", None):
                                base_host = str(resp.url.host)
                            cookies = dict(resp.cookies) if hasattr(resp, "cookies") else {}

                            self._session = _BingSession(
                                ig, iid, key, token, expires_at, base_host=base_host, cookies=cookies
                            )
                            return self._session
                    except Exception as e:
                        last_err = e
                        continue

                raise ValueError(f"无法从必应翻译主页解析动态防滥用会话凭证 ({last_err})")
            finally:
                client.close()

    def _translate_free_bing(self, clean_text: str, src_lang: str, tgt_lang: str) -> str:
        """通过必应网页免 Key 极速通道执行翻译"""
        mapped_src = self._map_lang(src_lang, is_source=True)
        mapped_tgt = self._map_lang(tgt_lang, is_source=False)

        client = create_safe_http_client(self.config.timeout_seconds, follow_redirects=False)
        try:
            for attempt in range(2):
                session = self._get_bing_session(force_refresh=(attempt > 0))

                # 优先使用获取到会话的实际域名，并提供双镜像容灾
                candidate_hosts = [session.base_host, "cn.bing.com", "www.bing.com"]
                seen_hosts = set()
                endpoints = []
                for host in candidate_hosts:
                    if host and host not in seen_hosts:
                        seen_hosts.add(host)
                        endpoints.append(f"https://{host}/ttranslatev3")

                data = {
                    "fromLang": mapped_src,
                    "text": clean_text,
                    "to": mapped_tgt,
                    "token": session.token,
                    "key": session.key,
                }

                for endpoint in endpoints:
                    url = f"{endpoint}?isVertical=1&&IG={session.ig}&IID={session.iid}"
                    try:
                        resp = client.post(
                            url,
                            headers=self._headers,
                            data=data,
                            cookies=session.cookies,
                            follow_redirects=False,
                        )

                        # 如果服务端返回 301/302 重定向，手动重定向 POST，避免 HTTP 规范将 POST 降级为无 Body 的 GET
                        if resp.status_code in (301, 302, 303, 307, 308):
                            loc = resp.headers.get("location")
                            if loc:
                                if not loc.startswith("http"):
                                    loc = f"https://{session.base_host}{loc}" if loc.startswith("/") else f"https://{session.base_host}/{loc}"
                                resp = client.post(
                                    loc,
                                    headers=self._headers,
                                    data=data,
                                    cookies=session.cookies,
                                    follow_redirects=False,
                                )

                        if resp.status_code != 200:
                            continue

                        raw_text = resp.text.strip()
                        if not raw_text:
                            # 响应体为空，说明该端点丢弃了请求体或遇到校验阻断，尝试下一个备用端点
                            continue

                        try:
                            res_json = resp.json()
                        except Exception:
                            # 响应不是标准 JSON 格式，尝试下一个备用端点
                            continue

                        # 检查是否由于 token 过期返回了 205
                        if isinstance(res_json, dict) and res_json.get("statusCode") == 205:
                            break  # 跳出当前端点循环，外层 attempt 循环将强制刷新凭证

                        if isinstance(res_json, list) and len(res_json) > 0:
                            translations = res_json[0].get("translations", [])
                            if translations and "text" in translations[0]:
                                return translations[0]["text"]

                    except Exception:
                        continue

            raise ValueError("必应翻译重试后仍未获取到有效译文（可能受到临时限流或网络阻断）")
        finally:
            client.close()

    def _translate_azure_official(self, clean_text: str, src_lang: str, tgt_lang: str) -> str:
        """通过 Azure Cognitive Services 官方 REST API 执行翻译"""
        mapped_tgt = self._map_lang(tgt_lang, is_source=False)
        params: Dict[str, str] = {
            "api-version": "3.0",
            "to": mapped_tgt,
        }
        mapped_src = self._map_lang(src_lang, is_source=True)
        if mapped_src != "auto-detect":
            params["from"] = mapped_src

        headers = {
            "Ocp-Apim-Subscription-Key": self.config.api_key,
            "Content-Type": "application/json",
        }
        # 如果 base_url 提供了区域信息或者默认 global
        if "region=" in self.config.base_url:
            region = self.config.base_url.split("region=")[-1].split("&")[0]
            headers["Ocp-Apim-Subscription-Region"] = region

        endpoint = "https://api.cognitive.microsofttranslator.com/translate"
        if self.config.base_url and self.config.base_url.startswith("http") and not self.config.base_url.endswith("ttranslatev3"):
            endpoint = self.config.base_url.split("?")[0]

        client = create_safe_http_client(self.config.timeout_seconds)
        try:
            resp = client.post(endpoint, params=params, headers=headers, json=[{"Text": clean_text}])
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                translations = data[0].get("translations", [])
                if translations and "text" in translations[0]:
                    return translations[0]["text"]
            raise ValueError(f"Azure 接口返回非预期响应: {data}")
        finally:
            client.close()

    def translate(self, request: TranslationRequest) -> TranslationResult:
        clean_text = request.clean_text()
        if not clean_text:
            return TranslationResult(
                original_text="",
                translated_text="[Error] 输入文本为空",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=0.0,
            )

        start_time = time.perf_counter()
        try:
            # 判断调用模式：有 Key 走官方专线，无 Key 走免费通道
            if self.config.api_key and self.config.api_key.strip():
                translated_text = self._translate_azure_official(
                    clean_text, request.source_lang, request.target_lang
                )
            else:
                translated_text = self._translate_free_bing(
                    clean_text, request.source_lang, request.target_lang
                )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TranslationResult(
                original_text=clean_text,
                translated_text=translated_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=round(latency_ms, 1),
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return TranslationResult(
                original_text=clean_text,
                translated_text=f"[Error] 微软翻译错误: {e}",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                provider=self.config.name,
                latency_ms=round(latency_ms, 1),
            )

    def test_connection(self) -> Tuple[bool, str]:
        """连通性健康探测"""
        req = TranslationRequest(text="Hello", source_lang="en", target_lang="zh-CN")
        res = self.translate(req)
        if res.is_success():
            mode = "Azure 官方专线" if self.config.api_key else "必应免 Key 免费通道"
            return True, f"微软翻译连通成功 [{mode}]，测试译文: {res.translated_text} ({res.latency_ms:.0f}ms)"
        return False, f"微软翻译探测失败: {res.translated_text}"
