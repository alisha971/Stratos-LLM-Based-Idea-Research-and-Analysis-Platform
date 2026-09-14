"""app/llm/repair.py -- the shared generate-then-repair-once orchestration
introduced by the fix-audit (Part 2) to replace four copies of the same
try/except/retry shape in section_worker.py, verdict_worker.py,
clarification_worker.py and outline_worker.py."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.repair import BASE_TEMPERATURE, REPAIR_TEMPERATURE, generate_with_repair


class GenerateWithRepairTests(unittest.TestCase):
    def test_happy_path_calls_generate_once_at_base_temperature(self):
        calls = []

        def generate(repair_reason, temperature):
            calls.append((repair_reason, temperature))
            return {"ok": True}

        result = generate_with_repair(generate=generate)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [(None, BASE_TEMPERATURE)])

    def test_value_error_triggers_exactly_one_repair_at_raised_temperature(self):
        calls = []

        def generate(repair_reason, temperature):
            calls.append((repair_reason, temperature))
            if repair_reason is None:
                raise ValueError("bad json")
            return {"ok": True}

        result = generate_with_repair(generate=generate)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [(None, BASE_TEMPERATURE), ("bad json", REPAIR_TEMPERATURE)])

    def test_runtime_error_also_triggers_repair(self):
        # RuntimeError is what generate_chat raises after exhausting both
        # Groq keys -- must be treated the same as a bad/unparseable
        # response, not just ValueError.
        calls = []

        def generate(repair_reason, temperature):
            calls.append(temperature)
            if repair_reason is None:
                raise RuntimeError("both Groq keys exhausted")
            return {"ok": True}

        result = generate_with_repair(generate=generate)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls, [BASE_TEMPERATURE, REPAIR_TEMPERATURE])

    def test_second_failure_propagates_uncaught(self):
        # Exactly one repair attempt -- a second failure must not be
        # swallowed here, so the caller's own fatal-event handling
        # (section_failed/verdict_failed/etc.) fires exactly once.
        def generate(repair_reason, temperature):
            raise RuntimeError(f"failed (repair_reason={repair_reason})")

        with self.assertRaises(RuntimeError):
            generate_with_repair(generate=generate)

    def test_validate_failure_triggers_repair_with_its_reason(self):
        def generate(repair_reason, temperature):
            return {"attempt": repair_reason}

        def validate(result):
            if result["attempt"] is None:
                raise ValueError("first attempt invalid")

        result = generate_with_repair(generate=generate, validate=validate)

        self.assertEqual(result, {"attempt": "first attempt invalid"})

    def test_validate_runs_on_repair_attempt_too(self):
        # Grounding must not be weakened by the temperature bump: validate
        # still runs (and can still fail) on the repair attempt.
        def generate(repair_reason, temperature):
            return {"attempt": repair_reason}

        def validate(result):
            raise ValueError("always invalid")

        with self.assertRaises(ValueError):
            generate_with_repair(generate=generate, validate=validate)

    def test_on_repair_callback_receives_the_reason(self):
        seen = []

        def generate(repair_reason, temperature):
            if repair_reason is None:
                raise ValueError("boom")
            return "ok"

        generate_with_repair(generate=generate, on_repair=seen.append)

        self.assertEqual(seen, ["boom"])

    def test_on_repair_not_called_on_happy_path(self):
        seen = []

        generate_with_repair(generate=lambda r, t: "ok", on_repair=seen.append)

        self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
