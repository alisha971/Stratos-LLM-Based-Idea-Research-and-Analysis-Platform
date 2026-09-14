"""app/utils/text_cleaner.py -- previously untested. Fix-audit Part 4
rewrote clean_html to preserve paragraph structure (blocks joined by a
blank line) instead of one global get_text(separator="\n") that put a
single newline between every tag indiscriminately, which meant
chunking.py's paragraph-boundary splitter never had a real boundary to
find."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.chunking import _PARAGRAPH_SPLIT
from app.utils.text_cleaner import clean_html


class CleanHtmlTests(unittest.TestCase):
    def test_strips_boilerplate_tags(self):
        html = (
            "<html><body>"
            "<nav>Home | About</nav>"
            "<header>Site Header</header>"
            "<p>Real content paragraph here.</p>"
            "<footer>Copyright 2026</footer>"
            "<script>var x = 1;</script>"
            "<style>.a{color:red}</style>"
            "<aside>Related links</aside>"
            "</body></html>"
        )
        result = clean_html(html)

        self.assertIn("Real content paragraph here.", result)
        for boilerplate in (
            "Home | About",
            "Site Header",
            "Copyright 2026",
            "var x = 1",
            "color:red",
            "Related links",
        ):
            self.assertNotIn(boilerplate, result)

    def test_paragraph_boundaries_are_detectable_by_chunking(self):
        # The actual bug: chunking.py's _PARAGRAPH_SPLIT (\n\s*\n) must
        # find real boundaries in clean_html's output.
        html = (
            "<article>"
            "<p>First paragraph about existing solutions on the market.</p>"
            "<p>Second paragraph about target users and personas.</p>"
            "<p>Third paragraph about competitor pricing.</p>"
            "</article>"
        )
        result = clean_html(html)
        paragraphs = [p for p in _PARAGRAPH_SPLIT.split(result) if p.strip()]

        self.assertEqual(len(paragraphs), 3)
        self.assertIn("existing solutions", paragraphs[0])
        self.assertIn("target users", paragraphs[1])
        self.assertIn("competitor pricing", paragraphs[2])

    def test_nested_block_is_not_duplicated(self):
        # A <div> wrapping a <p> must not emit the same text twice (once
        # for the div, once for the nested p).
        html = "<div><p>Only counted once please.</p></div>"
        result = clean_html(html)
        self.assertEqual(result.count("Only counted once please."), 1)

    def test_headings_are_their_own_paragraph(self):
        html = "<h1>Report Title</h1><p>Body text follows the heading.</p>"
        result = clean_html(html)
        paragraphs = [p for p in _PARAGRAPH_SPLIT.split(result) if p.strip()]
        self.assertEqual(paragraphs[0], "Report Title")

    def test_normalizes_nbsp_and_zero_width_space(self):
        html = "<p>Type\u00a02\u200bdiabetes management plan.</p>"
        result = clean_html(html)
        self.assertNotIn("\u00a0", result)
        self.assertNotIn("\u200b", result)
        self.assertIn("Type 2diabetes", result)  # NBSP -> space, ZWSP -> nothing

    def test_collapses_internal_whitespace_without_touching_boundaries(self):
        html = "<p>Word   with     extra    spaces.</p><p>Second block.</p>"
        result = clean_html(html)
        self.assertIn("Word with extra spaces.", result)
        self.assertIn("\n\n", result)

    def test_empty_input_returns_empty_string(self):
        self.assertEqual(clean_html(""), "")
        self.assertEqual(clean_html("<html><body></body></html>"), "")

    def test_bare_text_with_no_block_tags_falls_back_to_whole_document(self):
        html = "<html><body>Just some bare text, no block tags at all.</body></html>"
        result = clean_html(html)
        self.assertIn("Just some bare text, no block tags at all.", result)

    def test_table_cells_are_separate_blocks(self):
        html = "<table><tr><td>Cell one</td><td>Cell two</td></tr></table>"
        result = clean_html(html)
        paragraphs = [p for p in _PARAGRAPH_SPLIT.split(result) if p.strip()]
        self.assertEqual(paragraphs, ["Cell one", "Cell two"])


if __name__ == "__main__":
    unittest.main()
