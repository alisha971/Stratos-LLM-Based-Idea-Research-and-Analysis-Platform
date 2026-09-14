"""TrendService.generate_queries -- previously untested. Fix-audit Part 0/2
narrowed its except clause, swapped bare json.loads for parse_json_object,
added one repair attempt before the templated fallback, and migrated its
fallback signal from a fire-and-forget research_degraded SSE event (no
subscriber anywhere in the codebase) onto the shared degradation counter."""

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.trend_service import TrendService

SUMMARY = json.dumps({"final_schema": {"project_domain": "healthcare"}})


def _service() -> TrendService:
    return TrendService(
        db=None,
        astra_repository=MagicMock(),
        embedding_service=MagicMock(),
    )


class GenerateQueriesTests(unittest.TestCase):
    def setUp(self):
        self.service = _service()

    def test_missing_summary_raises(self):
        with self.assertRaises(ValueError):
            self.service.generate_queries("")

    @patch("app.services.trend_service.generate_chat")
    def test_happy_path_returns_llm_queries_capped_at_four(self, mock_chat):
        mock_chat.return_value = json.dumps(
            {"queries": [f"query number {i} about the idea" for i in range(6)]}
        )
        queries = self.service.generate_queries(SUMMARY)
        self.assertEqual(len(queries), 4)
        self.assertEqual(mock_chat.call_count, 1)

    @patch("app.services.trend_service.generate_chat")
    def test_uses_point_three_base_temperature(self, mock_chat):
        mock_chat.return_value = json.dumps({"queries": ["a decent trend query here"]})
        self.service.generate_queries(SUMMARY)
        self.assertEqual(mock_chat.call_args.kwargs["temperature"], 0.3)

    @patch("app.utils.degradation.redis_client")
    @patch("app.services.trend_service.generate_chat")
    def test_runtime_error_repairs_once_before_fallback(self, mock_chat, mock_redis):
        mock_chat.side_effect = [
            RuntimeError("Groq down"),
            json.dumps({"queries": ["a recovered trend query here"]}),
        ]
        queries = self.service.generate_queries(SUMMARY, report_id="r1")

        self.assertEqual(queries, ["a recovered trend query here"])
        self.assertEqual(mock_chat.call_count, 2)
        # Second call carries the repair reason and a raised temperature --
        # not a replay of the identical failing request.
        second_kwargs = mock_chat.call_args_list[1].kwargs
        self.assertIn("REPAIR REQUIRED", second_kwargs["messages"][0]["content"])
        self.assertGreater(second_kwargs["temperature"], 0.3)
        mock_redis.hincrby.assert_not_called()

    @patch("app.utils.degradation.redis_client")
    @patch("app.services.trend_service.generate_chat")
    def test_both_attempts_failing_falls_back_and_records_degradation(
        self, mock_chat, mock_redis
    ):
        mock_chat.side_effect = RuntimeError("Groq down")

        queries = self.service.generate_queries(
            SUMMARY, idea_description="a meal-prep app", report_id="r1"
        )

        self.assertEqual(mock_chat.call_count, 2)
        self.assertTrue(all("meal-prep app" in q for q in queries))
        mock_redis.hincrby.assert_called_once_with("degradation:r1", "trend_query_generation", 1)

    @patch("app.utils.degradation.redis_client")
    @patch("app.services.trend_service.generate_chat")
    def test_no_report_id_skips_degradation_recording(self, mock_chat, mock_redis):
        mock_chat.side_effect = RuntimeError("Groq down")

        self.service.generate_queries(SUMMARY, idea_description="idea text")

        mock_redis.hincrby.assert_not_called()

    @patch("app.services.trend_service.generate_chat")
    def test_no_idea_description_uses_last_resort_generic_fallback(self, mock_chat):
        mock_chat.side_effect = RuntimeError("Groq down")
        queries = self.service.generate_queries(SUMMARY)
        self.assertIn("industry trends", queries)

    @patch("app.services.trend_service.generate_chat")
    def test_a_real_bug_in_the_happy_path_is_not_absorbed_as_an_llm_failure(self, mock_chat):
        # Fix-audit Part 0 Rule 2: only ValueError/RuntimeError may be
        # treated as a query-generation failure.
        mock_chat.side_effect = KeyError("not an LLM failure")

        with self.assertRaises(KeyError):
            self.service.generate_queries(SUMMARY)


class FeedTimeoutTests(unittest.TestCase):
    """2026-09-14 remediation Phase 4.7: feedparser.parse(url) has no
    timeout of its own for the URL-string form -- fetch_google_news_rss/
    fetch_arxiv now fetch with a real timeout themselves and hand
    feedparser the already-downloaded bytes instead."""

    def setUp(self):
        self.service = TrendService(db=None)

    @patch("app.services.trend_service._session.get")
    def test_google_news_rss_fetches_with_a_real_timeout(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.content = b"<rss></rss>"

        self.service.fetch_google_news_rss("meal planning")

        self.assertEqual(mock_get.call_args.kwargs["timeout"], 10)

    @patch("app.services.trend_service._session.get")
    def test_google_news_rss_fetch_failure_returns_empty_not_raises(self, mock_get):
        mock_get.side_effect = RuntimeError("connection reset")

        items = self.service.fetch_google_news_rss("meal planning")

        self.assertEqual(items, [])

    @patch("app.services.trend_service._session.get")
    def test_arxiv_fetches_with_a_real_timeout(self, mock_get):
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.content = b"<feed></feed>"

        self.service.fetch_arxiv("meal planning")

        self.assertEqual(mock_get.call_args.kwargs["timeout"], 10)

    @patch("app.services.trend_service._session.get")
    def test_arxiv_fetch_failure_returns_empty_not_raises(self, mock_get):
        mock_get.side_effect = RuntimeError("connection reset")

        items = self.service.fetch_arxiv("meal planning")

        self.assertEqual(items, [])

    @patch("app.services.trend_service._session.get")
    def test_non_200_status_returns_empty_not_raises(self, mock_get):
        import requests

        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("500")

        items = self.service.fetch_google_news_rss("meal planning")

        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
