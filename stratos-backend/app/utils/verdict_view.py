# app/utils/verdict_view.py
"""
Shared verdict projection (gap-closing plan Stage 5) -- both the PDF export
(assembler_worker.py's draft) and the web report view
(OrchestratorService.get_report_view) need the same
Report.verdict/verdict_payload -> dict shape, so it lives in one place
rather than being parsed twice with two chances to drift.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def verdict_view(report: Any) -> dict[str, Any] | None:
    """None when the verdict never landed -- verdict_failed is non-fatal
    (Stage 4d) or run_verdict simply hasn't completed yet. Callers must
    treat that as "no verdict to show", not an error."""
    if not report.verdict:
        return None

    payload: dict[str, Any] = {}
    if report.verdict_payload:
        try:
            payload = json.loads(report.verdict_payload)
        except (ValueError, TypeError):
            logger.warning(
                "[VERDICT_VIEW] verdict_payload is not valid JSON for report_id=%s",
                report.id,
            )

    return {
        "verdict": report.verdict,
        "holding": report.verdict_holding,
        "flip_condition": report.flip_condition,
        "confidence": report.verdict_confidence,
        # Full raw draft (case_for_prose, case_against_prose, which_won,
        # etc.) -- payload is the source of truth for anything not already
        # promoted to its own Report column.
        "payload": payload,
    }
