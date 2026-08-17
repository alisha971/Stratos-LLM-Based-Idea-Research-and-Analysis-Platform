"""SSRF guard release-blocker tests (security §5). All 8 cases must pass."""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.safe_fetch import BlockedRequestError, safe_get


def _addrinfo(ip: str):
    return [(2, 1, 6, "", (ip, 0))]


def test_block_cloud_metadata():
    with pytest.raises(BlockedRequestError):
        safe_get("http://169.254.169.254/latest/meta-data/")


def test_block_localhost_redis_port():
    with pytest.raises(BlockedRequestError):
        safe_get("http://localhost:6379")


def test_block_file_scheme():
    with pytest.raises(BlockedRequestError):
        safe_get("file:///etc/passwd")


def test_block_ftp_scheme():
    with pytest.raises(BlockedRequestError):
        safe_get("ftp://x")


def test_block_loopback_ip_with_app_port():
    with pytest.raises(BlockedRequestError):
        safe_get("http://127.0.0.1:8000")


def test_block_hostname_resolving_to_private():
    with patch("app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
        with pytest.raises(BlockedRequestError):
            safe_get("http://internal.example.com")


def test_block_redirect_to_private():
    redirect = MagicMock()
    redirect.is_redirect = True
    redirect.status_code = 302
    redirect.headers = {"Location": "http://192.168.1.1/"}

    with patch("app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        with patch("app.utils.safe_fetch.requests.get", return_value=redirect):
            with pytest.raises(BlockedRequestError):
                safe_get("https://example.com")


def test_allow_public_https():
    ok = MagicMock()
    ok.is_redirect = False
    ok.status_code = 200
    ok.headers = {"Content-Type": "text/html"}
    ok.iter_content = lambda chunk_size=8192: [b"<html>ok</html>"]

    with patch("app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        with patch("app.utils.safe_fetch.requests.get", return_value=ok):
            resp = safe_get("https://example.com")
    assert resp.status_code == 200
    assert resp._content == b"<html>ok</html>"
