"""app/llm/client_groq.py -- fix-audit Part 3 added a finish_reason=="length"
warning log at the source of a Groq completion, since truncation there is
the most likely cause of a downstream json_validate_failed/parse failure
several layers up."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import client_groq


def _fake_response(content: str, finish_reason: str):
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def test_returns_stripped_content_on_normal_completion(caplog):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        '  {"ok": true}  ', finish_reason="stop"
    )

    with patch.dict(client_groq._clients, {"alisha": fake_client}):
        result = client_groq.generate_chat(
            messages=[{"role": "system", "content": "hi"}],
            key_label="alisha",
            model="openai/gpt-oss-120b",
        )

    assert result == '{"ok": true}'
    assert "finish_reason=length" not in caplog.text


def test_logs_warning_when_truncated_at_max_tokens(caplog):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        '{"incomplete": "json', finish_reason="length"
    )

    with patch.dict(client_groq._clients, {"alisha": fake_client}):
        with caplog.at_level("WARNING"):
            result = client_groq.generate_chat(
                messages=[{"role": "system", "content": "hi"}],
                key_label="alisha",
                model="openai/gpt-oss-20b",
                max_tokens=768,
            )

    assert result == '{"incomplete": "json'
    assert "finish_reason=length" in caplog.text
    assert "768" in caplog.text
