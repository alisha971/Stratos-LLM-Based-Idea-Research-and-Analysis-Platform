# app/services/research_join_service.py
"""
Tracks arrival of the three parallel research legs (research / trend /
competitor) for a report, so section writing can wait for all three -- or
proceed after a bounded timeout instead of stalling forever if one leg
never reports back (see stratos-launch-plan Stage 1b).

Backed by Redis, not Postgres: this is transient pipeline-coordination
state that only matters for the few minutes a run is in flight, not report
data, so it doesn't belong in a migration or in models.py.
"""

from __future__ import annotations

import time

from app.utils.redis_pub import redis_client

LEGS = ("research", "trend", "competitor")
_KEY_PREFIX = "research_join:"
# Generous: a run still waiting on this after an hour has bigger problems
# than a stale Redis key, and the key is harmless if it lingers.
_TTL_SECONDS = 3600


def _key(report_id: str) -> str:
    return f"{_KEY_PREFIX}{report_id}"


def record_leg_arrival(report_id: str, leg: str) -> None:
    """Mark `leg` resolved for `report_id` (whether it succeeded or failed --
    callers that hit a `trend_failed`/`competitor_failed` event record arrival
    too, since a definitive failure should unblock the join exactly like a
    real completion, not wait out the full timeout)."""
    if leg not in LEGS:
        return
    key = _key(report_id)
    # HSETNX: the first arrival wins the timestamp. A duplicate/retried
    # event must not reset the join clock.
    redis_client.hsetnx(key, leg, str(time.time()))
    redis_client.expire(key, _TTL_SECONDS)


def _arrived(report_id: str) -> dict[str, float]:
    raw = redis_client.hgetall(_key(report_id))
    return {
        (k.decode() if isinstance(k, bytes) else k): float(v)
        for k, v in raw.items()
    }


def join_ready(report_id: str, timeout_seconds: float = 90.0) -> bool:
    """True once all three legs have resolved, or once the required
    `research` leg resolved at least `timeout_seconds` ago without the
    other two ever showing up."""
    arrived = _arrived(report_id)
    if all(leg in arrived for leg in LEGS):
        return True
    research_at = arrived.get("research")
    if research_at is None:
        return False
    return (time.time() - research_at) >= timeout_seconds


def missing_legs(report_id: str) -> list[str]:
    arrived = _arrived(report_id)
    return [leg for leg in LEGS if leg not in arrived]


def clear(report_id: str) -> None:
    redis_client.delete(_key(report_id))
