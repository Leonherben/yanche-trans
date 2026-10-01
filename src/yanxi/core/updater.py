"""言蹊翻译 (YanXi Trans) 在线更新检查与自更新引擎

从 GitHub Releases 获取最新发布包与更新日志，支持语义化版本比对及一键更新下载。
"""

from __future__ import annotations
import os
import re
import sys
import webbrowser
from pathlib import Path
from typing import Callable, Optional
import httpx
from pydantic import BaseModel

import yanxi

GITHUB_REPO = "Leonherben/yanxi-trans"
GITHUB_LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_semver(v_str: str) -> tuple[int, ...]:
    """解析语义化版本字符串为元组，忽略前导 'v' 或其他非数字前缀"""
    cleaned = re.sub(r"^[^\d]*", "", v_str.strip())
    # 提取主次修订号
    parts = []
    for chunk in cleaned.split("."):
        digits = re.match(r"^\d+", chunk)
        if digits:
            parts.append(int(digits.group(0)))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(remote_ver: str, local_ver: str) -> bool:
    """比较远程版本号是否高于当前本地版本号"""
    try:
        return parse_semver(remote_ver) > parse_semver(local_ver)
    except Exception:
        return False


class UpdateInfo(BaseModel):
    """版本更新信息实体"""
    has_update: bool = False
    current_version: str = ""
    latest_version: str = ""
    release_name: str = ""
    release_notes: str = ""
    release_url: str = ""
    download_url: Optional[str] = None
    asset_name: Optional[str] = None
    asset_size: int = 0
    published_at: str = ""
    error_message: Optional[str] = None


def check_github_update(
    current_version: Optional[str] = None,
    timeout: float = 6.0,
) -> UpdateInfo:
    """同步检测 GitHub 仓库最新 Release 版本"""
    current_ver = current_version or yanxi.__version__
    headers = {
        "User-Agent": f"YanXi-Trans/{current_ver} ({sys.platform})",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(GITHUB_LATEST_API, headers=headers)
            if resp.status_code == 404:
                return UpdateInfo(
                    current_version=current_ver,
                    latest_version=current_ver,
                    has_update=False,
                    release_notes="当前暂无发布的更新版本。",
                )
            resp.raise_for_status()
            data = resp.json()

        tag_name = data.get("tag_name", "")
        clean_tag = tag_name.lstrip("v")
        release_name = data.get("name") or tag_name
        release_notes = data.get("body", "无详细更新日志。")
        html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
        published_at = data.get("published_at", "")[:10]  # 提取 YYYY-MM-DD

        # 匹配当前操作系统平台对应的发布资产包
        is_win = sys.platform.startswith("win")
        platform_pattern = "windows" if is_win else "linux"
        matched_download_url: Optional[str] = None
        matched_asset_name: Optional[str] = None
        matched_asset_size: int = 0

        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if platform_pattern in name and (name.endswith(".zip") or name.endswith(".tar.gz")):
                matched_download_url = asset.get("browser_download_url")
                matched_asset_name = asset.get("name")
                matched_asset_size = asset.get("size", 0)
                break

        has_update = is_version_newer(clean_tag, current_ver)

        return UpdateInfo(
            has_update=has_update,
            current_version=current_ver,
            latest_version=clean_tag,
            release_name=release_name,
            release_notes=release_notes,
            release_url=html_url,
            download_url=matched_download_url or html_url,
            asset_name=matched_asset_name,
            asset_size=matched_asset_size,
            published_at=published_at,
        )

    except httpx.HTTPStatusError as e:
        return UpdateInfo(
            current_version=current_ver,
            error_message=f"检查更新服务响应异常 ({e.response.status_code})",
        )
    except httpx.RequestError as e:
        return UpdateInfo(
            current_version=current_ver,
            error_message=f"网络连接超时或无法访问 GitHub: {e}",
        )
    except Exception as e:
        return UpdateInfo(
            current_version=current_ver,
            error_message=f"检查更新失败: {e}",
        )


def open_release_page(info: UpdateInfo) -> None:
    """在系统默认浏览器中打开版本发布或下载页"""
    target_url = info.download_url or info.release_url or f"https://github.com/{GITHUB_REPO}/releases"
    try:
        webbrowser.open(target_url)
    except Exception:
        pass


def download_update_package(
    download_url: str,
    target_path: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
    timeout: float = 60.0,
) -> Path:
    """下载最新更新包到指定路径，并回调下载进度 (current_bytes, total_bytes)"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", download_url, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(target_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress:
                    on_progress(downloaded, total)
    return target_path
