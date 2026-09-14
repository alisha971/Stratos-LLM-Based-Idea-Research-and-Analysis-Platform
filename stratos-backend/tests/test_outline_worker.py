"""Fix-audit Part 2: outline_worker had the same duplicated generate+parse
retry shape as section_worker.py/verdict_worker.py/clarification_worker.py,
now migrated onto the shared app/llm/repair.py helper, but had no test
coverage of its own before this. Mirrors test_clarification_worker_retry.py
(mocks generate_chat directly, since outline_worker calls it itself rather
than through a service object)."""

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models
from app.llm.repair import BASE_TEMPERATURE, REPAIR_TEMPERATURE
from app.workers import outline_worker


def _report():
    return models.Report(id="r1", session_id="s1", topic="An idea")


def _session():
    session_obj = models.Session(id="s1", user_id="u1")
    session_obj.clarified_summary = json.dumps({"final_schema": {"project_domain": "x"}})
    return session_obj


def _valid_outline():
    return json.dumps({"sections": ["Technical Feasibility"]})


class RunOutlineRetryTests(unittest.TestCase):
    def setUp(self):
        self.fake_db = mock.MagicMock()
        fake_query = mock.MagicMock()
        self.fake_db.query.return_value = fake_query
        fake_query.filter_by.return_value = fake_query
        # First .first() call resolves the report, second resolves the
        # session -- matching the two sequential queries in run_outline.
        fake_query.first.side_effect = [_report(), _session()]

        self.published = []

        self.db_patch = mock.patch.object(
            outline_worker, "SessionLocal", return_value=self.fake_db
        )
        self.publish_patch = mock.patch.object(
            outline_worker,
            "publish_event",
            side_effect=lambda t, p: self.published.append((t, p)),
        )
        self.db_patch.start()
        self.publish_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.publish_patch.stop)

    def _event_names(self):
        return [name for name, _ in self.published]

    def test_runtime_error_then_success_retries_once_no_failure_event(self):
        with mock.patch.object(
            outline_worker,
            "generate_chat",
            side_effect=[RuntimeError("both Groq keys exhausted"), _valid_outline()],
        ) as mock_generate:
            outline_worker.run_outline.run("r1")

        self.assertEqual(mock_generate.call_count, 2)
        first_kwargs = mock_generate.call_args_list[0].kwargs
        self.assertEqual(first_kwargs["temperature"], BASE_TEMPERATURE)
        _, second_kwargs = mock_generate.call_args_list[1]
        self.assertIn("REPAIR REQUIRED", second_kwargs["messages"][0]["content"])
        self.assertEqual(second_kwargs["temperature"], REPAIR_TEMPERATURE)
        self.assertNotIn("outline_failed", self._event_names())
        self.assertIn("outline_ready", self._event_names())

    def test_runtime_error_twice_fires_outline_failed_once(self):
        with mock.patch.object(
            outline_worker,
            "generate_chat",
            side_effect=[
                RuntimeError("both Groq keys exhausted"),
                RuntimeError("both Groq keys exhausted again"),
            ],
        ) as mock_generate:
            with self.assertRaises(RuntimeError):
                outline_worker.run_outline.run("r1")

        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(self._event_names().count("outline_failed"), 1)
        self.assertNotIn("outline_ready", self._event_names())

    def test_malformed_json_also_retries_once(self):
        with mock.patch.object(
            outline_worker,
            "generate_chat",
            side_effect=["not json at all", _valid_outline()],
        ) as mock_generate:
            outline_worker.run_outline.run("r1")

        self.assertEqual(mock_generate.call_count, 2)
        self.assertNotIn("outline_failed", self._event_names())


if __name__ == "__main__":
    unittest.main()
