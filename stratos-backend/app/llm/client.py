import logging
import time

import groq

from app.llm.client_groq import generate_chat as _groq_call
from app.llm.routing import DEFAULT_ROUTE, TASK_ROUTES

logger = logging.getLogger(__name__)

RETRY_WAIT_SECONDS = 120
_RETRYABLE = groq.APIError  # RateLimitError, APIStatusError, connection/timeout errors


def generate_chat(messages, temperature: float = 0.2, task: str = "default") -> str:
    """
    Bounded retry across two Groq keys: primary -> secondary (immediately) ->
    wait RETRY_WAIT_SECONDS -> primary again -> give up.

    Exactly 3 attempts. No unbounded/exponential retry loop -- a failure here
    is meant to surface immediately, not be silently retried forever.
    """
    route = TASK_ROUTES.get(task, DEFAULT_ROUTE)
    (primary_key, primary_model), (secondary_key, secondary_model) = route[0], route[1]

    # (key_label, model, wait_before_this_attempt)
    attempts = [
        (primary_key, primary_model, 0),
        (secondary_key, secondary_model, 0),
        (primary_key, primary_model, RETRY_WAIT_SECONDS),
    ]

    last_exc: Exception | None = None
    for key_label, model, wait_before in attempts:
        if wait_before:
            logger.warning(
                "[LLM] task=%s both keys failed once; waiting %ss before final retry",
                task,
                wait_before,
            )
            time.sleep(wait_before)
        try:
            return _groq_call(
                messages=messages,
                key_label=key_label,
                model=model,
                temperature=temperature,
            )
        except _RETRYABLE as exc:
            logger.warning("[LLM] task=%s key=%s failed: %s", task, key_label, exc)
            last_exc = exc
            continue

    raise RuntimeError(
        f"LLM generation failed for task={task} after exhausting both Groq keys "
        f"(primary={primary_key}, secondary={secondary_key}): {last_exc}"
    ) from last_exc
