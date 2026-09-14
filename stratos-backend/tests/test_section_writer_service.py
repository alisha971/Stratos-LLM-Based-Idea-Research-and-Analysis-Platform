import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.section_writer_service import SectionWriterService


class SectionWriterValidationTests(unittest.TestCase):
    def setUp(self):
        self.service = SectionWriterService(db=None)
        self.context = {
            "section": {
                "title": "Competitor Landscape",
            },
            "outline_titles": [
                "Problem Context & Validation",
                "Competitor Landscape",
                "Market & Industry Trends",
            ],
            "citation_map": {
                "CIT-001": {
                    "source_id": "source-1",
                    "quote": "Competitor A offers onboarding templates.",
                },
                "CIT-002": {
                    "source_id": "source-2",
                    "quote": "Competitor B has usage-based pricing.",
                },
            },
        }

    def test_accepts_title_aligned_cited_chunks(self):
        draft = {
            "section_alignment_summary": (
                "This section explains the competitor landscape through features and pricing."
            ),
            "chunks": [
                {
                    "chunk_index": 1,
                    "text": (
                        "The competitor landscape already includes tools with onboarding "
                        "templates and feature-led positioning [CIT-001]."
                    ),
                    "citations": [
                        {
                            "marker": "CIT-001",
                            "source_id": "source-1",
                            "quote": "Competitor A offers onboarding templates.",
                        }
                    ],
                }
            ],
        }

        self.service.validate_section_draft(draft, self.context)

    def test_total_drift_does_not_raise_but_is_flagged_as_quality_finding(self):
        # Fix-audit Part 1: topical alignment is a quality signal, not a
        # correctness invariant -- a section that is entirely about another
        # outline section's subject must still ship (validate_section_draft
        # must not raise), but assess_section_quality must still surface it
        # for review, naming the competing title.
        draft = {
            "section_alignment_summary": (
                "This section explains market trends and industry adoption."
            ),
            "chunks": [
                {
                    "chunk_index": 1,
                    "text": (
                        "Market trends show industry adoption and growth signals "
                        "in recent news [CIT-001]."
                    ),
                    "citations": [
                        {
                            "marker": "CIT-001",
                            "source_id": "source-1",
                            "quote": "Competitor A offers onboarding templates.",
                        }
                    ],
                }
            ],
        }

        self.service.validate_section_draft(draft, self.context)  # must not raise

        findings = self.service.assess_section_quality(draft, self.context)
        self.assertTrue(
            any("Market & Industry Trends" in f for f in findings),
            findings,
        )

    def test_existing_solutions_style_overlap_is_not_flagged(self):
        # This is the actual production incident (fix-audit context): an
        # honest "Existing Solutions" section necessarily names competing
        # products, pricing and features, which also score on Competitor
        # Landscape's bucket. That proportionate overlap must be silent --
        # neither a validation failure nor a quality finding -- because it
        # is correct writing, not drift.
        context = {
            "section": {"title": "Existing Solutions"},
            "outline_titles": [
                "Existing Solutions",
                "Competitor Landscape",
                "Target Users & Personas",
            ],
            "citation_map": {
                "CIT-001": {"source_id": "source-1", "quote": "Vendor A charges $29/mo."},
            },
        }
        draft = {
            "section_alignment_summary": (
                "This section surveys existing solutions and alternatives already on the market."
            ),
            "chunks": [
                {
                    "chunk_index": 1,
                    "text": (
                        "Several existing products already serve this need: one "
                        "incumbent vendor charges usage-based pricing, while another "
                        "offering targets enterprise customers with a broader feature "
                        "set [CIT-001]. Existing alternatives largely target the same "
                        "users and customers as this idea."
                    ),
                    "citations": [
                        {
                            "marker": "CIT-001",
                            "source_id": "source-1",
                            "quote": "Vendor A charges $29/mo.",
                        }
                    ],
                }
            ],
        }

        self.service.validate_section_draft(draft, context)  # must not raise
        findings = self.service.assess_section_quality(draft, context)
        self.assertEqual(findings, [])

    def test_lopsided_lean_with_some_self_vocabulary_is_still_flagged(self):
        # The quality signal must still be meaningful, not neutered: a
        # section that barely touches its own title's vocabulary while
        # another section's vocabulary clearly dominates is a real lean
        # worth a human's attention, even though it is no longer fatal.
        context = {
            "section": {"title": "Existing Solutions"},
            "outline_titles": ["Existing Solutions", "Competitor Landscape"],
            "citation_map": {
                "CIT-001": {"source_id": "source-1", "quote": "Vendor A charges $29/mo."},
            },
        }
        draft = {
            "section_alignment_summary": "One existing option is on the market today.",
            "chunks": [
                {
                    "chunk_index": 1,
                    "text": (
                        "Competitor A and Competitor B dominate this landscape with "
                        "aggressive pricing and a wide feature set; competitors "
                        "large and small compete on features [CIT-001]."
                    ),
                    "citations": [
                        {
                            "marker": "CIT-001",
                            "source_id": "source-1",
                            "quote": "Vendor A charges $29/mo.",
                        }
                    ],
                }
            ],
        }

        self.service.validate_section_draft(draft, context)  # must not raise
        findings = self.service.assess_section_quality(draft, context)
        self.assertTrue(any("Competitor Landscape" in f for f in findings), findings)

    def test_opportunities_and_gaps_title_gets_its_full_keyword_bucket(self):
        # Fix-audit Part 1 bug fix: "opportunity" is NOT a substring of
        # "opportunities" (they diverge at the 11th character), so the old
        # TITLE_KEYWORDS key silently never matched "Opportunities & Gaps"
        # and it fell through to the generic 2-word {opportunities, gaps}
        # extraction -- too small to ever be picked as a drift target, or
        # to give the section credit for its own vocabulary. The key is
        # now the stem "opportunit", which matches both forms.
        from app.services.section_writer_service import TITLE_KEYWORDS

        keywords = self.service._keywords_for_title("Opportunities & Gaps")
        self.assertEqual(keywords, TITLE_KEYWORDS["opportunit"])
        self.assertIn("differentiation", keywords)  # the real 6-word bucket, not {opportunities, gaps}

    def test_rejects_unknown_citation_marker(self):
        draft = {
            "section_alignment_summary": (
                "This section explains the competitor landscape through features."
            ),
            "chunks": [
                {
                    "chunk_index": 1,
                    "text": "A competitor has a differentiated feature set [CIT-999].",
                    "citations": [
                        {
                            "marker": "CIT-999",
                            "source_id": "source-1",
                            "quote": "Unknown quote.",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "unknown citation marker"):
            self.service.validate_section_draft(draft, self.context)

    def test_rejects_non_sequential_chunk_indexes(self):
        draft = {
            "section_alignment_summary": (
                "This section explains the competitor landscape through features."
            ),
            "chunks": [
                {
                    "chunk_index": 2,
                    "text": "The competitor feature set is already crowded [CIT-001].",
                    "citations": [
                        {
                            "marker": "CIT-001",
                            "source_id": "source-1",
                            "quote": "Competitor A offers onboarding templates.",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "sequential"):
            self.service.validate_section_draft(draft, self.context)

    def test_preserves_astra_bundle_markers(self):
        items = [
            {
                "marker": "CIT-004",
                "evidence_id": "evidence-1",
                "source_id": "source-1",
                "quote": "Competitor A offers onboarding templates.",
            }
        ]

        # _finalize_evidence_items (gap-closing plan Stage 4) replaces
        # _normalize_evidence_items -- it no longer re-ranks by section
        # title (that's EvidenceBundleService's hybrid ranker's job now,
        # and the astra_bundle path is already ranked), so it takes no
        # section_title argument.
        finalized = self.service._finalize_evidence_items(
            items,
            "astra_bundle",
        )
        citation_map = self.service._build_citation_marker_map(finalized)

        self.assertIn("CIT-004", citation_map)
        self.assertEqual(citation_map["CIT-004"]["astra_evidence_id"], "evidence-1")
        self.assertEqual(citation_map["CIT-004"]["source_mode"], "astra_bundle")


if __name__ == "__main__":
    unittest.main()
