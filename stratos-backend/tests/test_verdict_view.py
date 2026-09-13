"""verdict_view tests (gap-closing plan Stage 5). Shared by
assembler_worker.py's draft and OrchestratorService.get_report_view --
tested once here rather than through both call sites."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.verdict_view import verdict_view


class FakeReport:
    def __init__(self, **kwargs):
        self.id = "r1"
        self.verdict = None
        self.verdict_holding = None
        self.verdict_payload = None
        self.flip_condition = None
        self.verdict_confidence = None
        self.__dict__.update(kwargs)


class VerdictViewTests(unittest.TestCase):
    def test_no_verdict_returns_none(self):
        self.assertIsNone(verdict_view(FakeReport()))

    def test_well_formed_verdict_returns_full_view(self):
        report = FakeReport(
            verdict="reshape",
            verdict_holding="Go, but only in the underserved segment.",
            verdict_payload='{"case_for_prose": "Demand is real [CIT-001]."}',
            flip_condition="If a top incumbent adds this feature.",
            verdict_confidence="medium",
        )
        view = verdict_view(report)
        self.assertEqual(view["verdict"], "reshape")
        self.assertEqual(view["holding"], "Go, but only in the underserved segment.")
        self.assertEqual(view["flip_condition"], "If a top incumbent adds this feature.")
        self.assertEqual(view["confidence"], "medium")
        self.assertEqual(view["payload"]["case_for_prose"], "Demand is real [CIT-001].")

    def test_malformed_payload_json_degrades_to_empty_payload_not_a_crash(self):
        report = FakeReport(verdict="build", verdict_payload="not valid json")
        view = verdict_view(report)
        self.assertIsNotNone(view)
        self.assertEqual(view["payload"], {})

    def test_missing_payload_is_empty_dict_not_none(self):
        report = FakeReport(verdict="walk_away", verdict_payload=None)
        view = verdict_view(report)
        self.assertEqual(view["payload"], {})


if __name__ == "__main__":
    unittest.main()
