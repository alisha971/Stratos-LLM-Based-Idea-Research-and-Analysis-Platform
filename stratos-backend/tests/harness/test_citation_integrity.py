"""Citation integrity (gap-closing plan Stage 6 mechanical check): every
marker a bundle assigns must resolve to a real evidence item that was
actually in the input pool -- no fabricated citations, no orphaned
markers, no gaps in the sequence a section writer could misalign against.

Offline, deterministic, no live Astra/NVIDIA dependency.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixture_loader import (
    clarified_summary_json,
    evidence_items_for_ranker,
    list_fixture_names,
    load_fixture,
    stance_by_source,
)

from app.services.evidence_bundle_service import EvidenceBundleService


class FakeEmbeddingService:
    def find_similar(self, *, report_id, query_text, limit=25):
        return []


def _service() -> EvidenceBundleService:
    return EvidenceBundleService(db=None, embedding_service=FakeEmbeddingService())


class CitationIntegrityTests(unittest.TestCase):
    """Runs across every fixture and every one of its declared sections --
    a real regression here means the marker/citation contract broke for
    some shape of input, not one hand-picked case."""

    def test_every_marker_traces_back_to_a_real_evidence_item(self):
        for fixture_name in list_fixture_names():
            fixture = load_fixture(fixture_name)
            valid_evidence_ids = {item["evidence_id"] for item in fixture["evidence_items"]}
            service = _service()

            for section_title in fixture["sections"]:
                with self.subTest(fixture=fixture_name, section=section_title):
                    ranked = service._hybrid_rank_for_section(
                        report_id="r1",
                        clarified_summary=clarified_summary_json(fixture),
                        section_title=section_title,
                        evidence_items=evidence_items_for_ranker(fixture),
                        stance_by_source=stance_by_source(fixture),
                    )
                    for item in ranked:
                        self.assertIn(
                            item["evidence_id"],
                            valid_evidence_ids,
                            msg=f"marker {item.get('marker')} traces to an evidence_id not in the input pool",
                        )

    def test_markers_are_unique_and_sequential(self):
        fixture = load_fixture("meal_prep_residents")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Problem Context & Validation",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        markers = [item["marker"] for item in ranked]
        self.assertEqual(len(markers), len(set(markers)), "duplicate markers assigned")
        self.assertEqual(markers, [f"CIT-{i:03d}" for i in range(1, len(markers) + 1)])

    def test_every_item_has_a_resolvable_source_id(self):
        for fixture_name in list_fixture_names():
            fixture = load_fixture(fixture_name)
            valid_source_ids = {item["source_id"] for item in fixture["evidence_items"]}
            service = _service()

            for section_title in fixture["sections"]:
                with self.subTest(fixture=fixture_name, section=section_title):
                    ranked = service._hybrid_rank_for_section(
                        report_id="r1",
                        clarified_summary=clarified_summary_json(fixture),
                        section_title=section_title,
                        evidence_items=evidence_items_for_ranker(fixture),
                        stance_by_source=stance_by_source(fixture),
                    )
                    for item in ranked:
                        self.assertIn(item["source_id"], valid_source_ids)


if __name__ == "__main__":
    unittest.main()
