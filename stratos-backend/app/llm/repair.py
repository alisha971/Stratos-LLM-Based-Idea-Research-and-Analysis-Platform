# app/llm/repair.py
"""
Shared "generate, then at most one repair attempt" orchestration.

Fix-audit Part 2. Before this module, the exact same shape was copy-pasted
into section_worker.py, verdict_worker.py, clarification_worker.py and
outline_worker.py: try a generate+validate pass, and on a ValueError (bad/
unparseable response) or RuntimeError (generate_chat exhausted both Groq
keys) re-run once with the failure reason appended to the prompt. Every
copy re-sampled the repair attempt at the SAME temperature as the first
attempt, with an otherwise byte-identical prompt -- which made the repair
attempt a near-replay of the exact failure rather than a genuinely
different draft. That is why a section that failed section-quality
validation (pre fix-audit Part 1, when that was still fatal) reproduced
the identical failure on its one retry and the section was dropped.

The fix is not "make the model less deterministic" as a blanket policy --
citation/structural grounding must hold at any temperature, and `validate`
below still enforces it on the repair attempt exactly as on the first.
It is specifically that a *retry* of the *same* request should not be the
*same* request: raising temperature only on the repair attempt is what
makes it an actual second attempt.

Callers keep full ownership of prompt wording (each site's "Regenerate the
full JSON so the {section,verdict,outline,response} is valid." stays
exactly as it was) and of message shape (a single system message for
section/verdict/outline; system prompt + full chat history for
clarification) -- this module only centralizes the retry-and-temperature
orchestration that was identical everywhere.
"""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

BASE_TEMPERATURE = 0.2
# A modest bump, not a big swing: the goal is "not a replay," not "less
# grounded." Citation/structural validation still runs on this attempt.
REPAIR_TEMPERATURE = 0.45


def generate_with_repair(
    *,
    generate: Callable[[str | None, float], T],
    validate: Callable[[T], None] | None = None,
    on_repair: Callable[[str], None] | None = None,
    base_temperature: float = BASE_TEMPERATURE,
    repair_temperature: float = REPAIR_TEMPERATURE,
) -> T:
    """Run `generate(None, base_temperature)`, validate it, and return it.

    On a `ValueError` (bad/unparseable response, or a `validate` failure)
    or `RuntimeError` (generate_chat exhausted both Groq keys), calls
    `on_repair(reason)` for logging/telemetry, then makes exactly one more
    attempt: `generate(reason, repair_temperature)`, validated the same
    way. That second failure is NOT caught here -- it propagates, so the
    caller's own fatal-event handling (section_failed, verdict_failed,
    outline_failed, clarification_failed) fires exactly once, same as
    before this module existed.

    `generate(repair_reason, temperature)` owns building its own prompt
    (appending its own REPAIR REQUIRED wording when `repair_reason` is not
    None) and its own message shape; it must return the parsed result and
    raise `ValueError` itself on a bad/unparseable response.
    """
    try:
        result = generate(None, base_temperature)
        if validate is not None:
            validate(result)
        return result
    except (ValueError, RuntimeError) as exc:
        reason = str(exc)
        if on_repair is not None:
            on_repair(reason)
        result = generate(reason, repair_temperature)
        if validate is not None:
            validate(result)
        return result
