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


def test_non_retryable_error_raises_immediately_without_waiting(monkeypatch):
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

    # Exactly one attempt: the first BadRequestError-style failure must not
    # be retried on the secondary key, nor sleep before giving up.
    assert calls == ["alisha"]
    assert slept == []
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
