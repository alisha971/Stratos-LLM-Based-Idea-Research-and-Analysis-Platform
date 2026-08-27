"""EvidenceRanker tests (gap-closing plan Stage 2e). Pure functions, no
network, no DB.

Covers the actual bug being fixed: SECTION_PREFERENCES/OFF_TOPIC_TERMS used
to be a hand-tuned lexicon for one freelancer-tool test idea, silently
applied to every report since. A healthcare idea got scored against
"upwork"/"fiverr" vocabulary it will never mention, and a fintech/security
idea had its most relevant evidence actively suppressed by a static
"crypto"/"malware" penalty.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evidence_ranker import EvidenceRanker, section_intent


HEALTHCARE_SUMMARY = (
    "A meal-prep app for medical residents who have no time to cook during "
    "long hospital shifts."
)

SECURITY_SUMMARY = (
    "A threat intelligence platform that scans the dark web for leaked "
    "corporate credentials and alerts security teams."
)


class NoHardcodedVocabularyTests(unittest.TestCase):
    """The healthcare idea's own evidence must not be penalized for lacking
    unrelated freelancer-tool vocabulary that no longer exists in the
    ranker at all."""

    def setUp(self):
        self.ranker = EvidenceRanker()

    def test_healthcare_evidence_not_penalized_for_missing_freelance_terms(self):
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "url": "https://example.com/a",
                "domain": "example.com",
                "title": "Resident burnout and nutrition",
                "type": "web",
                "quote": (
                    "Medical residents report severe time scarcity for meal "
                    "preparation during 80-hour work weeks in hospitals."
                ),
            }
        ]
        ranked = self.ranker.rank_for_section(
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertEqual(len(ranked), 1)
        self.assertGreater(ranked[0]["section_relevance_score"], 1.0)

    def test_security_evidence_no_longer_suppressed_by_off_topic_terms(self):
        """Before the fix, OFF_TOPIC_TERMS statically penalized 'crypto',
        'dark web', 'malware', 'threat intelligence' -- the exact
        vocabulary a legitimate security-product report needs."""
        items = [
            {
                "evidence_id": "e1",
                "source_id": "s1",
                "url": "https://example.com/a",
                "domain": "example.com",
                "title": "Dark web credential leaks rising",
                "type": "web",
                "quote": (
                    "Threat intelligence firms report a sharp rise in "
                    "corporate credentials leaked on dark web marketplaces "
                    "this year, exposing employees to malware campaigns."
                ),
            }
        ]
        ranked = self.ranker.rank_for_section(
            clarified_summary=SECURITY_SUMMARY,
            section_title="Market & Industry Trends",
            evidence_items=items,
        )
        self.assertEqual(len(ranked), 1)
        # Would have scored well below 1.0 (base score) under the deleted
        # OFF_TOPIC_TERMS penalty of -1.5 per matched term (3 terms match
        # here: "crypto"->no, "dark web", "malware", "threat intelligence").
        self.assertGreater(ranked[0]["section_relevance_score"], 1.0)

    def test_no_freelance_vocabulary_in_scoring_data(self):
        """Checks the actual data the scorer reads from (SECTION_INTENTS
        values, BOILERPLATE_TERMS) -- not the whole source file, which
        legitimately *mentions* the old vocabulary in a comment explaining
        why it was removed."""
        import app.services.evidence_ranker as module

        scoring_text = " ".join(module.SECTION_INTENTS.values()).lower()
        scoring_text += " ".join(module.BOILERPLATE_TERMS).lower()
        for banned in ("upwork", "fiverr", "toptal", "job board", "high-ticket"):
            self.assertNotIn(banned, scoring_text)

    def test_off_topic_terms_constant_no_longer_exists(self):
        import app.services.evidence_ranker as module

        self.assertFalse(hasattr(module, "OFF_TOPIC_TERMS"))

    def test_section_preferences_constant_no_longer_exists(self):
        import app.services.evidence_ranker as module

        self.assertFalse(hasattr(module, "SECTION_PREFERENCES"))


class SectionIntentTests(unittest.TestCase):
    def test_known_section_returns_topic_neutral_prose(self):
        intent = section_intent("Competitor Landscape")
        self.assertIn("competitors", intent)
        # Must not itself contain domain-specific vocabulary.
        self.assertNotIn("upwork", intent.lower())

    def test_unknown_section_falls_back_to_title(self):
        intent = section_intent("Some Novel LLM-Invented Section")
        self.assertEqual(intent, "Some Novel LLM-Invented Section")

    def test_all_core_and_optional_sections_have_an_intent(self):
        titles = [
            "Problem Context & Validation",
            "Target Users & Personas",
            "Existing Solutions",
            "Competitor Landscape",
            "Market & Industry Trends",
            "Opportunities & Gaps",
            "Risks & Open Questions",
            "Technical Feasibility",
            "Regulatory Considerations",
            "Go-To-Market Strategy",
        ]
        for title in titles:
            self.assertNotEqual(section_intent(title), title, msg=title)


class RankIdsForSectionTests(unittest.TestCase):
    def test_returns_ordered_ids_for_rrf_fusion(self):
        ranker = EvidenceRanker()
        items = [
            {
                "evidence_id": "low",
                "source_id": "s1",
                "quote": "Irrelevant filler text about nothing in particular.",
            },
            {
                "evidence_id": "high",
                "source_id": "s2",
                "quote": (
                    "Medical residents have no time to cook meals during "
                    "hospital shifts and workarounds are limited."
                ),
            },
        ]
        ids = ranker.rank_ids_for_section(
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertEqual(ids[0], "high")

    def test_skips_items_without_id(self):
        ranker = EvidenceRanker()
        items = [{"source_id": "s1", "quote": "Some evidence with no evidence_id set."}]
        ids = ranker.rank_ids_for_section(
            clarified_summary=HEALTHCARE_SUMMARY,
            section_title="Problem Context & Validation",
            evidence_items=items,
        )
        self.assertEqual(ids, [])


if __name__ == "__main__":
    unittest.main()
