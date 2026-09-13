"""§4 of the LLM JSON reliability plan: the worker must retry once on a
RuntimeError from generate_section_draft (an exhausted/non-retryable LLM
call), not just on a ValueError from the validator."""

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.workers import section_worker


def _context():
    return {
        "citation_map": {},
        "source_mode": "web",
    }


def _draft():
    return {
        "chunks": [{"chunk_index": 1, "text": "ok", "citations": []}],
        "section_alignment_summary": "ok",
    }


class RunSectionWriterRetryTests(unittest.TestCase):
    def setUp(self):
        self.db_patch = mock.patch.object(
            section_worker, "SessionLocal", return_value=mock.Mock()
        )
        self.publish_patch = mock.patch.object(section_worker, "publish_event")
        self.celery_patch = mock.patch.object(section_worker.celery_app, "send_task")

        self.db_patch.start()
        self.mock_publish = self.publish_patch.start()
        self.celery_patch.start()

        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.publish_patch.stop)
        self.addCleanup(self.celery_patch.stop)

    def _service(self, generate_side_effect):
        service = mock.Mock()
        service.build_section_context.return_value = _context()
        service.generate_section_draft.side_effect = generate_side_effect
        service.validate_section_draft.return_value = None
        service.persist_section_chunks.return_value = ["chunk-1"]
        return service

    def _event_names(self):
        return [call.args[0] for call in self.mock_publish.call_args_list]

    def test_runtime_error_then_success_retries_once_no_failure_event(self):
        service = self._service(
            generate_side_effect=[RuntimeError("both Groq keys exhausted"), _draft()]
        )
        with mock.patch.object(
            section_worker, "SectionWriterService", return_value=service
        ):
            section_worker.run_section_writer.run("report-1", "section-1")

        self.assertEqual(service.generate_section_draft.call_count, 2)
        # second call is the repair retry, carrying the failure reason
        _, repair_kwargs = service.generate_section_draft.call_args
        self.assertIn("repair_reason", repair_kwargs)
        self.assertNotIn("section_failed", self._event_names())
        self.assertIn("section_done", self._event_names())

    def test_runtime_error_twice_fires_section_failed_once(self):
        service = self._service(
            generate_side_effect=[
                RuntimeError("both Groq keys exhausted"),
                RuntimeError("both Groq keys exhausted again"),
            ]
        )
        with mock.patch.object(
            section_worker, "SectionWriterService", return_value=service
        ):
            with self.assertRaises(RuntimeError):
                section_worker.run_section_writer.run("report-1", "section-1")

        self.assertEqual(service.generate_section_draft.call_count, 2)
        self.assertEqual(self._event_names().count("section_failed"), 1)
        self.assertNotIn("section_done", self._event_names())

    def test_value_error_from_validator_still_retries_once(self):
        # Existing behaviour (validator ValueError) must be unaffected by
        # widening the except clause to include RuntimeError.
        service = self._service(generate_side_effect=[_draft(), _draft()])
        service.validate_section_draft.side_effect = [
            ValueError("title drift"),
            None,
        ]
        with mock.patch.object(
            section_worker, "SectionWriterService", return_value=service
        ):
            section_worker.run_section_writer.run("report-1", "section-1")

        self.assertEqual(service.generate_section_draft.call_count, 2)
        self.assertNotIn("section_failed", self._event_names())
        self.assertIn("section_done", self._event_names())


if __name__ == "__main__":
    unittest.main()
