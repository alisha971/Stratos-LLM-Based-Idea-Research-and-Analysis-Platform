"""RRF + diversification tests (gap-closing plan Stage 2f/2g). Pure
functions, no network, no DB."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.ranking_fusion import diversify, fuse_and_sort, reciprocal_rank_fusion


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_matches_worked_example_from_plan(self):
        lexical = ["D3", "D1", "D7", "D2", "D9"]
        semantic = ["D1", "D9", "D3", "D5", "D7"]

        scores = reciprocal_rank_fusion([lexical, semantic], k=60)

        self.assertAlmostEqual(scores["D1"], 1 / 62 + 1 / 61, places=6)
        self.assertAlmostEqual(scores["D3"], 1 / 61 + 1 / 63, places=6)
        self.assertAlmostEqual(scores["D9"], 1 / 65 + 1 / 62, places=6)
        self.assertAlmostEqual(scores["D7"], 1 / 63 + 1 / 65, places=6)
        self.assertAlmostEqual(scores["D5"], 1 / 64, places=6)
        self.assertAlmostEqual(scores["D2"], 1 / 64, places=6)

    def test_consensus_wins_over_single_system_top_rank(self):
        # D1 never ranks #1 in either system but should top the fused list
        # because both systems placed it highly (Stage 2f's point).
        lexical = ["D3", "D1", "D7", "D2", "D9"]
        semantic = ["D1", "D9", "D3", "D5", "D7"]

        fused = fuse_and_sort([lexical, semantic], k=60)
        self.assertEqual(fused[0], "D1")

    def test_item_in_only_one_list_still_ranks(self):
        fused = fuse_and_sort([["A", "B"], ["C"]], k=60)
        self.assertIn("C", fused)
        self.assertEqual(len(fused), 3)

    def test_empty_lists_produce_no_scores(self):
        self.assertEqual(reciprocal_rank_fusion([[], []]), {})

    def test_single_list_preserves_original_order(self):
        fused = fuse_and_sort([["A", "B", "C"]])
        self.assertEqual(fused, ["A", "B", "C"])


class DiversifyTests(unittest.TestCase):
    def test_drops_near_duplicate_wire_copy(self):
        items = [
            {"id": "a", "text": "Three funded incumbents already own tier-one distribution in the skincare market."},
            {"id": "b", "text": "Three funded incumbents already own tier-one distribution in the skincare market today."},
            {"id": "c", "text": "The compliance burden for therapist note-taking apps is substantial and growing."},
        ]
        result = diversify(items, text_fn=lambda i: i["text"], limit=3)
        ids = [i["id"] for i in result]
        self.assertIn("a", ids)
        self.assertIn("c", ids)
        self.assertNotIn("b", ids)  # near-duplicate of "a", dropped
        self.assertEqual(len(result), 2)

    def test_distinct_items_all_survive(self):
        items = [
            {"id": "a", "text": "The Indian D2C skincare market reached 1.2 billion dollars."},
            {"id": "b", "text": "Compliance load is the primary barrier for therapist note-taking apps."},
            {"id": "c", "text": "Medical residents report severe time scarcity for meal preparation."},
        ]
        result = diversify(items, text_fn=lambda i: i["text"], limit=3)
        self.assertEqual(len(result), 3)

    def test_respects_limit(self):
        items = [{"id": str(i), "text": f"Unique sentence number {i} about a distinct topic entirely."} for i in range(10)]
        result = diversify(items, text_fn=lambda i: i["text"], limit=3)
        self.assertEqual(len(result), 3)

    def test_short_text_does_not_crash(self):
        items = [
            {"id": "a", "text": "ok"},
            {"id": "b", "text": "ok"},
            {"id": "c", "text": ""},
        ]
        result = diversify(items, text_fn=lambda i: i["text"], limit=3)
        self.assertGreaterEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
