import logging
import time

import groq

from app.llm.client_groq import generate_chat as _groq_call
from app.llm.routing import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_ROUTE,
    TASK_MAX_TOKENS,
    TASK_ROUTES,
)

logger = logging.getLogger(__name__)

RETRY_WAIT_SECONDS = 30
_RETRYABLE = (
    groq.RateLimitError,       # 429
    groq.APIConnectionError,   # network / timeout
    groq.InternalServerError,  # 5xx
)

# Fix-audit Part 3: substrings that mark a Groq 400 as a stochastic
# decode-shape hiccup on THIS generation -- typically output truncated at
# max_tokens, or a gpt-oss harmony-format preamble the response_format
# validator rejects -- rather than a structurally invalid request that
# would fail identically on any key/model (bad model id, malformed params,
# input over the context window). The same request re-sent against a
# DIFFERENT key/model can genuinely succeed, which is exactly the
# situation the secondary-key fallback exists for.
_STOCHASTIC_BAD_REQUEST_MARKERS = ("json_validate_failed",)


def _is_stochastic_bad_request(exc: groq.APIError) -> bool:
    if not isinstance(exc, groq.BadRequestError):
        return False

    haystack = str(exc).lower()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            haystack += " " + str(error.get("code") or "").lower()
            haystack += " " + str(error.get("message") or "").lower()

    return any(marker in haystack for marker in _STOCHASTIC_BAD_REQUEST_MARKERS)


def generate_chat(
    messages,
    temperature: float = 0.2,
    task: str = "default",
    max_tokens: int | None = None,
) -> str:
    """
    Bounded retry across two Groq keys: primary -> secondary (immediately) ->
    wait RETRY_WAIT_SECONDS -> primary again -> give up.

    Exactly 3 attempts. No unbounded/exponential retry loop -- a failure here
    is meant to surface immediately, not be silently retried forever.

    `max_tokens`, when passed, overrides the per-task default from
    routing.py. Fix-audit Part 0: a caller whose output size scales with its
    own input (e.g. one JSON object per item in a batch) must size the
    budget to that batch instead of a fixed per-task constant -- a
    per-task-only budget is what turned batch-scaled truncation into a
    routine `json_validate_failed`.
    """
    route = TASK_ROUTES.get(task, DEFAULT_ROUTE)
    primary_key, primary_model = route[0]
    if max_tokens is None:
        max_tokens = TASK_MAX_TOKENS.get(task, DEFAULT_MAX_TOKENS)

    # (key_label, model, wait_before_this_attempt): try every route member
    # once in order, then retry the PRIMARY one more time after a wait.
    # 2026-09-14 remediation Phase 3.3.e: generalized from a hardcoded
    # route[0], route[1] 2-entry unpack so a route can name N members --
    # for today's 2-entry Groq routes this produces the IDENTICAL 3-step
    # sequence as before (verified byte-for-byte by tests/test_llm_client.py,
    # which this change must not alter the observable behavior of); a
    # route with N members produces N+1 attempts. No task's route is
    # actually longer than 2 yet -- see app/llm/client_federated.py for
    # the new scheduler-backed dispatch that a task opts into once a
    # multi-provider route is actually wired up.
    attempts = [(key, model, 0) for key, model in route]
    attempts.append((primary_key, primary_model, RETRY_WAIT_SECONDS))

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
                max_tokens=max_tokens,
            )
        except _RETRYABLE as exc:
            logger.warning("[LLM] task=%s key=%s failed: %s", task, key_label, exc)
            last_exc = exc
            continue
        except groq.APIError as exc:
            if _is_stochastic_bad_request(exc):
                # Route-retryable, not permanent (fix-audit Part 3): advance
                # to the next (key, model) attempt instead of raising --
                # this is the fix for json_validate_failed never reaching
                # the fallback model, leaving worker-level repair as the
                # only recovery and re-entering through the same route.
                logger.warning(
                    "[LLM] task=%s key=%s stochastic bad request, "
                    "advancing to next attempt: %s",
                    task,
                    key_label,
                    exc,
                )
                last_exc = exc
                continue
            # Genuinely non-transient (e.g. malformed params, unknown
            # model, context-length-exceeded on input): the identical
            # request would fail identically on any key, so don't burn the
            # remaining attempts or the retry sleep. Re-raise as
            # RuntimeError so callers (worker repair-retry logic) have a
            # single exception type to catch regardless of why
            # generate_chat failed.
            logger.warning(
                "[LLM] task=%s key=%s non-retryable failure: %s", task, key_label, exc
            )
            raise RuntimeError(
                f"LLM generation failed for task={task} (key={key_label}, "
                f"non-retryable): {exc}"
            ) from exc

    attempted_labels = [key for key, _ in route]
    raise RuntimeError(
        f"LLM generation failed for task={task} after exhausting both Groq "
        f"keys (attempted={attempted_labels}): {last_exc}"
    ) from last_exc
