# app/utils/degradation.py
"""
Counts every time a pipeline stage falls back to a degraded path instead of
its primary LLM-backed behavior -- a vote-sorted competitor list instead of
LLM relevance ranking, a stance's provenance prior instead of LLM
classification, a templated trend query instead of a generated one, a
dropped embedding chunk, a blocked/failed fetch.

Rationale (fix-audit Part 0): the fallback existing is not the problem --
report generation must survive a flaky LLM call, and every fallback here
stays in place as a genuine last resort. The problem is a fallback firing
being invisible. A vote-sorted competitor list and an LLM-ranked one look
identical in the shipped report; without a count, "the fallback caught it
once" cannot be told apart from "the fallback is now doing the primary
job." This turns every activation into a number the assembler can log and
ship in the export draft, per report, per stage -- so a clean run (empty
tally) is provable rather than inferred from scrollback.

Redis-backed like section_status_service.py, for the same reason: this is
transient per-run pipeline telemetry, not report data that belongs in
Postgres. A HINCRBY counter, not a set -- Rule 3 is "every activation is
counted," not "every distinct reason is counted once." Two batches that
degrade for the identical reason string (e.g. the same validation message)
are still two real activations and must both count.
"""

from __future__ import annotations

import logging

from app.utils.redis_pub import redis_client

logger = logging.getLogger(__name__)

_KEY_PREFIX = "degradation:"
# Same generous window as section_status_service/research_join_service --
# a run still being read after an hour has bigger problems, and the key is
# harmless if it lingers.
_TTL_SECONDS = 3600


def _key(report_id: str) -> str:
    return f"{_KEY_PREFIX}{report_id}"


def record_degradation(report_id: str, stage: str, reason: str) -> None:
    """Count one fallback activation for `stage` on `report_id`.

    `reason` is logged for diagnosis, not used as a dedup key -- see the
    module docstring on why this is a counter, not a set.
    """
    key = _key(report_id)
    redis_client.hincrby(key, stage, 1)
    redis_client.expire(key, _TTL_SECONDS)
    logger.warning(
        "[DEGRADED] report_id=%s stage=%s reason=%s", report_id, stage, reason
    )


def degradation_tally(report_id: str) -> dict[str, int]:
    """`{stage: activation_count}` for this report.

    Empty means a clean run -- the fix-audit's acceptance bar is that no
    fallback should have been needed, not that the fallbacks caught it.
    """
    raw = redis_client.hgetall(_key(report_id))
    return {
        (k.decode() if isinstance(k, bytes) else k): int(v)
        for k, v in raw.items()
    }


def clear(report_id: str) -> None:
    redis_client.delete(_key(report_id))
