"""SSRF-guarded HTTP fetcher (security §5).

Every outbound fetch of an internet-supplied URL (research/competitor scraping)
MUST go through :func:`safe_get`. It:

1. Allows only http/https on ports 80/443.
2. Resolves DNS first (with hints, retry, and IDNA/trailing-dot normalization
   -- fix-audit Part 5), filters out any private/reserved/loopback/link-local
   records, and rejects the host only if NO public address remains.
3. PINS the connection to that vetted IP (fix-audit Part 5): the TCP socket
   connects to the vetted address directly, while the Host header and TLS
   SNI/certificate verification still use the original hostname. Previously
   the vetted IP was discarded and `requests` re-resolved DNS independently
   just before connecting -- a live DNS-rebinding/TOCTOU gap between
   validation and connection, on top of doubling DNS query volume.
4. Re-validates (and re-pins) on each redirect (capped at 6 -- raised from 3
   in the 2026-09-14 remediation: real competitor/marketing homepages
   routinely need 4-5 hops (tracker redirect -> www canonicalization ->
   HTTPS upgrade -> CDN), and every hop still gets the FULL validation in
   step 2-3 above, so a longer cap does not weaken the guard -- it only
   gives more legitimate hops a chance to complete) — redirect-to-internal
   is the classic bypass.
5. Caps body size (2 MB), connect timeout (3 s) and read timeout (8 s), and
   requires a text content type.
6. Emits a structured log line for every blocked fetch (intrusion signal),
   and a separately-tagged line for a DNS resolution failure -- the two are
   not the same signal and must not look identical in logs.

Uses one module-level Session (connection pooling) with a custom HTTPAdapter
for the pinning above. The pin itself is thread-local: this module is called
concurrently from ThreadPoolExecutor pools (research_worker.py,
competitor_worker.py), and a shared mutable "pinned IP" on the adapter
would otherwise be a race between threads.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

MAX_BYTES = 2 * 1024 * 1024  # 2 MB
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 8
MAX_REDIRECTS = 6
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}

# Fix-audit Part 5: a single transient gaierror used to permanently drop
# the URL. Two retries with a short pause -- NOT the LLM client's 30s
# backoff -- since a worker thread pool blocking here should not stall for
# long, and a real DNS problem should still surface quickly.
DNS_RESOLUTION_ATTEMPTS = 3
DNS_RETRY_DELAY_SECONDS = 0.3

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class BlockedRequestError(Exception):
    """Raised when a URL is rejected by the SSRF guard."""


def _block(url: str, reason: str, *, tag: str = "SSRF") -> BlockedRequestError:
    # Fix-audit Part 5: DNS failures get their own log tag. A genuine
    # network/resolver problem and an actual security block used to be
    # the identical [SSRF] log line, indistinguishable at a glance.
    logger.warning("[%s] Blocked fetch url=%s reason=%s", tag, url, reason)
    return BlockedRequestError(reason)


def _is_forbidden_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _normalize_host(host: str) -> str:
    """Strip a trailing DNS root dot and IDNA-encode, so a host that
    differs only in ways DNS treats as equivalent can't slip past string
    comparisons/validation done on the raw hostname elsewhere."""
    host = host.rstrip(".")
    try:
        return host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        # Not encodable as IDNA (already ASCII, or genuinely malformed) --
        # fall through with the original; getaddrinfo will reject it if
        # it's truly invalid.
        return host


def _resolve_public_ip(host: str, port: int, url: str) -> str:
    """Resolve `host` and return ONE vetted public IP, else raise.

    Fix-audit Part 5, three changes from the original:
    - Hints (`AF_UNSPEC`/`SOCK_STREAM`, and the real port instead of
      `None`) instead of a hint-less call -- the classic source of
      spurious `gaierror`s under load, since a hint-less lookup makes the
      resolver return every family x socktype x protocol permutation.
    - Retries a transient `gaierror` instead of permanently dropping the
      URL on the first one.
    - Filters out forbidden records instead of rejecting the whole host
      if ANY record is forbidden -- a host with a large mixed A/AAAA
      record set (e.g. a CDN-backed domain) is no longer blocked just
      because one of many records happens to look reserved.
    """
    last_exc: socket.gaierror | None = None
    infos = None
    for attempt in range(DNS_RESOLUTION_ATTEMPTS):
        if attempt:
            time.sleep(DNS_RETRY_DELAY_SECONDS)
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            break
        except socket.gaierror as exc:
            last_exc = exc
            continue

    if infos is None:
        raise _block(url, f"dns_resolution_failed: {last_exc}", tag="DNS")

    public_ips = [info[4][0] for info in infos if not _is_forbidden_ip(info[4][0])]
    if not public_ips:
        raise _block(url, "no_public_address_in_dns_response")

    return public_ips[0]


def _validate_url(url: str) -> tuple[str, str, int]:
    """Returns (original_host, vetted_ip, port) or raises."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise _block(url, f"forbidden_scheme:{parsed.scheme}")

    host = parsed.hostname
    if not host:
        raise _block(url, "missing_host")
    host = _normalize_host(host)

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise _block(url, f"forbidden_port:{port}")

    # If the host is a literal IP, validate it directly -- nothing to pin,
    # the "IP" and the connection target are already the same thing.
    try:
        if _is_forbidden_ip(host):
            raise _block(url, f"forbidden_ip_literal:{host}")
        return host, host, port
    except ValueError:
        pass  # not an IP literal -- resolve DNS

    ip = _resolve_public_ip(host, port, url)
    return host, ip, port


