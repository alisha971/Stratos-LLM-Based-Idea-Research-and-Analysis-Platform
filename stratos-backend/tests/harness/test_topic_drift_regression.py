"""Topic drift regression (gap-closing plan Stage 6 mechanical check): the
permanent guard on the Stage 2e bug -- SECTION_PREFERENCES/OFF_TOPIC_TERMS
used to be a hand-tuned lexicon for one freelancer-tool test idea, applied
to every report since. A healthcare idea's evidence should not need to
mention "upwork"/"fiverr" to rank, and a security idea's evidence should
not be suppressed for legitimately mentioning "crypto"/"dark web"/"malware".

Offline, deterministic, no live Astra/NVIDIA dependency -- this checks the
LEXICAL ranker specifically (EvidenceRanker), since that's the layer the
original bug lived in; hybrid ranking with a fake (empty) semantic side
reduces to the same thing here.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixture_loader import (
    clarified_summary_json,
    evidence_items_for_ranker,
    load_fixture,
    noise_evidence_ids,
    relevance_ground_truth,
    stance_by_source,
)

from app.services.evidence_bundle_service import EvidenceBundleService


class FakeEmbeddingService:
    def find_similar(self, *, report_id, query_text, limit=25):
        return []


def _service() -> EvidenceBundleService:
    return EvidenceBundleService(db=None, embedding_service=FakeEmbeddingService())


class FreelancerVocabularyNoiseTests(unittest.TestCase):
    """meal_prep_residents fixture: ev-9/ev-10 use the exact vocabulary the
    deleted SECTION_PREFERENCES dict was hand-tuned on (Upwork, Fiverr,
    Telegram, Discord, job boards) but are not relevant to any section of
    a meal-prep-for-residents report."""

    def test_freelancer_noise_never_outranks_real_relevant_evidence(self):
        fixture = load_fixture("meal_prep_residents")
        noise_ids = noise_evidence_ids(fixture)
        self.assertTrue(noise_ids)  # sanity: the fixture actually has noise

        service = _service()
        for section_title in fixture["sections"]:
            relevant_ids = relevance_ground_truth(fixture, section_title)
            if not relevant_ids:
                continue

            with self.subTest(section=section_title):
                ranked = service._hybrid_rank_for_section(
                    report_id="r1",
                    clarified_summary=clarified_summary_json(fixture),
                    section_title=section_title,
                    evidence_items=evidence_items_for_ranker(fixture),
                    stance_by_source=stance_by_source(fixture),
                )
                ranked_ids = [item["evidence_id"] for item in ranked]

                # Every relevant item that made it in must rank ahead of
                # every noise item that made it in.
                relevant_ranks = [ranked_ids.index(i) for i in relevant_ids if i in ranked_ids]
                noise_ranks = [ranked_ids.index(i) for i in noise_ids if i in ranked_ids]
                if relevant_ranks and noise_ranks:
                    self.assertLess(max(relevant_ranks), min(noise_ranks))

    def test_relevant_healthcare_evidence_is_not_penalized_for_lacking_freelance_terms(self):
        """The core Stage 2e assertion: a healthcare item's score isn't
        artificially low just because it doesn't mention gig-economy
        vocabulary -- it should still be selected for its own section."""
        fixture = load_fixture("meal_prep_residents")
        service = _service()
        ranked = service._hybrid_rank_for_section(
            report_id="r1",
            clarified_summary=clarified_summary_json(fixture),
            section_title="Problem Context & Validation",
            evidence_items=evidence_items_for_ranker(fixture),
            stance_by_source=stance_by_source(fixture),
        )
        ranked_ids = {item["evidence_id"] for item in ranked}
        relevant_ids = relevance_ground_truth(fixture, "Problem Context & Validation")
        self.assertTrue(relevant_ids & ranked_ids, "no hand-labeled-relevant evidence was selected at all")


class OffTopicTermsRegressionTests(unittest.TestCase):
    """security_platform fixture: ev-1..ev-4 legitimately use vocabulary
    the deleted OFF_TOPIC_TERMS constant used to statically penalize
    (crypto, dark web, malware, threat intelligence). They must rank
    ahead of ev-8, which is genuinely unrelated content."""

    def test_legitimate_security_vocabulary_outranks_genuine_noise(self):
        fixture = load_fixture("security_platform")
        service = _service()

        for section_title in fixture["sections"]:
            relevant_ids = relevance_ground_truth(fixture, section_title)
            if not relevant_ids:
                continue

            with self.subTest(section=section_title):
                ranked = service._hybrid_rank_for_section(
                    report_id="r1",
                    clarified_summary=clarified_summary_json(fixture),
                    section_title=section_title,
                    evidence_items=evidence_items_for_ranker(fixture),
                    stance_by_source=stance_by_source(fixture),
                )
                ranked_ids = [item["evidence_id"] for item in ranked]

                self.assertTrue(
                    set(relevant_ids) & set(ranked_ids),
                    f"no relevant crypto/dark-web/malware evidence selected for {section_title}",
                )
                if "ev-8" in ranked_ids:
                    relevant_ranks = [ranked_ids.index(i) for i in relevant_ids if i in ranked_ids]
                    self.assertLess(max(relevant_ranks), ranked_ids.index("ev-8"))


if __name__ == "__main__":
    unittest.main()
