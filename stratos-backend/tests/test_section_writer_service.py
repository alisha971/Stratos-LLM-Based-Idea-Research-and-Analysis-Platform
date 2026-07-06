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

    def test_rejects_title_drift(self):
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

        with self.assertRaisesRegex(ValueError, "section title|drifts"):
            self.service.validate_section_draft(draft, self.context)

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

        normalized = self.service._normalize_evidence_items(
            items,
            "Competitor Landscape",
            "astra_bundle",
        )
        citation_map = self.service._build_citation_marker_map(normalized)

        self.assertIn("CIT-004", citation_map)
        self.assertEqual(citation_map["CIT-004"]["astra_evidence_id"], "evidence-1")
        self.assertEqual(citation_map["CIT-004"]["source_mode"], "astra_bundle")


if __name__ == "__main__":
    unittest.main()
