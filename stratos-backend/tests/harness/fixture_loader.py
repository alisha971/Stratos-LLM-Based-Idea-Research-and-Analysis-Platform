# tests/harness/fixture_loader.py
"""
Frozen-fixture loader for the gap-closing plan's Stage 6 evaluation harness.

Fixtures live in tests/harness/fixtures/*.json, hand-labeled with ground
truth (which evidence item is relevant to which section, and its stance)
so the harness needs no live SerpAPI/web dependence to run -- see each
fixture's own "_regression_note" for what specific bug it guards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def list_fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))


def evidence_items_for_ranker(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalizes fixture evidence_items into the shape EvidenceRanker /
    EvidenceBundleService expect (the same shape _load_evidence_items
    produces from Postgres/Astra in production)."""
    return [
        {
            "evidence_id": item["evidence_id"],
            "source_id": item["source_id"],
            "url": item.get("url"),
            "domain": item.get("domain"),
            "title": item.get("domain") or item.get("url"),
            "type": "web",
            "quote": item["quote"],
        }
        for item in fixture["evidence_items"]
    ]


def stance_by_source(fixture: dict[str, Any]) -> dict[str, str]:
    return {item["source_id"]: item["stance"] for item in fixture["evidence_items"]}


def relevance_ground_truth(fixture: dict[str, Any], section_title: str) -> set[str]:
    """evidence_ids hand-labeled relevant to this section -- the ground
    truth Precision@k and the topic-drift regression checks score against."""
    return {
        item["evidence_id"]
        for item in fixture["evidence_items"]
        if section_title in item.get("relevant_sections", [])
    }


def noise_evidence_ids(fixture: dict[str, Any]) -> set[str]:
    """evidence_ids relevant to NO section at all -- deliberately irrelevant
    noise (see each fixture's _regression_note)."""
    return {
        item["evidence_id"]
        for item in fixture["evidence_items"]
        if not item.get("relevant_sections")
    }


def clarified_summary_json(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture["clarified_summary"])
