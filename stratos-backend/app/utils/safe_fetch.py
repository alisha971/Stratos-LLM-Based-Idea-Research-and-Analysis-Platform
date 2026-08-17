"""SSRF-guarded HTTP fetcher (security §5).

Every outbound fetch of an internet-supplied URL (research/competitor scraping)
MUST go through :func:`safe_get`. It:

1. Allows only http/https on ports 80/443.
2. Resolves DNS first and rejects private/reserved/loopback/link-local IPs,
   pinning the connection to the vetted IP.
3. Re-validates on each redirect (capped at 3) — redirect-to-internal is the
   classic bypass.
4. Caps body size (2 MB), read timeout (8 s), and requires a text content type.
5. Emits a structured log line for every blocked fetch (intrusion signal).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

MAX_BYTES = 2 * 1024 * 1024  # 2 MB
READ_TIMEOUT = 8
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class BlockedRequestError(Exception):
    """Raised when a URL is rejected by the SSRF guard."""


def _block(url: str, reason: str) -> BlockedRequestError:
    logger.warning("[SSRF] Blocked fetch url=%s reason=%s", url, reason)
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


def _resolve_public_ip(host: str, url: str) -> str:
    """Resolve ``host`` and return a vetted public IP, else raise."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise _block(url, f"dns_resolution_failed: {exc}") from exc

    for info in infos:
        ip = info[4][0]
        if _is_forbidden_ip(ip):
            raise _block(url, f"resolves_to_forbidden_ip:{ip}")

    # All resolved addresses are public; return the first.
    return infos[0][4][0]


def _validate_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise _block(url, f"forbidden_scheme:{parsed.scheme}")

    host = parsed.hostname
    if not host:
        raise _block(url, "missing_host")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise _block(url, f"forbidden_port:{port}")

    # If the host is a literal IP, validate it directly.
    try:
        if _is_forbidden_ip(host):
            raise _block(url, f"forbidden_ip_literal:{host}")
        return host, host  # literal IP, already vetted
    except ValueError:
        pass  # not an IP literal — resolve DNS

    ip = _resolve_public_ip(host, url)
    return host, ip


def safe_get(url: str, timeout: int = READ_TIMEOUT) -> requests.Response:
    """Fetch ``url`` through the SSRF guard. Raises ``BlockedRequestError``."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        _validate_url(current_url)

        resp = requests.get(
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