_pin_state = threading.local()


def _pin_ip_for_this_thread(host: str, ip: str) -> None:
    _pin_state.host = host
    _pin_state.ip = ip


def _clear_pin_for_this_thread() -> None:
    _pin_state.host = None
    _pin_state.ip = None


class _PinnedIPHTTPAdapter(HTTPAdapter):
    """Routes the TCP connection to whatever IP is pinned (thread-local,
    see above) for the current request's host, while keeping the Host
    header and TLS SNI/certificate verification against the ORIGINAL
    hostname -- this is what actually closes the DNS-rebinding/TOCTOU gap:
    the address `_validate_url` just vetted is the address that gets
    connected to, not whatever a second, independent DNS lookup returns.

    Falls back to normal (unpinned) behavior whenever a pin isn't
    applicable -- no pin set, a proxy is configured, or the request's host
    doesn't match what was pinned (e.g. mid-redirect before the new hop
    has been separately vetted+pinned) -- rather than ever silently
    connecting a mismatched host to a stale pinned IP.
    """

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        pinned_host = getattr(_pin_state, "host", None)
        pinned_ip = getattr(_pin_state, "ip", None)

        if not pinned_host or not pinned_ip:
            return super().get_connection_with_tls_context(request, verify, proxies, cert)

        proxy = requests.adapters.select_proxy(request.url, proxies)
        if proxy:
            return super().get_connection_with_tls_context(request, verify, proxies, cert)

        host_params, pool_kwargs = self.build_connection_pool_key_attributes(
            request, verify, cert
        )
        if host_params.get("host") != pinned_host:
            return super().get_connection_with_tls_context(request, verify, proxies, cert)

        host_params = dict(host_params)
        host_params["host"] = pinned_ip
        pool_kwargs = dict(pool_kwargs)
        # SNI and certificate-hostname verification stay on the REAL
        # hostname even though the socket connects to the IP -- required
        # for any virtual-hosted HTTPS server (i.e. almost all of them).
        pool_kwargs["server_hostname"] = pinned_host
        pool_kwargs["assert_hostname"] = pinned_host

        return self.poolmanager.connection_from_host(**host_params, pool_kwargs=pool_kwargs)


_session = requests.Session()
_session.mount("http://", _PinnedIPHTTPAdapter())
_session.mount("https://", _PinnedIPHTTPAdapter())


def safe_get(url: str, timeout: tuple[int, int] = (CONNECT_TIMEOUT, READ_TIMEOUT)) -> requests.Response:
    """Fetch `url` through the SSRF guard. Raises `BlockedRequestError`."""
    current_url = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            host, ip, _port = _validate_url(current_url)
            _pin_ip_for_this_thread(host, ip)

            resp = _session.get(
                current_url,
                timeout=timeout,
                headers=_DEFAULT_HEADERS,
                allow_redirects=False,
                stream=True,
            )

            if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                resp.close()
                if not location:
                    raise _block(current_url, "redirect_without_location")
                current_url = requests.compat.urljoin(current_url, location)
                continue

            content_type = resp.headers.get("Content-Type", "")
            if content_type and "text" not in content_type and "html" not in content_type:
                resp.close()
                raise _block(current_url, f"non_text_content_type:{content_type}")

            # Enforce body cap while streaming.
            body = bytearray()
            for chunk in resp.iter_content(chunk_size=8192):
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    resp.close()
                    raise _block(current_url, "body_too_large")

            resp._content = bytes(body)
            return resp

        raise _block(url, "too_many_redirects")
    finally:
        # The pin is single-use, per hop -- never leave a stale pin on
        # this thread for some unrelated later request (through this same
        # session, from the same worker thread) to accidentally match.
        _clear_pin_for_this_thread()
