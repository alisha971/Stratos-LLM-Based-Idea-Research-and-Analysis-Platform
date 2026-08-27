import httpx
import groq
import pytest

from app.llm import client as llm_client


def _api_error(message: str) -> groq.APIError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return groq.APIError(message, request, body=None)


def test_falls_back_to_secondary_key_without_waiting(monkeypatch):
    calls = []

    def fake_groq_call(*, messages, key_label, model, temperature):
        calls.append(key_label)
        if key_label == "encril":
            return '{"ok": true}'
        raise _api_error("primary key rate limited")

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

    def fake_groq_call(*, messages, key_label, model, temperature):
        calls.append(key_label)
        if len(calls) < 3:
            raise _api_error(f"{key_label} failed")
        return '{"ok": true}'

    slept = []
    monkeypatch.setattr(llm_client, "_groq_call", fake_groq_call)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: slept.append(s))

    result = llm_client.generate_chat(
        messages=[{"role": "system", "content": "hi"}],
        task="outline",
    )

    assert result == '{"ok": true}'
    assert calls == ["encril", "alisha", "encril"]
    assert slept == [llm_client.RETRY_WAIT_SECONDS]


def test_raises_descriptive_error_after_exhausting_both_keys(monkeypatch):
    def fake_groq_call(*, messages, key_label, model, temperature):
        raise _api_error(f"{key_label} exhausted")

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
