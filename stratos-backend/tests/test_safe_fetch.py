"""SSRF guard release-blocker tests (security §5). All 8 original cases
must pass, plus fix-audit Part 5 coverage: DNS hints/retry/record
filtering, and the IP-pinning adapter that closes the DNS-rebinding/TOCTOU
gap where the vetted IP used to be discarded and `requests` re-resolved
independently just before connecting.

Fix-audit Part 5 changed the actual HTTP call from a bare `requests.get`
to a module-level `Session` (for pooling) with a custom pinning adapter --
tests that need to control the HTTP response now patch
`app.utils.safe_fetch._session.get` (the session instance), not
`app.utils.safe_fetch.requests.get` (which a Session's own `.get()` does
not go through)."""

import socket
from unittest.mock import MagicMock, patch

import pytest

from app.utils import safe_fetch
from app.utils.safe_fetch import BlockedRequestError, safe_get


def _addrinfo(*ips: str):
    return [(2, 1, 6, "", (ip, 0)) for ip in ips]


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
        with patch.object(safe_fetch._session, "get", return_value=redirect):
            with pytest.raises(BlockedRequestError):
                safe_get("https://example.com")


def test_allow_public_https():
    ok = MagicMock()
    ok.is_redirect = False
    ok.status_code = 200
    ok.headers = {"Content-Type": "text/html"}
    ok.iter_content = lambda chunk_size=8192: [b"<html>ok</html>"]

    with patch("app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        with patch.object(safe_fetch._session, "get", return_value=ok) as mock_get:
            resp = safe_get("https://example.com")
    assert resp.status_code == 200
    assert resp._content == b"<html>ok</html>"
    # Fix-audit Part 5: connect/read timeouts are now a tuple, not a
    # single scalar applied to both.
    assert mock_get.call_args.kwargs["timeout"] == (
        safe_fetch.CONNECT_TIMEOUT,
        safe_fetch.READ_TIMEOUT,
    )


class TestDnsResolution:
    """_resolve_public_ip: hints, retry, record filtering."""

    def test_getaddrinfo_called_with_hints_and_real_port(self):
        calls = []

        def fake_getaddrinfo(host, port, family, socktype):
            calls.append((host, port, family, socktype))
            return _addrinfo("93.184.216.34")

        with patch("app.utils.safe_fetch.socket.getaddrinfo", side_effect=fake_getaddrinfo):
            safe_fetch._resolve_public_ip("example.com", 443, "https://example.com")

        assert calls == [("example.com", 443, socket.AF_UNSPEC, socket.SOCK_STREAM)]

    def test_transient_gaierror_is_retried_then_succeeds(self):
        attempts = {"n": 0}

        def fake_getaddrinfo(host, port, family, socktype):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise socket.gaierror("temporary failure")
            return _addrinfo("93.184.216.34")

        with patch("app.utils.safe_fetch.socket.getaddrinfo", side_effect=fake_getaddrinfo):
            with patch("app.utils.safe_fetch.time.sleep"):
                ip = safe_fetch._resolve_public_ip("example.com", 443, "https://example.com")

        assert ip == "93.184.216.34"
        assert attempts["n"] == 2

    def test_persistent_gaierror_raises_blocked_request_error_tagged_dns(self, caplog):
        def always_fails(host, port, family, socktype):
            raise socket.gaierror("nope")

        with patch("app.utils.safe_fetch.socket.getaddrinfo", side_effect=always_fails):
            with patch("app.utils.safe_fetch.time.sleep"):
                with caplog.at_level("WARNING"):
                    with pytest.raises(BlockedRequestError):
                        safe_fetch._resolve_public_ip(
                            "example.com", 443, "https://example.com"
                        )

        assert "[DNS]" in caplog.text
        assert "[SSRF]" not in caplog.text

    def test_mixed_record_set_keeps_public_drops_forbidden(self):
        # Fix-audit Part 5: previously ANY forbidden record blocked the
        # whole host -- a large mixed A/AAAA set (realistic for a
        # CDN-backed domain) must not be blocked just because one record
        # looks reserved.
        with patch(
            "app.utils.safe_fetch.socket.getaddrinfo",
            return_value=_addrinfo("169.254.0.1", "93.184.216.34"),
        ):
            ip = safe_fetch._resolve_public_ip("example.com", 443, "https://example.com")
        assert ip == "93.184.216.34"

    def test_all_records_forbidden_still_blocks(self):
        with patch(
            "app.utils.safe_fetch.socket.getaddrinfo",
            return_value=_addrinfo("169.254.0.1", "127.0.0.1"),
        ):
            with pytest.raises(BlockedRequestError):
                safe_fetch._resolve_public_ip("example.com", 443, "https://example.com")


class TestHostNormalization:
    def test_trailing_dot_is_stripped(self):
        assert safe_fetch._normalize_host("example.com.") == "example.com"

    def test_idna_encodes_unicode_host(self):
        # A trivial ASCII-safe round trip; a full IDNA/punycode host isn't
        # needed to prove the encode path runs and doesn't raise.
        assert safe_fetch._normalize_host("example.com") == "example.com"

    def test_malformed_host_falls_through_unchanged_rather_than_raising(self):
        # An empty label or other malformed input must not crash
        # _validate_url -- getaddrinfo (or the caller) rejects it instead.
        result = safe_fetch._normalize_host("")
        assert result == ""


class TestPinnedIPAdapter:
    """_PinnedIPHTTPAdapter.get_connection_with_tls_context -- the actual
    DNS-rebinding/TOCTOU fix. Unit-tested directly against a mocked
    poolmanager, without any real socket/TLS work."""

    def setup_method(self):
        safe_fetch._clear_pin_for_this_thread()

    def teardown_method(self):
        safe_fetch._clear_pin_for_this_thread()

    def _adapter_with_mocks(self, host_params: dict):
        adapter = safe_fetch._PinnedIPHTTPAdapter()
        adapter.poolmanager = MagicMock()
        patcher = patch.object(
            adapter,
            "build_connection_pool_key_attributes",
            return_value=(dict(host_params), {"existing_kwarg": "kept"}),
        )
        patcher.start()
        return adapter, patcher

    def test_pinned_host_match_routes_to_ip_with_sni_on_real_host(self):
        adapter, patcher = self._adapter_with_mocks({"host": "example.com", "port": 443})
        try:
            safe_fetch._pin_ip_for_this_thread("example.com", "93.184.216.34")
            fake_request = MagicMock(url="https://example.com/page")

            with patch(
                "app.utils.safe_fetch.requests.adapters.select_proxy", return_value=None
            ):
                adapter.get_connection_with_tls_context(fake_request, verify=True)

            adapter.poolmanager.connection_from_host.assert_called_once()
            _, kwargs = adapter.poolmanager.connection_from_host.call_args
            assert kwargs["host"] == "93.184.216.34"  # connects to the vetted IP
            assert kwargs["port"] == 443
            assert kwargs["pool_kwargs"]["server_hostname"] == "example.com"
            assert kwargs["pool_kwargs"]["assert_hostname"] == "example.com"
            assert kwargs["pool_kwargs"]["existing_kwarg"] == "kept"
        finally:
            patcher.stop()

    def test_no_pin_falls_back_to_base_behavior(self):
        adapter, patcher = self._adapter_with_mocks({"host": "example.com", "port": 443})
        try:
            # No pin set (setup_method cleared it).
            with patch(
                "app.utils.safe_fetch.requests.adapters.select_proxy", return_value=None
            ):
                adapter.get_connection_with_tls_context(
                    MagicMock(url="https://example.com/"), verify=True
                )

            _, kwargs = adapter.poolmanager.connection_from_host.call_args
            assert kwargs["host"] == "example.com"  # unmodified -- no pin applied
            assert "server_hostname" not in kwargs["pool_kwargs"]
        finally:
            patcher.stop()

    def test_mismatched_host_does_not_use_stale_pin(self):
        # Pinned for a DIFFERENT host than the one actually being
        # requested (e.g. a redirect target not yet separately vetted) --
        # must not connect it to the stale pinned IP.
        adapter, patcher = self._adapter_with_mocks({"host": "other.example.com", "port": 443})
        try:
            safe_fetch._pin_ip_for_this_thread("example.com", "93.184.216.34")
            with patch(
                "app.utils.safe_fetch.requests.adapters.select_proxy", return_value=None
            ):
                adapter.get_connection_with_tls_context(
                    MagicMock(url="https://other.example.com/"), verify=True
                )

            _, kwargs = adapter.poolmanager.connection_from_host.call_args
            assert kwargs["host"] == "other.example.com"  # NOT the stale pinned IP
        finally:
            patcher.stop()

    def test_proxy_configured_falls_back_to_base_behavior(self):
        # The base HTTPAdapter routes a proxied request through a REAL
        # ProxyManager (not adapter.poolmanager), which does real PoolKey
        # construction from pool_kwargs -- mock it too, same as
        # adapter.poolmanager, rather than letting it validate this test's
        # fake pool_kwargs content.
        adapter, patcher = self._adapter_with_mocks({"host": "example.com", "port": 443})
        fake_proxy_manager = MagicMock()
        try:
            safe_fetch._pin_ip_for_this_thread("example.com", "93.184.216.34")
            with patch(
                "app.utils.safe_fetch.requests.adapters.select_proxy",
                return_value="http://proxy.local:8080",
            ), patch.object(adapter, "proxy_manager_for", return_value=fake_proxy_manager):
                adapter.get_connection_with_tls_context(
                    MagicMock(url="https://example.com/"),
                    verify=True,
                    proxies={"https": "http://proxy.local:8080"},
                )

            fake_proxy_manager.connection_from_host.assert_called_once()
            adapter.poolmanager.connection_from_host.assert_not_called()
            _, kwargs = fake_proxy_manager.connection_from_host.call_args
            assert kwargs["host"] == "example.com"  # not pinned through a proxy
        finally:
            patcher.stop()


class TestThreadLocalPin:
    def teardown_method(self):
        safe_fetch._clear_pin_for_this_thread()

    def test_pin_is_thread_local_not_shared(self):
        import threading

        results = {}

        def worker(name, host, ip):
            safe_fetch._pin_ip_for_this_thread(host, ip)
            # A tiny window where another thread could race in, if the
            # pin were shared mutable state instead of thread-local.
            import time as _time

            _time.sleep(0.01)
            results[name] = (safe_fetch._pin_state.host, safe_fetch._pin_state.ip)

        t1 = threading.Thread(target=worker, args=("a", "host-a.example.com", "1.1.1.1"))
        t2 = threading.Thread(target=worker, args=("b", "host-b.example.com", "2.2.2.2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["a"] == ("host-a.example.com", "1.1.1.1")
        assert results["b"] == ("host-b.example.com", "2.2.2.2")

    def test_pin_cleared_after_safe_get_completes(self):
        ok = MagicMock()
        ok.is_redirect = False
        ok.status_code = 200
        ok.headers = {"Content-Type": "text/html"}
        ok.iter_content = lambda chunk_size=8192: [b"ok"]

        with patch(
            "app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")
        ):
            with patch.object(safe_fetch._session, "get", return_value=ok):
                safe_get("https://example.com")

        assert getattr(safe_fetch._pin_state, "host", None) is None

    def test_pin_cleared_even_when_safe_get_raises(self):
        with patch("app.utils.safe_fetch.socket.getaddrinfo", return_value=_addrinfo("10.0.0.5")):
            with pytest.raises(BlockedRequestError):
                safe_get("http://internal.example.com")

        assert getattr(safe_fetch._pin_state, "host", None) is None
