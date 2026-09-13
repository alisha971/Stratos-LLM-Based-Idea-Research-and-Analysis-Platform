from __future__ import annotations

import json
import re
from typing import Any


def parse_json_object(raw_output: str, label: str) -> dict[str, Any]:
    """Parse an LLM JSON object, tolerating a code fence or a reasoning preamble.

    Strips a ```json ... ``` fence (or a bare ``` ... ``` fence), then tries
    `json.loads` directly. If that fails -- e.g. a gpt-oss harmony
    `<|channel|>analysis...<|message|>` preamble or a "Here is the JSON:"
    line precedes the object -- falls back to extracting the first `{...}`
    span, the same regex `clarification_worker` already uses. Does NOT fix a
    truncated document: a genuinely cut-off JSON object still fails both the
    direct parse and the extract, and raises `ValueError` as before so the
    caller's repair-retry path fires.
    """
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"{label} LLM output is not valid JSON")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label} LLM output is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label} LLM output must be a JSON object")
    return data
