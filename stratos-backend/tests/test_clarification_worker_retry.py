"""Extension of the LLM JSON reliability plan's §4 pattern to
clarification_worker.py -- discovered via a live end-to-end pipeline run
where a single non-retryable Groq failure (RuntimeError, no local retry)
fatally killed the whole session (clarification_failed is fatal, see
orchestrator_service.py). Mirrors test_section_worker.py's structure."""

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models
from app.workers import clarification_worker


def _session():
    session_obj = models.Session(
        id="s1", user_id="u1", status="CLARIFYING", idea_description="x"
    )
    session_obj.clarification_schema = {}
    return session_obj


def _valid_reply(**overrides):
    reply = {
        "message_intent": "idea_content",
        "updated_schema": {
            "project_domain": "health/diabetes",
            "target_persona": "diabetic patients",
            "core_problem": "Patients do not know what to eat.",
            "current_workaround": "Google, chatbots, doctors.",
            "proposed_solution": "food plan app",
            "differentiation": None,
        },
        "hard_constraints": [],
        "hypotheses": [],
        "knowledge_gaps": {},
        "research_directives": [],
        "confidence_score": 0.5,
        "unknown_detected": False,
        "turn_fatigue": False,
        "mirror_summary": "Got it.",
        "next_question": "What's your unique angle?",
    }
    reply.update(overrides)
    return json.dumps(reply)


class RunClarificationRetryTests(unittest.TestCase):
    def setUp(self):
        self.fake_db = mock.MagicMock()
        fake_query = mock.MagicMock()
        self.fake_db.query.return_value = fake_query
        fake_query.filter_by.return_value = fake_query
        fake_query.order_by.return_value = fake_query
        fake_query.first.return_value = _session()
        fake_query.all.return_value = []

        self.published = []

        self.db_patch = mock.patch.object(
            clarification_worker, "SessionLocal", return_value=self.fake_db
        )
        self.publish_patch = mock.patch.object(
            clarification_worker,
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
            clarification_worker,
            "generate_chat",
            side_effect=[RuntimeError("both Groq keys exhausted"), _valid_reply()],
        ) as mock_generate:
            clarification_worker.run_clarification("s1")

        self.assertEqual(mock_generate.call_count, 2)
        # second call's system prompt carries the repair reason
        _, second_kwargs = mock_generate.call_args_list[1]
        self.assertIn("REPAIR REQUIRED", second_kwargs["messages"][0]["content"])
        self.assertNotIn("clarification_failed", self._event_names())

    def test_runtime_error_twice_fires_clarification_failed_once(self):
        with mock.patch.object(
            clarification_worker,
            "generate_chat",
            side_effect=[
                RuntimeError("both Groq keys exhausted"),
                RuntimeError("both Groq keys exhausted again"),
            ],
        ) as mock_generate:
            with self.assertRaises(RuntimeError):
                clarification_worker.run_clarification("s1")

        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(self._event_names().count("clarification_failed"), 1)

    def test_empty_response_then_success_retries_once(self):
        # Guard 1 (empty response -> ValueError) must also get the retry.
        with mock.patch.object(
            clarification_worker,
            "generate_chat",
            side_effect=["", _valid_reply()],
        ) as mock_generate:
            clarification_worker.run_clarification("s1")

        self.assertEqual(mock_generate.call_count, 2)
        self.assertNotIn("clarification_failed", self._event_names())


if __name__ == "__main__":
    unittest.main()
