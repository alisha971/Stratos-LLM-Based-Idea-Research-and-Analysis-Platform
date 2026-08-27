import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.competitor_service import CompetitorService
from app.utils.safe_fetch import BlockedRequestError


class FakeResponse:
    def __init__(self, status_code=200, text="", url="https://example.com"):
        self.status_code = status_code
        self.text = text
        self.url = url


class FakeAstraRepository:
    """Records what would have been written, always reports enabled."""

    def __init__(self, enabled=True):
        self.saved = []
        self.enabled = enabled

    def save_competitor_insight(self, document):
        self.saved.append(document)
        return document.get("insight_id")


class FakeDb:
    """Minimal stand-in for a SQLAlchemy Session: records adds, no-ops flush/commit."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        pass


LONG_HOMEPAGE_TEXT = "Welcome to our product. " * 20  # > 200 chars


class VerificationTests(unittest.TestCase):
    """The anti-hallucination wall: a candidate must be dropped, never
    profiled or persisted, unless a real homepage fetch succeeds."""

    def setUp(self):
        self.service = CompetitorService(db=None)

    @patch("app.services.competitor_service.safe_get")
    def test_drops_candidate_on_non_200(self, mock_safe_get):
        mock_safe_get.return_value = FakeResponse(status_code=404)

        resolved_url, homepage_text, pricing_text = self.service.verify(
            {"url": "https://dead-product.example.com"}
        )

        self.assertIsNone(resolved_url)
        self.assertIsNone(homepage_text)

    @patch("app.services.competitor_service.safe_get")
    def test_drops_candidate_on_blocked_request(self, mock_safe_get):
        mock_safe_get.side_effect = BlockedRequestError("resolves_to_forbidden_ip:127.0.0.1")

        resolved_url, homepage_text, pricing_text = self.service.verify(
            {"url": "https://internal.example.com"}
        )

        self.assertIsNone(resolved_url)
        self.assertIsNone(homepage_text)

    @patch("app.services.competitor_service.safe_get")
    def test_drops_candidate_with_no_extractable_text(self, mock_safe_get):
        mock_safe_get.return_value = FakeResponse(status_code=200, text="<html></html>")

        resolved_url, homepage_text, pricing_text = self.service.verify(
            {"url": "https://js-only-app.example.com"}
        )

        self.assertIsNone(resolved_url)
        self.assertIsNone(homepage_text)

    @patch("app.services.competitor_service.safe_get")
    def test_resolves_redirect_and_extracts_text(self, mock_safe_get):
        homepage_html = f"<html><body>{LONG_HOMEPAGE_TEXT}</body></html>"

        def side_effect(url, *args, **kwargs):
            if url.endswith("/pricing"):
                return FakeResponse(status_code=404, text="")
            # Product Hunt's website field is a /r/ redirect; safe_get
            # follows it and resp.url carries the final homepage.
            return FakeResponse(
                status_code=200,
                text=homepage_html,
                url="https://real-product.example.com",
            )

        mock_safe_get.side_effect = side_effect

        resolved_url, homepage_text, pricing_text = self.service.verify(
            {"url": "https://producthunt.com/r/abc123"}
        )

        self.assertEqual(resolved_url, "https://real-product.example.com")
        self.assertIn("Welcome to our product", homepage_text)
        self.assertIsNone(pricing_text)

    def test_missing_url_is_dropped(self):
        resolved_url, homepage_text, pricing_text = self.service.verify({})
        self.assertIsNone(resolved_url)


class DedupeTests(unittest.TestCase):
    def setUp(self):
        self.service = CompetitorService(db=None)

    def test_dedupe_candidates_collapses_exact_duplicates(self):
        items = [
            {"name": "Acme", "url": "https://acme.example.com/", "provider": "show_hn"},
            {"name": "acme", "url": "https://acme.example.com", "provider": "product_hunt"},
            {"name": "Other", "url": "https://other.example.com", "provider": "show_hn"},
        ]

        deduped = self.service.dedupe_candidates(items)

        self.assertEqual(len(deduped), 2)
        names = {c["name"].lower() for c in deduped}
        self.assertEqual(names, {"acme", "other"})

    def test_dedupe_candidates_drops_incomplete_entries(self):
        items = [
            {"name": "", "url": "https://acme.example.com"},
            {"name": "Acme", "url": ""},
            {"name": "Acme", "url": "https://acme.example.com"},
        ]

        deduped = self.service.dedupe_candidates(items)

        self.assertEqual(len(deduped), 1)

    def test_dedupe_by_domain_collapses_ph_and_hn_hits_of_same_product(self):
        verified = [
            {
                "name": "Acme (Show HN)",
                "resolved_url": "https://www.acme.example.com/",
                "votes": 40,
            },
            {
                "name": "Acme",
                "resolved_url": "https://acme.example.com/landing",
                "votes": 120,
            },
        ]

        deduped = self.service.dedupe_by_domain(verified)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["votes"], 120)

    def test_dedupe_by_domain_keeps_distinct_products(self):
        verified = [
            {"name": "Acme", "resolved_url": "https://acme.com", "votes": 10},
            {"name": "Beta", "resolved_url": "https://beta.io", "votes": 5},
        ]

        deduped = self.service.dedupe_by_domain(verified)

        self.assertEqual(len(deduped), 2)


class RelevanceFilterTests(unittest.TestCase):
    def setUp(self):
        self.service = CompetitorService(db=None)
        self.candidates = [
            {"id": "a", "name": "Acme", "tagline": "t1", "url": "https://a.example.com", "votes": 5},
            {"id": "b", "name": "Beta", "tagline": "t2", "url": "https://b.example.com", "votes": 50},
            {"id": "c", "name": "Gamma", "tagline": "t3", "url": "https://c.example.com", "votes": 20},
        ]

    def test_empty_candidates_short_circuits(self):
        self.assertEqual(self.service.filter_relevant("idea", [], pool_size=5), [])

    @patch("app.services.competitor_service.generate_chat")
    def test_uses_llm_ranked_ids(self, mock_generate_chat):
        mock_generate_chat.return_value = json.dumps({"relevant_ids": ["b", "a"]})

        ranked = self.service.filter_relevant("idea", self.candidates, pool_size=5)

        self.assertEqual([c["id"] for c in ranked], ["b", "a"])

    @patch("app.services.competitor_service.generate_chat")
    def test_falls_back_to_vote_sort_on_llm_failure(self, mock_generate_chat):
        mock_generate_chat.side_effect = RuntimeError("LLM unavailable")

        ranked = self.service.filter_relevant("idea", self.candidates, pool_size=2)

        self.assertEqual([c["id"] for c in ranked], ["b", "c"])

    @patch("app.services.competitor_service.generate_chat")
    def test_falls_back_on_unknown_ids(self, mock_generate_chat):
        mock_generate_chat.return_value = json.dumps({"relevant_ids": ["nonexistent"]})

        ranked = self.service.filter_relevant("idea", self.candidates, pool_size=2)

        self.assertEqual([c["id"] for c in ranked], ["b", "c"])


class ProfileGroundingTests(unittest.TestCase):
    """Guessed pricing is the failure mode to design against: with no
    pricing info in the source text, pricing_model must stay null."""

    def setUp(self):
        self.service = CompetitorService(db=None)

    @patch("app.services.competitor_service.generate_chat")
    def test_null_pricing_survives_when_unsupported(self, mock_generate_chat):
        mock_generate_chat.return_value = json.dumps(
            {
                "name": "Acme",
                "tagline": "Does things",
                "target_customer": None,
                "key_features": ["feature one"],
                "pricing_model": None,
                "pricing_signal": None,
                "differentiators": [],
            }
        )

        for _ in range(3):
            profile = self.service.profile(
                {"name": "Acme", "tagline": "Does things"},
                homepage_text="Acme helps you do things. No pricing mentioned anywhere.",
                pricing_text=None,
            )
            self.assertIsNone(profile["pricing_model"])
            self.assertIsNone(profile["pricing_signal"])

    @patch("app.services.competitor_service.generate_chat")
    def test_llm_failure_falls_back_to_minimal_ungrounded_profile(self, mock_generate_chat):
        mock_generate_chat.side_effect = RuntimeError("LLM unavailable")

        profile = self.service.profile(
            {"name": "Acme", "tagline": "Does things"},
            homepage_text="irrelevant",
            pricing_text=None,
        )

        self.assertEqual(profile["name"], "Acme")
        self.assertIsNone(profile["pricing_model"])
        self.assertEqual(profile["key_features"], [])


class PersistenceShapeTests(unittest.TestCase):
    """Competitor evidence is only citable if it lands on a real Postgres
    Source row, and only surfaced to the section writer if the Astra doc
    carries the keys _flatten_evidence_documents / the normalizer read."""

    def setUp(self):
        self.db = FakeDb()
        self.astra = FakeAstraRepository()
        self.service = CompetitorService(db=self.db, astra_repository=self.astra)

    def test_persist_postgres_links_competitor_to_a_real_source(self):
        entries = [
            {
                "id": "x1",
                "name": "Acme",
                "resolved_url": "https://acme.example.com",
                "domain": "acme.example.com",
                "profile": {
                    "name": "Acme",
                    "tagline": "Does things",
                    "target_customer": "SMBs",
                    "key_features": ["feature one", "feature two"],
                    "pricing_model": "subscription",
                    "pricing_signal": "$10/mo",
                    "differentiators": ["faster onboarding"],
                },
            }
        ]

        persisted = self.service.persist_postgres("report-1", entries)

        self.assertEqual(len(persisted), 1)
        source_ids = {obj.id for obj in self.db.added if type(obj).__name__ == "Source"}
        competitors = [obj for obj in self.db.added if type(obj).__name__ == "Competitor"]
        features = [obj for obj in self.db.added if type(obj).__name__ == "CompetitorFeature"]

        self.assertEqual(len(competitors), 1)
        self.assertIn(competitors[0].source_id, source_ids)
        self.assertEqual(persisted[0]["source_id"], competitors[0].source_id)
        # key_features (2) + differentiators (1)
        self.assertEqual(len(features), 3)

    def test_persist_astra_doc_matches_evidence_pipeline_shape(self):
        entries = [
            {
                "id": "x1",
                "name": "Acme",
                "resolved_url": "https://acme.example.com",
                "domain": "acme.example.com",
                "profile": {
                    "name": "Acme",
                    "tagline": "Does things",
                    "target_customer": "SMBs",
                    "key_features": ["feature one"],
                    "pricing_model": "subscription",
                    "pricing_signal": "$10/mo",
                    "differentiators": [],
                },
            }
        ]
        persisted = self.service.persist_postgres("report-1", entries)

        saved_count = self.service.persist_astra("report-1", persisted)

        self.assertEqual(saved_count, 1)
        doc = self.astra.saved[0]
        # Keys section_writer_service._normalize_evidence_items /
        # _flatten_evidence_documents-style consumers read.
        for key in ("source_id", "url", "domain", "title", "type", "text", "quote"):
            self.assertIn(key, doc)
        self.assertTrue(doc["source_id"])
        self.assertEqual(doc["type"], "competitor")

    def test_persist_astra_skips_when_disabled(self):
        disabled_astra = FakeAstraRepository(enabled=False)
        service = CompetitorService(db=self.db, astra_repository=disabled_astra)

        saved_count = service.persist_astra("report-1", [])

        self.assertEqual(saved_count, 0)


class DegradationTests(unittest.TestCase):
    """PRODUCT_HUNT_TOKEN unset must silently skip that channel, never fail."""

    @patch("app.services.competitor_service.settings")
    def test_fetch_product_hunt_returns_empty_without_token(self, mock_settings):
        mock_settings.PRODUCT_HUNT_TOKEN = None
        service = CompetitorService(db=None)

        result = service.fetch_product_hunt("crm")

        self.assertEqual(result, [])


class FallbackKeywordTests(unittest.TestCase):
    def test_fallback_keywords_are_deterministic_and_non_empty(self):
        from app.services.competitor_service import _fallback_keywords

        keywords = _fallback_keywords("An AI notetaker for sales calls and meetings")
        self.assertTrue(keywords)
        self.assertEqual(keywords, _fallback_keywords("An AI notetaker for sales calls and meetings"))

    def test_fallback_keywords_never_empty(self):
        from app.services.competitor_service import _fallback_keywords

        self.assertEqual(_fallback_keywords(""), ["software tools"])


if __name__ == "__main__":
    unittest.main()
