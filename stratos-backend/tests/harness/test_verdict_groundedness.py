"""Verdict groundedness (gap-closing plan Stage 6 mechanical check): the
verdict cites only markers that trace back to real, fixture-backed
evidence -- never a fabricated one -- and refuses to validate a draft that
cites nothing at all (the "confident filler with zero grounding" guard).

This deliberately does NOT try to mechanically judge whether a verdict's
prose is "persuasive" or its confidence level is well-calibrated -- that's
prompt-guardrail territory (VERDICT_PROMPT's CASE AGAINST GUARDRAIL / NO
CONFIDENT FILLER sections), not something a marker-based validator can or
should enforce. What IS mechanically checkable, and is what this file
checks: the marker_map the harness's fixtures produce is honestly
stance-representative (see test_stance_balance.py) and validate_verdict_
draft actually rejects a fabricated marker against it.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixture_loader import load_fixture

from app.services.verdict_service import VerdictService


def _marker_map_from_fixture(fixture: dict) -> dict[str, dict]:
    """Mirrors what VerdictService.build_verdict_context assembles from a
    finished report's own citations -- marker -> source_id/stance/quote --
    built here directly from the fixture's evidence items instead of a
    live Postgres section/chunk/citation chain."""
    marker_map = {}
    for index, item in enumerate(fixture["evidence_items"], start=1):
        marker_map[f"CIT-{index:03d}"] = {
            "source_id": item["source_id"],
            "stance": item["stance"],
            "url": item.get("url"),
            "quote": item["quote"],
        }
    return marker_map


def _draft(**overrides) -> dict:
    draft = {
        "verdict": "reshape",
        "holding": "Go, with a specific pivot.",
        "case_for_prose": "Demand is real [CIT-001].",
        "case_against_prose": "There is a real obstacle [CIT-002].",
        "which_won": "The obstacle outweighs the demand [CIT-002].",
        "flip_condition": "If a specific, checkable thing happened.",
        "confidence": "medium",
    }
    draft.update(overrides)
    return draft


class VerdictGroundednessTests(unittest.TestCase):
    def setUp(self):
        self.service = VerdictService(db=None)

    def test_accepts_a_draft_grounded_in_real_fixture_markers(self):
        fixture = load_fixture("meal_prep_residents")
        context = {"marker_map": _marker_map_from_fixture(fixture)}
        self.service.validate_verdict_draft(_draft(), context)  # must not raise

    def test_rejects_a_fabricated_marker_not_in_any_fixture_evidence(self):
        fixture = load_fixture("meal_prep_residents")
        context = {"marker_map": _marker_map_from_fixture(fixture)}
        draft = _draft(case_for_prose="Demand is real [CIT-999].")
        with self.assertRaisesRegex(ValueError, "not present"):
            self.service.validate_verdict_draft(draft, context)

    def test_rejects_a_draft_citing_no_evidence_at_all(self):
        fixture = load_fixture("meal_prep_residents")
        context = {"marker_map": _marker_map_from_fixture(fixture)}
        draft = _draft(
            case_for_prose="Demand is real.",
            case_against_prose="There is a real obstacle.",
            which_won="The obstacle outweighs the demand.",
        )
        with self.assertRaisesRegex(ValueError, "no evidence markers"):
            self.service.validate_verdict_draft(draft, context)

    def test_grounds_correctly_against_the_one_sided_fixture_too(self):
        """therapist_notetaker has zero 'supports' markers -- a verdict
        that only cites the 'challenges' markers it actually has must
        still validate cleanly; the validator doesn't require both
        stances to be cited, only that whatever IS cited is real."""
        fixture = load_fixture("therapist_notetaker")
        context = {"marker_map": _marker_map_from_fixture(fixture)}
        draft = _draft(
            case_for_prose="The research did not surface a strong case for [CIT-001].",
            case_against_prose="Compliance burden and incumbent bundling are real obstacles [CIT-001][CIT-002].",
            which_won="Absent real supporting evidence, the case against wins by default [CIT-002].",
            confidence="low",
        )
        self.service.validate_verdict_draft(draft, context)  # must not raise


if __name__ == "__main__":
    unittest.main()
