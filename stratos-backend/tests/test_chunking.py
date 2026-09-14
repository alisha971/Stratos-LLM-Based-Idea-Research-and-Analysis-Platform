"""Chunking tests (gap-closing plan Stage 2a). Pure functions, no network,
no DB -- runs anywhere."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.chunking import chunk_text


class ChunkTextTests(unittest.TestCase):
    def test_empty_input_returns_no_chunks(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n\n  "), [])

    def test_short_text_returns_single_chunk(self):
        text = "A short paragraph about medical residents and meal prep."
        chunks = chunk_text(text, chunk_size=500)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_every_chunk_within_size_budget(self):
        # Long, punctuation-bearing text so sentence splitting has real work
        # to do -- one long paragraph, many sentences.
        sentence = "Medical residents work long shifts and rarely have time to cook. "
        text = sentence * 60  # ~4080 chars
        chunks = chunk_text(text, chunk_size=500, overlap_ratio=0.12)
        self.assertGreater(len(chunks), 1)
        # Fix-audit Part 4: previously an emitted chunk could reach roughly
        # 2x chunk_size (the overlap carry, itself near the budget, had the
        # next unit appended on top unconditionally). The pack loop now
        # re-checks actual joined length at both points, so no chunk may
        # exceed chunk_size at all -- no slack needed.
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 500)

    def test_paragraph_boundaries_preferred_over_mid_sentence_splits(self):
        para1 = "First paragraph. " * 10
        para2 = "Second paragraph. " * 10
        text = para1.strip() + "\n\n" + para2.strip()
        chunks = chunk_text(text, chunk_size=len(para1) + 5, overlap_ratio=0.0)
        # The first chunk should end with a complete sentence (period), not
        # a truncated mid-sentence fragment.
        self.assertTrue(chunks[0].rstrip().endswith("."))

    def test_no_word_is_ever_split(self):
        text = ("supercalifragilisticexpialidocious " * 40).strip()
        chunks = chunk_text(text, chunk_size=100)
        for chunk in chunks:
            for word in chunk.split():
                self.assertIn(word, text)  # every emitted word is intact

    def test_overlap_preserves_boundary_straddling_claim(self):
        # A claim planted right at a natural chunk boundary must survive
        # intact in at least one chunk when overlap is enabled.
        filler_a = "Padding sentence number one. " * 15
        claim = "The Indian D2C skincare market reached 1.2 billion dollars in 2025."
        filler_b = "Padding sentence number two. " * 15
        text = filler_a.strip() + " " + claim + " " + filler_b.strip()

        chunks = chunk_text(text, chunk_size=400, overlap_ratio=0.15)
        self.assertTrue(any(claim in c for c in chunks))

    def test_zero_overlap_still_chunks(self):
        sentence = "One sentence here. " * 40
        chunks = chunk_text(sentence, chunk_size=300, overlap_ratio=0.0)
        self.assertGreater(len(chunks), 1)
        # No chunk should be empty.
        self.assertTrue(all(c.strip() for c in chunks))

    def test_oversized_single_word_is_hard_split_not_emitted_whole(self):
        # Fix-audit Part 4: a URL/base64-style run with no spaces used to
        # be returned whole even when far longer than chunk_size -- exactly
        # the token-dense text that overflows an embedding model's token
        # limit at a fraction of the character budget.
        url = "https://example.com/" + ("a" * 900)  # one 921-char "word"
        chunks = chunk_text(url, chunk_size=200, overlap_ratio=0.0)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 200)
        # No content lost: the pieces reassemble back to the original.
        self.assertEqual("".join(chunks), url)

    def test_oversized_word_embedded_in_normal_prose_is_still_split(self):
        text = (
            "Read the pricing details here: "
            + ("x" * 600)
            + " and let us know what you think."
        )
        chunks = chunk_text(text, chunk_size=150, overlap_ratio=0.0)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 150)

    def test_no_chunk_ever_exceeds_size_budget_across_varied_inputs(self):
        # A broader sweep than the single long-paragraph case above:
        # multiple paragraphs, short and long sentences, and an oversized
        # word, all in the same document.
        text = "\n\n".join(
            [
                "Short intro paragraph.",
                ("A longer paragraph with many sentences. " * 20).strip(),
                "One sentence with a long token: " + ("z" * 550) + " right there.",
                ("Another paragraph. " * 15).strip(),
            ]
        )
        for chunk_size in (100, 250, 500):
            chunks = chunk_text(text, chunk_size=chunk_size, overlap_ratio=0.12)
            for chunk in chunks:
                self.assertLessEqual(
                    len(chunk), chunk_size, f"chunk_size={chunk_size} chunk={chunk!r}"
                )

    def test_reconstructable_content_no_word_dropped(self):
        """Every word in the source appears somewhere in the chunked output
        (overlap means some appear more than once, none should appear zero
        times)."""
        text = (
            "Three funded incumbents already own tier-one distribution in "
            "this market. " * 8
        ).strip()
        chunks = chunk_text(text, chunk_size=150, overlap_ratio=0.1)
        chunked_words = set(" ".join(chunks).split())
        source_words = set(text.split())
        self.assertTrue(source_words.issubset(chunked_words))


if __name__ == "__main__":
    unittest.main()
