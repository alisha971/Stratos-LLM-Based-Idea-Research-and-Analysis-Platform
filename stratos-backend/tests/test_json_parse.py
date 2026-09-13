from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.llm.json_parse import parse_json_object


def test_parses_plain_json():
    result = parse_json_object('{"a": 1}', label="Test")
    assert result == {"a": 1}


def test_parses_fenced_json():
    raw = '```json\n{"a": 1}\n```'
    result = parse_json_object(raw, label="Test")
    assert result == {"a": 1}


def test_parses_bare_fenced_json():
    raw = '```\n{"a": 1}\n```'
    result = parse_json_object(raw, label="Test")
    assert result == {"a": 1}


def test_parses_json_behind_harmony_preamble():
    raw = '<|channel|>analysis<|message|>thinking...\n{"a": 1}'
    result = parse_json_object(raw, label="Test")
    assert result == {"a": 1}


def test_parses_json_behind_prose_preamble():
    raw = 'Here is the JSON:\n{"a": 1}'
    result = parse_json_object(raw, label="Test")
    assert result == {"a": 1}


def test_raises_value_error_on_truncated_json():
    # A cut-off document -- neither the direct parse nor the greedy extract
    # can recover this; the caller's repair-retry path must still fire.
    raw = '{"chunks": [{"text": "unterminated'
    with pytest.raises(ValueError, match="Test LLM output is not valid JSON"):
        parse_json_object(raw, label="Test")


def test_raises_value_error_on_non_object_json():
    with pytest.raises(ValueError, match="Test LLM output must be a JSON object"):
        parse_json_object("[1, 2, 3]", label="Test")


def test_raises_value_error_on_empty_string():
    with pytest.raises(ValueError, match="Test LLM output is not valid JSON"):
        parse_json_object("", label="Test")
