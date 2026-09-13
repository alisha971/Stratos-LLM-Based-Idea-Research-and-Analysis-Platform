"""ResearchService tests (gap-closing plan Stage 3a/3b/3c/3e). Query
generation and directive seeding are tested with db=None (they never touch
the database); stance classification uses a real in-memory SQLite session
for Source/SourceEvidence, since it genuinely queries them. generate_chat
and publish_event are mocked at their import site in research_service.py --
no live LLM or Redis/Postgres dependency."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import models
from app.db.database import Base
from app.services.research_service import (
    EVIDENCE_RAW_TEXT_MAX_BYTES,
    ResearchService,
    _truncate_utf8_bytes,
)

HEALTHCARE_SUMMARY = json.dumps(
    {
        "final_schema": {"project_domain": "healthcare"},
        "research_directives": [
            "Determine typical pricing for meal-prep subscription apps.",
        ],
    }
)


def _in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.tables["sources"].create(engine)
    Base.metadata.tables["source_evidence"].create(engine)
    Session = sessionmaker(bind=engine)
    return Session()


class GenerateQueriesFallbackTests(unittest.TestCase):
    """Stage 3b: a query-generation failure must degrade to a fallback
    templated from the idea description (not three topic-blind strings),
    and must be flagged via research_degraded, not silent."""

    def setUp(self):
        self.service = ResearchService(db=None)

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_llm_failure_falls_back_to_idea_templated_queries(self, mock_chat, mock_publish):
        mock_chat.side_effect = RuntimeError("Groq 429")

        queries = self.service.generate_queries(
            HEALTHCARE_SUMMARY,
            idea_description="a meal-prep app for medical residents",
            report_id="r1",
        )

        self.assertTrue(all("meal-prep app for medical residents" in q for q in queries))
        self.assertNotIn("existing solutions", queries)  # the old topic-blind fallback

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_failure_publishes_research_degraded(self, mock_chat, mock_publish):
        mock_chat.side_effect = RuntimeError("Groq 429")

        self.service.generate_queries(
            HEALTHCARE_SUMMARY, idea_description="idea text", report_id="r1"
        )

        mock_publish.assert_called_once()
        event_type, payload = mock_publish.call_args[0]
        self.assertEqual(event_type, "research_degraded")
        self.assertEqual(payload["report_id"], "r1")

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_no_report_id_does_not_publish(self, mock_chat, mock_publish):
        mock_chat.side_effect = RuntimeError("Groq 429")
        self.service.generate_queries(HEALTHCARE_SUMMARY, idea_description="idea text")
        mock_publish.assert_not_called()

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_no_idea_description_uses_last_resort_generic_fallback(self, mock_chat, mock_publish):
        mock_chat.side_effect = RuntimeError("Groq 429")
        queries = self.service.generate_queries(HEALTHCARE_SUMMARY, report_id="r1")
        self.assertIn("existing solutions", queries)

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_malformed_json_also_triggers_fallback(self, mock_chat, mock_publish):
        mock_chat.return_value = "not json at all"
        queries = self.service.generate_queries(
            HEALTHCARE_SUMMARY, idea_description="idea text", report_id="r1"
        )
        self.assertTrue(len(queries) > 0)
        mock_publish.assert_called_once()

    @patch("app.services.research_service.generate_chat")
    def test_happy_path_returns_llm_queries_capped_at_five(self, mock_chat):
        mock_chat.return_value = json.dumps(
            {"queries": [f"query number {i} about the idea" for i in range(8)]}
        )
        queries = self.service.generate_queries(HEALTHCARE_SUMMARY, report_id="r1")
        self.assertEqual(len(queries), 5)


class GenerateCounterQueriesTests(unittest.TestCase):
    def setUp(self):
        self.service = ResearchService(db=None)

    @patch("app.services.research_service.generate_chat")
    def test_happy_path_capped_at_three(self, mock_chat):
        mock_chat.return_value = json.dumps(
            {"queries": [f"why this idea fails number {i}" for i in range(6)]}
        )
        queries = self.service.generate_counter_queries(HEALTHCARE_SUMMARY, report_id="r1")
        self.assertEqual(len(queries), 3)

    @patch("app.services.research_service.publish_event")
    @patch("app.services.research_service.generate_chat")
    def test_uses_counter_task_route(self, mock_chat, mock_publish):
        mock_chat.return_value = json.dumps({"queries": ["why this fails badly today"]})
        self.service.generate_counter_queries(HEALTHCARE_SUMMARY, report_id="r1")
        self.assertEqual(mock_chat.call_args.kwargs["task"], "research_query_counter")


class SeedQueriesFromDirectivesTests(unittest.TestCase):
    def setUp(self):
        self.service = ResearchService(db=None)

    def test_extracts_directives_as_query_seeds(self):
        seeds = self.service.seed_queries_from_directives(HEALTHCARE_SUMMARY)
        self.assertEqual(
            seeds, ["Determine typical pricing for meal-prep subscription apps."]
        )

    def test_no_llm_call_involved(self):
        with patch("app.services.research_service.generate_chat") as mock_chat:
            self.service.seed_queries_from_directives(HEALTHCARE_SUMMARY)
            mock_chat.assert_not_called()

    def test_empty_directives_returns_empty_list(self):
        summary = json.dumps({"final_schema": {}, "research_directives": []})
        self.assertEqual(self.service.seed_queries_from_directives(summary), [])

    def test_caps_at_two_seeds(self):
        summary = json.dumps(
            {
                "research_directives": [
                    "Directive one about pricing models here.",
                    "Directive two about target audience here.",
                    "Directive three about distribution channel here.",
                ]
            }
        )
        seeds = self.service.seed_queries_from_directives(summary)
        self.assertEqual(len(seeds), 2)


class ClassifyStanceTests(unittest.TestCase):
    def setUp(self):
        self.db = _in_memory_db()
        self.service = ResearchService(db=self.db)

    def _add_source(self, source_id, quote, stance="neutral"):
        source = models.Source(
            id=source_id,
            report_id="r1",
            url=f"https://example.com/{source_id}",
            domain="example.com",
            type="web",
            stance=stance,
        )
        self.db.add(source)
        self.db.add(models.SourceEvidence(id=f"ev-{source_id}", source_id=source_id, snippet=quote))
        self.db.commit()
        return source

    @patch("app.services.research_service.generate_chat")
    def test_llm_classification_updates_stance_and_rationale(self, mock_chat):
        self._add_source("s1", "Three funded incumbents already own tier-one distribution.")
        mock_chat.return_value = json.dumps(
            {
                "classifications": [
                    {
                        "id": "s1",
                        "stance": "challenges",
                        "rationale": "Incumbent distribution makes entry harder.",
                    }
                ]
            }
        )

        self.service.classify_stance("r1", HEALTHCARE_SUMMARY, ["s1"])

        refreshed = self.db.query(models.Source).filter_by(id="s1").first()
        self.assertEqual(refreshed.stance, "challenges")
        self.assertEqual(refreshed.stance_rationale, "Incumbent distribution makes entry harder.")

    @patch("app.services.research_service.generate_chat")
    def test_classification_failure_keeps_provenance_prior(self, mock_chat):
        self._add_source("s1", "Some quote text here.", stance="challenges")
        mock_chat.side_effect = RuntimeError("Groq down")

        self.service.classify_stance("r1", HEALTHCARE_SUMMARY, ["s1"])

        refreshed = self.db.query(models.Source).filter_by(id="s1").first()
        self.assertEqual(refreshed.stance, "challenges")  # untouched, not dropped

    @patch("app.services.research_service.generate_chat")
    def test_invalid_stance_value_is_ignored(self, mock_chat):
        self._add_source("s1", "Some quote text here.", stance="neutral")
        mock_chat.return_value = json.dumps(
            {"classifications": [{"id": "s1", "stance": "definitely_maybe", "rationale": "x"}]}
        )

        self.service.classify_stance("r1", HEALTHCARE_SUMMARY, ["s1"])

        refreshed = self.db.query(models.Source).filter_by(id="s1").first()
        self.assertEqual(refreshed.stance, "neutral")  # invalid value rejected

    @patch("app.services.research_service.generate_chat")
    def test_unreferenced_id_in_response_is_ignored_not_invented(self, mock_chat):
        self._add_source("s1", "Some quote text here.")
        mock_chat.return_value = json.dumps(
            {
                "classifications": [
                    {"id": "s1", "stance": "supports", "rationale": "ok"},
                    {"id": "not-a-real-id", "stance": "challenges", "rationale": "ignored"},
                ]
            }
        )
        # Must not raise even though "not-a-real-id" isn't in by_id.
        self.service.classify_stance("r1", HEALTHCARE_SUMMARY, ["s1"])
        refreshed = self.db.query(models.Source).filter_by(id="s1").first()
        self.assertEqual(refreshed.stance, "supports")

    def test_empty_source_ids_is_a_noop(self):
        with patch("app.services.research_service.generate_chat") as mock_chat:
            self.service.classify_stance("r1", HEALTHCARE_SUMMARY, [])
            mock_chat.assert_not_called()

    @patch("app.services.research_service.generate_chat")
    def test_batches_at_ten_sources_per_call(self, mock_chat):
        for i in range(15):
            self._add_source(f"s{i}", f"Distinct quote number {i} about the idea.")
        mock_chat.return_value = json.dumps({"classifications": []})

        self.service.classify_stance(
            "r1", HEALTHCARE_SUMMARY, [f"s{i}" for i in range(15)]
        )
        self.assertEqual(mock_chat.call_count, 2)  # 10 + 5


class SaveToAstraArchiveShapeTests(unittest.TestCase):
    """The `evidence` collection indexes every field and Astra rejects any
    indexed string over 8000 bytes (SHRED_DOC_LIMIT_VIOLATION), which was
    failing the archive write for every page longer than ~8 KB. `raw_text`
    must be capped in UTF-8 bytes, and the transient `snippets` list must
    not be persisted inside `metadata` (gap-closing plan Stage 5)."""

    def setUp(self):
        self.service = ResearchService(db=None)

    def _capture_document(self, text, metadata):
        captured = {}
        with patch.object(
            self.service.astra_repository,
            "save_evidence_document",
            side_effect=lambda doc: captured.update(doc) or doc.get("evidence_id"),
        ):
            self.service.save_to_astra(
                report_id="r1",
                source_id="s1",
                url="https://example.com/a",
                text=text,
                metadata=metadata,
            )
        return captured

    def test_raw_text_capped_to_utf8_byte_limit(self):
        long_text = "meal planning for diabetics. " * 5000  # ~140 KB
        doc = self._capture_document(long_text, {"title": "T", "snippets": []})
        self.assertLessEqual(
            len(doc["raw_text"].encode("utf-8")), EVIDENCE_RAW_TEXT_MAX_BYTES
        )
        self.assertTrue(long_text.startswith(doc["raw_text"]))

    def test_short_raw_text_is_untouched(self):
        doc = self._capture_document("short page body", {"snippets": []})
        self.assertEqual(doc["raw_text"], "short page body")

    def test_snippets_not_persisted_in_metadata(self):
        doc = self._capture_document(
            "page body",
            {"title": "T", "domain": "example.com", "snippets": ["chunk one", "chunk two"]},
        )
        self.assertNotIn("snippets", doc["metadata"])
        self.assertEqual(doc["metadata"]["title"], "T")

    def test_truncate_helper_never_splits_a_codepoint(self):
        # A run of 3-byte characters straddling the cut must still decode.
        text = "€" * 4000  # 12 KB
        out = _truncate_utf8_bytes(text, 7801)  # not a multiple of 3
        self.assertLessEqual(len(out.encode("utf-8")), 7801)
        self.assertTrue(text.startswith(out))


if __name__ == "__main__":
    unittest.main()
