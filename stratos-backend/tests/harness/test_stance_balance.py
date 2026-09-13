"""Stance balance (gap-closing plan Stage 6 mechanical check): every bundle
with both stances available in the evidence pool must contain both -- the
highest-severity failure this harness guards, since a lopsided bundle makes
a balanced case impossible no matter what the section-writer prompt asks
for (see EvidenceBundleService._select_with_stance_slots, Stage 3f).

Offline, deterministic, no live Astra/NVIDIA dependency -- uses a fake
EmbeddingService returning [] (lexical-only ranking), same pattern as
test_evidence_bundle_hybrid.py.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixture_loader import (
    clarified_summary_json,
    evidence_items_for_ranker,
    load_fixture,
    stance_by_source,
)

from app.services.evidence_bundle_service import MIN_ITEMS_PER_STANCE, EvidenceBundleService


class FakeEmbeddingService:
    def find_similar(self, *, report_id, query_text, limit=25):
        return []


def _service() -> EvidenceBundleService:
    return EvidenceBundleService(db=None, embedding_service=FakeEmbeddingService())


class BothStancesAvailableTests(unittest.TestCase):
    """meal_prep_residents and security_platform both have supports AND
    challenges items relevant to at least one section -- those sections'
    bundles must reserve slots for both, not just rank by score."""

    def test_meal_prep_problem_section_has_both_stances(self):
        fixture = load_fixture("meal_prep_residents")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Problem Context & Validation",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        stances = {stance_by_source(fixture).get(i["source_id"]) for i in ranked}
        self.assertIn("supports", stances)
        self.assertIn("challenges", stances)

    def test_meal_prep_competitor_section_has_both_stances(self):
        fixture = load_fixture("meal_prep_residents")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Competitor Landscape",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        stances = {stance_by_source(fixture).get(i["source_id"]) for i in ranked}
        self.assertIn("supports", stances)
        self.assertIn("challenges", stances)

    def test_security_platform_problem_section_has_both_stances(self):
        fixture = load_fixture("security_platform")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Problem Context & Validation",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        stances = {stance_by_source(fixture).get(i["source_id"]) for i in ranked}
        self.assertIn("supports", stances)
        self.assertIn("challenges", stances)


class OneSidedEvidenceDoesNotFabricateTheOtherSideTests(unittest.TestCase):
    """therapist_notetaker has ZERO 'supports' items anywhere -- the bundle
    must reflect that honestly (0 supports), not pad with irrelevant or
    off-stance material to force an artificial balance. This is the input
    the verdict's 'no confident filler' guardrail depends on being true."""

    def test_no_supports_items_are_fabricated(self):
        fixture = load_fixture("therapist_notetaker")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Problem Context & Validation",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        stances = [stance_by_source(fixture).get(i["source_id"]) for i in ranked]
        self.assertNotIn("supports", stances)
        # Real evidence still gets through -- the fixture isn't empty.
        self.assertGreater(len(ranked), 0)

    def test_challenges_slot_still_fills_up_to_the_minimum(self):
        fixture = load_fixture("therapist_notetaker")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Risks & Open Questions",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        stances = [stance_by_source(fixture).get(i["source_id"]) for i in ranked]
        self.assertGreaterEqual(stances.count("challenges"), min(MIN_ITEMS_PER_STANCE, len(ranked)))


if __name__ == "__main__":
    unittest.main()
