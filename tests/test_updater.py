"""言蹊翻译 在线更新引擎单元测试"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import pytest

from yanxi.core.updater import (
    parse_semver,
    is_version_newer,
    check_github_update,
    open_release_page,
    download_update_package,
    UpdateInfo,
)


def test_parse_semver():
    assert parse_semver("0.1.0") == (0, 1, 0)
    assert parse_semver("v1.2.3") == (1, 2, 3)
    assert parse_semver("2.0") == (2, 0, 0)
    assert parse_semver("v3") == (3, 0, 0)
    assert parse_semver("1.0.4-rc1") == (1, 0, 4)


def test_is_version_newer():
    assert is_version_newer("0.2.0", "0.1.0") is True
    assert is_version_newer("1.0.0", "0.9.9") is True
    assert is_version_newer("v0.1.1", "0.1.0") is True
    assert is_version_newer("0.1.0", "0.1.0") is False
    assert is_version_newer("0.0.9", "0.1.0") is False


def test_check_github_update_has_new_version():
    mock_payload = {
        "tag_name": "v0.2.0",
        "name": "言蹊翻译 v0.2.0",
        "body": "更新日志：\n- 修复 Windows 图标\n- 新增在线更新检查",
        "html_url": "https://github.com/Leonherben/yanxi-trans/releases/tag/v0.2.0",
        "published_at": "2026-10-02T08:00:00Z",
        "assets": [
            {
                "name": "yanxi-v0.2.0-windows-x86_64.zip",
                "browser_download_url": "https://github.com/Leonherben/yanxi-trans/releases/download/v0.2.0/yanxi-v0.2.0-windows-x86_64.zip",
                "size": 15000000,
            },
            {
                "name": "yanxi-v0.2.0-linux-x86_64.tar.gz",
                "browser_download_url": "https://github.com/Leonherben/yanxi-trans/releases/download/v0.2.0/yanxi-v0.2.0-linux-x86_64.tar.gz",
                "size": 18000000,
            },
        ],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp):
        info = check_github_update(current_version="0.1.0")
        assert info.has_update is True
        assert info.latest_version == "0.2.0"
        assert info.current_version == "0.1.0"
        assert "修复 Windows 图标" in info.release_notes
        assert info.download_url is not None
        assert info.asset_name is not None
        assert info.published_at == "2026-10-02"


def test_check_github_update_already_latest():
    mock_payload = {
        "tag_name": "v0.1.0",
        "name": "言蹊翻译 v0.1.0",
        "body": "初始版本",
        "html_url": "https://github.com/Leonherben/yanxi-trans/releases/tag/v0.1.0",
        "published_at": "2026-10-01T08:00:00Z",
        "assets": [],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp):
        info = check_github_update(current_version="0.1.0")
        assert info.has_update is False
        assert info.latest_version == "0.1.0"


def test_check_github_update_404_no_release():
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.Client.get", return_value=mock_resp):
        info = check_github_update(current_version="0.1.0")
        assert info.has_update is False
        assert "暂无发布" in info.release_notes


def test_check_github_update_network_error():
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Network unreachable")):
        info = check_github_update(current_version="0.1.0")
        assert info.has_update is False
        assert info.error_message is not None
        assert "网络连接超时" in info.error_message


def test_open_release_page():
    info = UpdateInfo(
        download_url="https://github.com/Leonherben/yanxi-trans/releases/download/v0.2.0/yanxi.zip",
        release_url="https://github.com/Leonherben/yanxi-trans/releases/tag/v0.2.0",
    )
    with patch("webbrowser.open") as mock_open:
        open_release_page(info)
        mock_open.assert_called_once_with(info.download_url)


def test_download_update_package(tmp_path):
    target_file = tmp_path / "download" / "yanxi.zip"
    chunks = [b"chunk1_", b"chunk2_", b"chunk3"]

    mock_resp = MagicMock()
    mock_resp.headers = {"content-length": str(sum(len(c) for c in chunks))}
    mock_resp.iter_bytes.return_value = iter(chunks)

    progress_records = []
    def on_progress(cur, total):
        progress_records.append((cur, total))

    with patch("httpx.stream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = mock_resp
        result = download_update_package(
            "https://fake.url/yanxi.zip",
            target_file,
            on_progress=on_progress,
        )

        assert result == target_file
        assert target_file.exists()
        assert target_file.read_bytes() == b"chunk1_chunk2_chunk3"
        assert len(progress_records) == 3
        assert progress_records[-1][0] == len(b"chunk1_chunk2_chunk3")
