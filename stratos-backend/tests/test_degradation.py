"""app/utils/degradation.py -- the shared fallback-activation counter
introduced by the fix-audit (Part 0). Uses a tiny in-memory fake for
redis_client rather than a live Redis connection, matching this suite's
no-external-services convention (generate_chat/publish_event are likewise
mocked at their import sites elsewhere).
"""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils import degradation


class _FakeRedis:
    """Just enough of the redis-py hash API for this module: hincrby,
    hgetall (bytes keys/values, like a real un-decoded client), expire,
    delete."""

    def __init__(self):
        self.hashes: dict[str, dict[bytes, int]] = {}
        self.expirations: dict[str, int] = {}

    def hincrby(self, key, field, amount=1):
        bucket = self.hashes.setdefault(key, {})
        field_b = field.encode() if isinstance(field, str) else field
        bucket[field_b] = bucket.get(field_b, 0) + amount
        return bucket[field_b]

    def hgetall(self, key):
        bucket = self.hashes.get(key, {})
        return {k: str(v).encode() for k, v in bucket.items()}

    def expire(self, key, ttl):
        self.expirations[key] = ttl

    def delete(self, key):
        self.hashes.pop(key, None)
        self.expirations.pop(key, None)


class DegradationTallyTests(unittest.TestCase):
    def setUp(self):
        self.fake = _FakeRedis()
        patcher = patch.object(degradation, "redis_client", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_tally_for_unknown_report(self):
        self.assertEqual(degradation.degradation_tally("unknown"), {})

    def test_single_activation_is_counted(self):
        degradation.record_degradation("r1", "stance_classification", "bad json")
        self.assertEqual(degradation.degradation_tally("r1"), {"stance_classification": 1})

    def test_repeated_activations_with_the_identical_reason_both_count(self):
        # This is the point of the module: two real degradations that
        # happen to produce the same reason string (e.g. the same
        # validation message on two different batches) are two real
        # activations, not one deduplicated event.
        degradation.record_degradation("r1", "stance_classification", "same reason")
        degradation.record_degradation("r1", "stance_classification", "same reason")
        self.assertEqual(degradation.degradation_tally("r1"), {"stance_classification": 2})

    def test_tally_aggregates_by_stage_independently(self):
        degradation.record_degradation("r1", "stance_classification", "x")
        degradation.record_degradation("r1", "stance_classification", "y")
        degradation.record_degradation("r1", "competitor_relevance", "z")

        self.assertEqual(
            degradation.degradation_tally("r1"),
            {"stance_classification": 2, "competitor_relevance": 1},
        )

    def test_reports_do_not_share_a_tally(self):
        degradation.record_degradation("r1", "stance_classification", "x")
        degradation.record_degradation("r2", "stance_classification", "y")

        self.assertEqual(degradation.degradation_tally("r1"), {"stance_classification": 1})
        self.assertEqual(degradation.degradation_tally("r2"), {"stance_classification": 1})

    def test_ttl_is_refreshed_on_every_activation(self):
        degradation.record_degradation("r1", "stance_classification", "x")
        self.assertEqual(self.fake.expirations["degradation:r1"], degradation._TTL_SECONDS)

    def test_clear_removes_the_tally(self):
        degradation.record_degradation("r1", "stance_classification", "x")
        degradation.clear("r1")
        self.assertEqual(degradation.degradation_tally("r1"), {})


if __name__ == "__main__":
    unittest.main()
