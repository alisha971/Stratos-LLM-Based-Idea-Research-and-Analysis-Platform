"""app/services/markdown_pdf.py (fix-audit Part 6b). chunk.text is
markdown -- the same string the frontend renders with react-markdown --
so the PDF renderer must produce real headings/bullets/tables/bold, not
literal "**bold**"/"- bullet" characters flattened into one Paragraph.
Citations must still link from inside table cells and list items, and a
model-authored link href must never become clickable (only this module's
own citation-marker substitution against a vetted `sources` dict creates
a link)."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import ListFlowable, Paragraph, Table

from app.services.markdown_pdf import render_markdown

SOURCES = {
    "CIT-001": {"url": "https://a.example.com", "domain": "a.example.com"},
    "CIT-002": {"url": "https://b.example.com", "domain": "b.example.com"},
}


def _extract_text(flowable) -> str:
    if hasattr(flowable, "text"):
        return flowable.text
    if isinstance(flowable, ListFlowable):
        return "\n".join(
            _extract_text(sub) for item in flowable._flowables for sub in item._flowables
        )
    if isinstance(flowable, Table):
        return " | ".join(
            _extract_text(cell) for row in flowable._cellvalues for cell in row
        )
    return ""


class RenderMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.styles = getSampleStyleSheet()

    def test_empty_input_returns_no_flowables(self):
        self.assertEqual(render_markdown("", SOURCES, self.styles), [])
        self.assertEqual(render_markdown("   \n\n  ", SOURCES, self.styles), [])

    def test_plain_paragraph(self):
        flowables = render_markdown("A plain sentence with no markup.", SOURCES, self.styles)
        self.assertEqual(len(flowables), 1)
        self.assertIsInstance(flowables[0], Paragraph)
        self.assertIn("A plain sentence", flowables[0].text)

    def test_heading_becomes_its_own_paragraph_capped_below_heading2(self):
        flowables = render_markdown("## Existing Solutions", SOURCES, self.styles)
        self.assertEqual(len(flowables), 1)
        self.assertEqual(flowables[0].style.name, "Heading3")  # capped, never Heading2

    def test_deep_heading_capped_at_heading4(self):
        flowables = render_markdown("###### Deep heading", SOURCES, self.styles)
        self.assertEqual(flowables[0].style.name, "Heading4")

    def test_bold_and_italic_render_as_reportlab_markup(self):
        flowables = render_markdown("This is **bold** and *italic* text.", SOURCES, self.styles)
        text = flowables[0].text
        self.assertIn("<b>bold</b>", text)
        self.assertIn("<i>italic</i>", text)
        self.assertNotIn("**bold**", text)  # not left as literal markdown

    def test_bulleted_list_produces_list_flowable(self):
        markdown = "- First point\n- Second point\n- Third point"
        flowables = render_markdown(markdown, SOURCES, self.styles)
        self.assertEqual(len(flowables), 1)
        self.assertIsInstance(flowables[0], ListFlowable)
        self.assertEqual(flowables[0]._bulletType, "bullet")
        text = _extract_text(flowables[0])
        self.assertIn("First point", text)
        self.assertIn("Second point", text)
        self.assertIn("Third point", text)

    def test_numbered_list_uses_numeric_bullet_type(self):
        markdown = "1. First\n2. Second"
        flowables = render_markdown(markdown, SOURCES, self.styles)
        self.assertEqual(flowables[0]._bulletType, "1")

    def test_citation_inside_list_item_is_linked(self):
        markdown = "- Vendor A charges $29/mo [CIT-001]\n- Vendor B is free [CIT-002]"
        flowables = render_markdown(markdown, SOURCES, self.styles)
        text = _extract_text(flowables[0])
        self.assertIn('<a href="https://a.example.com"', text)
        self.assertIn('<a href="https://b.example.com"', text)
        self.assertIn("[CIT-001]", text)
        self.assertIn("[CIT-002]", text)

    def test_gfm_table_produces_table_flowable(self):
        markdown = (
            "| Vendor | Price |\n"
            "| --- | --- |\n"
            "| A | $29/mo |\n"
            "| B | Free |\n"
        )
        flowables = render_markdown(markdown, SOURCES, self.styles)
        tables = [f for f in flowables if isinstance(f, Table)]
        self.assertEqual(len(tables), 1)
        text = _extract_text(tables[0])
        self.assertIn("Vendor", text)
        self.assertIn("$29/mo", text)
        self.assertIn("Free", text)

    def test_citation_inside_table_cell_is_linked(self):
        markdown = (
            "| Vendor | Notes |\n"
            "| --- | --- |\n"
            "| A | Popular choice [CIT-001] |\n"
        )
        flowables = render_markdown(markdown, SOURCES, self.styles)
        table = next(f for f in flowables if isinstance(f, Table))
        text = _extract_text(table)
        self.assertIn('<a href="https://a.example.com"', text)
        self.assertIn("[CIT-001]", text)

    def test_table_header_row_is_bolded(self):
        markdown = "| Vendor | Price |\n| --- | --- |\n| A | $29/mo |\n"
        flowables = render_markdown(markdown, SOURCES, self.styles)
        table = next(f for f in flowables if isinstance(f, Table))
        header_text = table._cellvalues[0][0].text
        self.assertIn("<b>", header_text)

    def test_citation_marker_with_no_source_stays_plain_text_everywhere(self):
        markdown = "- Some claim with an unresolvable marker [CIT-999]"
        flowables = render_markdown(markdown, {}, self.styles)
        text = _extract_text(flowables[0])
        self.assertNotIn("<a href", text)
        self.assertIn("[CIT-999]", text)

    def test_model_authored_link_href_never_becomes_clickable(self):
        # Security: mistune parses [text](url) into a real link token
        # with the model's own href verbatim (confirmed manually against
        # mistune 3.x) -- only OUR citation-marker substitution against a
        # vetted `sources` dict may ever produce a clickable <a> tag.
        markdown = "Check this out: [click here](javascript:alert(1)) for details."
        flowables = render_markdown(markdown, SOURCES, self.styles)
        text = flowables[0].text
        self.assertNotIn("javascript:", text)
        self.assertNotIn("<a href", text)
        self.assertIn("click here", text)  # visible text still renders

    def test_blockquote_renders_with_distinct_indent(self):
        markdown = "> An important caveat [CIT-001]."
        flowables = render_markdown(markdown, SOURCES, self.styles)
        self.assertEqual(len(flowables), 1)
        para = flowables[0]
        self.assertGreater(para.style.leftIndent, self.styles["BodyText"].leftIndent)
        self.assertIn('<a href="https://a.example.com"', para.text)

    def test_html_special_characters_are_escaped(self):
        flowables = render_markdown("Growth & opportunity are real.", SOURCES, self.styles)
        text = flowables[0].text
        self.assertIn("&amp;", text)

    def test_raw_inline_html_is_not_rendered_unescaped(self):
        # Same posture as the frontend's deliberate no-rehype-raw choice.
        markdown = "Text with <script>alert(1)</script> embedded."
        flowables = render_markdown(markdown, SOURCES, self.styles)
        text = flowables[0].text
        self.assertNotIn("<script>", text)

    def test_raw_inline_html_like_text_is_visible_not_silently_dropped(self):
        # Regression: mistune tags ANY <word>-shaped run as inline_html
        # per CommonMark, not just real tags -- "Growth was <huge> and
        # real" used to lose "<huge>" entirely (silently dropped by the
        # unknown-inline-type fallback) instead of showing it escaped.
        flowables = render_markdown("Growth was <huge> and real.", SOURCES, self.styles)
        text = flowables[0].text
        self.assertIn("&lt;huge&gt;", text)
        self.assertIn("Growth was", text)
        self.assertIn("and real.", text)

    def test_block_level_raw_html_is_visible_not_silently_dropped(self):
        markdown = "<div>A stray HTML block</div>"
        flowables = render_markdown(markdown, SOURCES, self.styles)
        full_text = " ".join(getattr(f, "text", "") for f in flowables)
        self.assertIn("A stray HTML block", full_text)
        self.assertNotIn("<div>", full_text)  # escaped, not rendered as markup

    def test_the_reported_symptom_non_breaking_hyphen_is_folded(self):
        flowables = render_markdown("type 2‑diabetes management", SOURCES, self.styles)
        self.assertIn("type 2-diabetes", flowables[0].text)

    def test_mixed_document_renders_headings_paragraphs_lists_and_tables_in_order(self):
        markdown = (
            "## Existing Solutions\n\n"
            "Several products serve this market.\n\n"
            "- Vendor A [CIT-001]\n"
            "- Vendor B [CIT-002]\n\n"
            "| Vendor | Price |\n"
            "| --- | --- |\n"
            "| A | $29/mo |\n"
        )
        flowables = render_markdown(markdown, SOURCES, self.styles)
        kinds = [type(f).__name__ for f in flowables]
        self.assertEqual(kinds[0], "Paragraph")  # heading
        self.assertIn("ListFlowable", kinds)
        self.assertIn("Table", kinds)
        # Order preserved: heading before list before table.
        self.assertLess(kinds.index("ListFlowable"), kinds.index("Table"))


if __name__ == "__main__":
    unittest.main()
