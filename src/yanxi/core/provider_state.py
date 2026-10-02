"""根据本地配置判断密钥需求，不代表服务连通性。"""

from ipaddress import ip_address
from urllib.parse import urlsplit

from yanxi.core.config import ProviderConfig


def is_microsoft(config: ProviderConfig) -> bool:
    return config.provider_type in ("microsoft", "bing") or config.name.lower() in ("microsoft", "bing")


def is_local_service(config: ProviderConfig) -> bool:
    try:
        host = urlsplit(config.base_url).hostname
        if host and host.lower() == "localhost":
            return True
        return bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


def needs_api_key(config: ProviderConfig) -> bool:
    return not is_microsoft(config) and not is_local_service(config)


def is_configured(config: ProviderConfig) -> bool:
    return not needs_api_key(config) or bool(config.api_key.strip())
