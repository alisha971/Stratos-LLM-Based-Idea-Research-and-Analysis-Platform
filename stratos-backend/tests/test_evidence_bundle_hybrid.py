"""Hybrid ranking orchestration tests (gap-closing plan Stage 2f/2g), the
part of EvidenceBundleService that fuses lexical (EvidenceRanker) with
semantic (EmbeddingService) results. Uses a fake EmbeddingService --
no live Astra/NVIDIA dependency -- with the real EvidenceRanker, since
lexical scoring itself is covered separately in test_evidence_ranker.py.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.db.database import Base
from app.services.evidence_bundle_service import BUNDLE_SIZE, EvidenceBundleService

HEALTHCARE_SUMMARY = (
    "A meal-prep app for medical residents who have no time to cook during "
    "long hospital shifts."
)


class FakeEmbeddingService:
    def __init__(self, hits: list[dict] | None = None):
        self.hits = hits or []
        self.calls: list[dict] = []

    def find_similar(self, *, report_id, query_text, limit=25):
        self.calls.append({"report_id": report_id, "query_text": query_text, "limit": limit})
        return self.hits


def _make_service(hits=None):
    embedding_service = FakeEmbeddingService(hits)
    service = EvidenceBundleService(db=None, embedding_service=embedding_service)
    return service, embedding_service


class DegradesToLexicalOnlyTests(unittest.TestCase):
    def test_empty_semantic_results_preserve_lexical_order(self):
        service, embedding_service = _make_service(hits=[])
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "quote": "Irrelevant filler text about nothing at all here.",
            },
            {
                "evidence_id": "e2",
                "source_id": "s2",
                "quote": (
                    "Medical residents have no time to cook meals during "
                    "hospital shifts and workarounds are limited."
                ),
            },
        ]

        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )

        self.assertGreaterEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["evidence_id"], "e2")  # higher lexical score
        self.assertEqual(embedding_service.calls[0]["report_id"], "r1")

    def test_semantic_query_is_section_intent_not_raw_title(self):
        """'Risks & Open Questions' embedded literally would just match
        other section-title-shaped text -- must use the intent prose."""
        service, embedding_service = _make_service(hits=[])
        service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Risks & Open Questions",
            evidence_items=[],
        )
        query = embedding_service.calls[0]["query_text"]
        self.assertNotEqual(query, "Risks & Open Questions")
        self.assertIn("risk", query.lower())


class SemanticOnlyRecallTests(unittest.TestCase):
    def test_item_found_only_by_semantic_search_is_included(self):
        """The whole point of hybrid ranking: a chunk that scored <=0
        lexically (or wasn't in evidence_items at all) but that the
        embedding search found as a strong semantic match must still
        surface."""
        service, _ = _make_service(
            hits=[
                {
                    "_id": "chunk-x",
                    "source_id": "s9",
                    "url": "https://example.com/x",
                    "domain": "example.com",
                    "content_type": "web_chunk",
                    "text": "Hospital shift schedules leave residents no time to shop for groceries.",
                }
            ]
        )
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=[],  # nothing lexical at all
        )
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["source_id"], "s9")
        self.assertEqual(ranked[0]["reason"], "semantic_only")


class SourceCapTests(unittest.TestCase):
    def test_single_source_capped_at_three_chunks(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": f"e{i}",
                "source_id": "same-source",
                "quote": f"Distinct claim number {i} about medical resident scheduling constraints.",
            }
            for i in range(6)
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertLessEqual(len(ranked), 3)

    def test_multiple_sources_not_capped_by_each_other(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": f"e{i}",
                "source_id": f"source-{i}",
                "quote": f"Distinct claim number {i} about medical resident scheduling constraints.",
            }
            for i in range(6)
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertEqual(len(ranked), 6)


class BundleSizeAndMarkerTests(unittest.TestCase):
    def test_never_exceeds_bundle_size(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": f"e{i}",
                "source_id": f"source-{i}",
                "quote": f"Distinct claim number {i} about medical resident scheduling constraints today.",
            }
            for i in range(BUNDLE_SIZE + 10)
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertLessEqual(len(ranked), BUNDLE_SIZE)

    def test_markers_assigned_sequentially(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "quote": "Medical residents have no time to cook during hospital shifts.",
            },
            {
                "evidence_id": "e2",
                "source_id": "s2",
                "quote": "Workarounds for resident meal scheduling remain limited today.",
            },
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        markers = [item["marker"] for item in ranked]
        self.assertEqual(markers, [f"CIT-{i:03d}" for i in range(1, len(markers) + 1)])


class StanceSlotReservationTests(unittest.TestCase):
    """Stage 3f: reserve slots for both argumentative stances before
    filling the rest by fused score, so a lopsided retrieval can't make a
    balanced section impossible."""

    def test_low_scoring_challenges_item_still_included(self):
        service, _ = _make_service(hits=[])
        # Five strong "supports"-leaning items (all neutral stance here,
        # since stance comes from the lookup map, not the text) plus one
        # weak item whose SOURCE is tagged "challenges" in the map.
        items = [
            {
                "evidence_id": f"e{i}",
                "source_id": f"supports-src-{i}",
                "quote": f"Medical residents have severe time scarcity number {i} for cooking meals during shifts.",
            }
            for i in range(5)
        ]
        items.append(
            {
                "evidence_id": "e-weak",
                "source_id": "challenges-src",
                "quote": "Irrelevant filler unrelated to anything in particular here.",
            }
        )
        stance_by_source = {
            **{f"supports-src-{i}": "supports" for i in range(5)},
            "challenges-src": "challenges",
        }

        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
            stance_by_source=stance_by_source,
        )

        ids = [item["evidence_id"] for item in ranked]
        self.assertIn("e-weak", ids)  # included despite the weak lexical score

    def test_reserves_up_to_three_per_stance_when_available(self):
        service, _ = _make_service(hits=[])
        items = []
        for i in range(4):
            items.append(
                {
                    "evidence_id": f"challenges-{i}",
                    "source_id": f"challenges-src-{i}",
                    "quote": f"Distinct challenging claim number {i} about resident scheduling constraints.",
                }
            )
        for i in range(4):
            items.append(
                {
                    "evidence_id": f"supports-{i}",
                    "source_id": f"supports-src-{i}",
                    "quote": f"Distinct supporting claim number {i} about resident scheduling constraints.",
                }
            )
        stance_by_source = {
            **{f"challenges-src-{i}": "challenges" for i in range(4)},
            **{f"supports-src-{i}": "supports" for i in range(4)},
        }

        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
            stance_by_source=stance_by_source,
        )

        stances = [stance_by_source.get(item["source_id"]) for item in ranked]
        self.assertGreaterEqual(stances.count("challenges"), 3)
        self.assertGreaterEqual(stances.count("supports"), 3)

    def test_source_cap_still_enforced_within_stance_slots(self):
        """A single source can't satisfy the whole stance reservation by
        itself beyond the normal per-source cap of 3."""
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": f"e{i}",
                "source_id": "one-source",
                "quote": f"Distinct challenging claim number {i} about the same single source today.",
            }
            for i in range(5)
        ]
        stance_by_source = {"one-source": "challenges"}

        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
            stance_by_source=stance_by_source,
        )
        self.assertLessEqual(len(ranked), 3)  # MAX_CHUNKS_PER_SOURCE

    def test_no_stance_data_falls_back_to_plain_fused_ranking(self):
        """When stance_by_source is empty (no classification happened
        yet, or Astra/DB hiccup), behavior must be identical to plain
        fused-rank selection -- no crash, no artificial reordering."""
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "quote": "Medical residents have no time to cook during hospital shifts.",
            },
            {
                "evidence_id": "e2",
                "source_id": "s2",
                "quote": "Workarounds for resident meal scheduling remain limited today.",
            },
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
            stance_by_source={},
        )
        self.assertEqual(len(ranked), 2)

    def test_fewer_than_three_available_does_not_crash(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "quote": "The single available challenging claim about the idea.",
            },
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
            stance_by_source={"s1": "challenges"},
        )
        self.assertEqual(len(ranked), 1)


class LoadStanceBySourceTests(unittest.TestCase):
    def test_builds_map_from_real_source_rows(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.tables["sources"].create(engine)
        db = sessionmaker(bind=engine)()

        db.add(models.Source(id="s1", report_id="r1", url="https://a.example.com", stance="challenges"))
        db.add(models.Source(id="s2", report_id="r1", url="https://b.example.com", stance="supports"))
        db.add(models.Source(id="s3", report_id="r1", url="https://c.example.com", stance=None))
        db.add(models.Source(id="s4", report_id="other-report", url="https://d.example.com", stance="challenges"))
        db.commit()

        service = EvidenceBundleService(db=db)
        stance_map = service._load_stance_by_source("r1")

        self.assertEqual(stance_map, {"s1": "challenges", "s2": "supports"})
        self.assertNotIn("s3", stance_map)  # null stance omitted, not "None"
        self.assertNotIn("s4", stance_map)  # different report


class FusionJoinKeyTests(unittest.TestCase):
    """Gap-closing plan Stage 5: lexical and semantic hits are fused on a
    real per-chunk id (`_id` from the `embeddings` collection), not a
    180-char text-prefix fingerprint. Two genuinely distinct chunks that
    happen to share their opening ~180 characters -- repeated nav/header
    boilerplate surviving clean_html -- must both survive into the
    candidate pool instead of silently collapsing into one, which is what
    the old fingerprint key did."""

    # 180+ chars of shared leading boilerplate, then a distinct body each.
    _SHARED_PREFIX = (
        "Medical residents working long hospital shifts report they have "
        "almost no time to prepare or eat proper meals during the workday, "
        "and the usual workarounds are widely acknowledged to be inadequate "
        "for sustained clinical performance over time. "
    )

    def test_shared_180_char_prefix_does_not_collapse_distinct_chunks(self):
        lexical_quote = self._SHARED_PREFIX + (
            "A residency-program survey found most trainees skip lunch "
            "entirely and rely on vending machines between rounds, patient "
            "handoffs, and charting blocks that fill every gap in the shift."
        )
        semantic_text = self._SHARED_PREFIX + (
            "Hospital cafeterias close before night-shift residents finish "
            "admissions, so those trainees depend on whatever packaged food "
            "they carried in at the start of a twenty-eight-hour call day."
        )

        service, _ = _make_service(
            hits=[
                {
                    "_id": "chunk-b",
                    "source_id": "s-b",
                    "url": "https://example.com/b",
                    "domain": "example.com",
                    "content_type": "web_chunk",
                    "text": semantic_text,
                }
            ]
        )
        items = [
            {
                "evidence_id": "e-a",
                "_id": "chunk-a",
                "source_id": "s-a",
                "quote": lexical_quote,
            }
        ]

        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )

        source_ids = {item["source_id"] for item in ranked}
        # Under the retired fingerprint key both sides hashed to the same
        # 180-char prefix and fused to one entry -- the semantic-only
        # chunk (s-b) was lost. Joining on `_id` keeps them distinct.
        self.assertEqual(source_ids, {"s-a", "s-b"})


class DiversificationTests(unittest.TestCase):
    def test_near_duplicate_chunks_collapsed(self):
        service, _ = _make_service(hits=[])
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "quote": "Three funded incumbents already own tier-one distribution in the market.",
            },
            {
                "evidence_id": "e2",
                "source_id": "s2",
                "quote": "Three funded incumbents already own tier-one distribution in the market today.",
            },
        ]
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Competitor Landscape",
            evidence_items=items,
        )
        self.assertEqual(len(ranked), 1)


if __name__ == "__main__":
    unittest.main()
