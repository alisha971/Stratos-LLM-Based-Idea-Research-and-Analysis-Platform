import httpx
import groq
import pytest

from app.llm import client as llm_client
from app.llm.routing import DEFAULT_MAX_TOKENS, MODEL_HEAVY, MODEL_LIGHT, TASK_MAX_TOKENS


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def _retryable_error(message: str) -> groq.RateLimitError:
    request = _request()
    return groq.RateLimitError(
        message, response=httpx.Response(429, request=request), body=None
    )


def _non_retryable_error(message: str) -> groq.BadRequestError:
    request = _request()
    return groq.BadRequestError(
        message, response=httpx.Response(400, request=request), body=None
    )


def test_falls_back_to_secondary_key_without_waiting(monkeypatch):
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        calls.append(key_label)
        if key_label == "encril":
            return '{"ok": true}'
        raise _retryable_error("primary key rate limited")

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    result = llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="section_writer",
    )

    assert result == '{"ok": true}'
    assert calls == ["alisha", "encril"]
    assert slept == []


def test_retries_primary_after_wait_when_both_keys_fail_once(monkeypatch):
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        calls.append(key_label)
        if len(calls) < 3:
            raise _retryable_error(f"{key_label} failed")
        return '{"ok": true}'

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    result = llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="outline",
    )

    assert result == '{"ok": true}'
    # outline is a heavy/structured task under §3 routing -- primary key is
    # now `alisha` (MODEL_HEAVY), not `encril`.
    assert calls == ["alisha", "encril", "alisha"]
    assert slept == [llm_client.RETRY_WAIT_SECONDS]


def test_raises_descriptive_error_after_exhausting_both_keys(monkeypatch):
    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        raise _retryable_error(f"{key_label} exhausted")

    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError) as exc_info:
        llm_client.generate_chat(
            messages=[{"role": "system", "content": "hi"}],
            task="clarification",
        )

    message = str(exc_info.value)
    assert "task=clarification" in message
    assert "encril" in message
    assert "alisha" in message


def test_json_validate_failed_advances_to_secondary_key(monkeypatch):
    # Fix-audit Part 3: json_validate_failed reflects a stochastic
    # decode-shape hiccup (typically truncation, or a gpt-oss harmony
    # preamble the json_object validator rejects), not a structurally
    # invalid request -- the same request against a DIFFERENT key/model
    # can genuinely succeed, so it must fail OVER, not fail OUT on the
    # first attempt. This replaces the old "raises immediately" behavior,
    # which meant a stochastic 20B decode failure never reached the
    # fallback model at all.
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        calls.append(key_label)
        if key_label == "encril":
            return '{"ok": true}'
        raise _non_retryable_error("json_validate_failed")

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    result = llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="section_writer",
    )

    assert result == '{"ok": true}'
    assert calls == ["alisha", "encril"]
    assert slept == []


def test_json_validate_failed_on_both_keys_eventually_exhausts(monkeypatch):
    # Route-retryable does not mean unbounded: with every attempt failing
    # the same way, the third (post-wait) attempt still exhausts normally.
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        calls.append(key_label)
        raise _non_retryable_error("json_validate_failed")

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    with pytest.raises(RuntimeError) as exc_info:
        llm_client.generate_chat(
            messages=[{"role": "system", "content": "hi"}],
            task="section_writer",
        )

    assert calls == ["alisha", "encril", "alisha"]
    assert slept == [llm_client.RETRY_WAIT_SECONDS]
    assert "exhausting both Groq keys" in str(exc_info.value)


def test_genuinely_permanent_bad_request_still_raises_immediately(monkeypatch):
    # A structurally invalid request (bad params, unknown model, input
    # over the context window) fails identically on any key -- this must
    # NOT be treated as route-retryable, unlike json_validate_failed above.
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        calls.append(key_label)
        raise _non_retryable_error("model_not_found")

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    with pytest.raises(RuntimeError) as exc_info:
        llm_client.generate_chat(
            messages=[{"role": "system", "content": "hi"}],
            task="section_writer",
        )

    # Exactly one attempt: a genuinely non-retryable failure must not be
    # retried on the secondary key, nor sleep before giving up.
    assert calls == ["alisha"]
    assert slept == []
    assert "task=section_writer" in str(exc_info.value)
    assert "task=section_writer" in str(exc_info.value)


def test_section_writer_uses_heavy_max_tokens(monkeypatch):
    captured = {}

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        captured["max_tokens"] = max_tokens
        captured["model"] = model
        return '{"ok": true}'

    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)

    llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="section_writer",
    )

    assert captured["max_tokens"] == TASK_MAX_TOKENS["section_writer"]
    assert captured["model"] == MODEL_HEAVY


def test_explicit_max_tokens_overrides_task_default(monkeypatch):
    # Fix-audit Part 0: a caller whose output size scales with its own
    # input (e.g. stance_classification's one-object-per-source batch) must
    # be able to size the budget itself rather than being stuck with the
    # fixed per-task constant that caused the batch-truncation failures.
    captured = {}

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        captured["max_tokens"] = max_tokens
        return '{"ok": true}'

    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)

    llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="stance_classification",
        max_tokens=910,
    )

    # Not DEFAULT_MAX_TOKENS and not any TASK_MAX_TOKENS entry -- proves the
    # explicit value won, not a coincidental default.
    assert captured["max_tokens"] == 910
    assert 910 != DEFAULT_MAX_TOKENS
    assert 910 not in TASK_MAX_TOKENS.values()


def test_research_query_uses_default_max_tokens(monkeypatch):
    captured = {}

    def fake_groq_call(*, messages, key_label, model, temperature, max_tokens):
        captured["max_tokens"] = max_tokens
        captured["model"] = model
        return '{"ok": true}'

    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)

    llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="research_query",
    )

    assert captured["max_tokens"] == DEFAULT_MAX_TOKENS
    assert captured["model"] == MODEL_LIGHT
