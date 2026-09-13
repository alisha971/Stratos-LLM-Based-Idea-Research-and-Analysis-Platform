# app/services/section_status_service.py
"""
Tracks sections that definitively failed to write, so `handle_section_done`
can treat a report as complete once every section has either produced
chunks or failed -- instead of waiting forever on a section that will never
arrive (gap-closing plan Stage 1 / partial-report survival).

Sibling to research_join_service.py, same reasoning: Redis-backed, not
Postgres, because this is transient pipeline-coordination state that only
matters for the few minutes a run is in flight, not report data. Kept as a
separate module rather than folded into research_join_service.py because
that module's `LEGS` guard (`if leg not in LEGS: return`) is specific to the
three research-fan-out legs and would silently discard section ids if
section tracking were bolted onto it.
"""

from __future__ import annotations

from app.utils.redis_pub import redis_client

_KEY_PREFIX = "section_failed:"
# Same generous window as research_join_service -- a run still waiting on
# this after an hour has bigger problems, and the key is harmless if it
# lingers.
_TTL_SECONDS = 3600


def _key(report_id: str) -> str:
    return f"{_KEY_PREFIX}{report_id}"


def record_section_failed(report_id: str, section_id: str) -> None:
    """Mark `section_id` as definitively failed for `report_id`. HSETNX so
    a retried/duplicate `section_failed` event for the same section can't
    double-count."""
    key = _key(report_id)
    redis_client.hsetnx(key, section_id, "1")
    redis_client.expire(key, _TTL_SECONDS)


def failed_section_ids(report_id: str) -> set[str]:
    raw = redis_client.hgetall(_key(report_id))
    return {(k.decode() if isinstance(k, bytes) else k) for k in raw.keys()}


def clear(report_id: str) -> None:
    redis_client.delete(_key(report_id))
