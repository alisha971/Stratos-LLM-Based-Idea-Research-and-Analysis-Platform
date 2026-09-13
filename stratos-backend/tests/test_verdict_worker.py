"""§4 of the LLM JSON reliability plan: mirrors test_section_worker.py --
the worker must retry once on a RuntimeError from generate_verdict_draft,
not just on a ValueError from the validator."""

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workers import verdict_worker


def _context():
    return {"unresolved_gaps": []}


def _draft():
    return {
        "verdict": "reshape",
        "holding": "Go, but only in the underserved segment.",
        "case_for_prose": "Demand is real.",
        "case_against_prose": "Incumbents own distribution.",
        "which_won": "Distribution gap wins.",
        "flip_condition": "If an incumbent ships this feature.",
        "confidence": "medium",
    }


class RunVerdictRetryTests(unittest.TestCase):
    def setUp(self):
        self.db_patch = mock.patch.object(
            verdict_worker, "SessionLocal", return_value=mock.Mock()
        )
        self.publish_patch = mock.patch.object(verdict_worker, "publish_event")

        self.db_patch.start()
        self.mock_publish = self.publish_patch.start()

        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.publish_patch.stop)

    def _service(self, generate_side_effect):
        service = mock.Mock()
        service.build_verdict_context.return_value = _context()
        service.generate_verdict_draft.side_effect = generate_side_effect
        service.validate_verdict_draft.return_value = None
        service.persist_verdict.return_value = None
        return service

    def _event_names(self):
        return [call.args[0] for call in self.mock_publish.call_args_list]

    def test_runtime_error_then_success_retries_once_no_failure_event(self):
        service = self._service(
            generate_side_effect=[RuntimeError("both Groq keys exhausted"), _draft()]
        )
        with mock.patch.object(verdict_worker, "VerdictService", return_value=service):
            verdict_worker.run_verdict.run("report-1")

        self.assertEqual(service.generate_verdict_draft.call_count, 2)
        _, repair_kwargs = service.generate_verdict_draft.call_args
        self.assertIn("repair_reason", repair_kwargs)
        self.assertNotIn("verdict_failed", self._event_names())
        self.assertIn("verdict_ready", self._event_names())

    def test_runtime_error_twice_fires_verdict_failed_once(self):
        service = self._service(
            generate_side_effect=[
                RuntimeError("both Groq keys exhausted"),
                RuntimeError("both Groq keys exhausted again"),
            ]
        )
        with mock.patch.object(verdict_worker, "VerdictService", return_value=service):
            with self.assertRaises(RuntimeError):
                verdict_worker.run_verdict.run("report-1")

        self.assertEqual(service.generate_verdict_draft.call_count, 2)
        self.assertEqual(self._event_names().count("verdict_failed"), 1)
        self.assertNotIn("verdict_ready", self._event_names())

    def test_value_error_from_validator_still_retries_once(self):
        service = self._service(generate_side_effect=[_draft(), _draft()])
        service.validate_verdict_draft.side_effect = [
            ValueError("missing prose field"),
            None,
        ]
        with mock.patch.object(verdict_worker, "VerdictService", return_value=service):
            verdict_worker.run_verdict.run("report-1")

        self.assertEqual(service.generate_verdict_draft.call_count, 2)
        self.assertNotIn("verdict_failed", self._event_names())
        self.assertIn("verdict_ready", self._event_names())


if __name__ == "__main__":
    unittest.main()
