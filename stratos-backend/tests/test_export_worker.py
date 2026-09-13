"""Export worker tests (gap-closing plan Stage 5a). _linkify/
_render_source_line are pure functions, tested directly. _build_story tests
inspect the .text of each flowable it would hand to ReportLab -- more
precise than parsing real PDF bytes back out, and needs no PDF-parsing
dependency. One RenderPdfSmokeTest still calls the real _render_pdf to
confirm doc.build() doesn't choke on the produced markup (a malformed tag,
e.g. from an unescaped &, would only surface there)."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib.styles import getSampleStyleSheet

from app.workers.export_worker import _build_story, _linkify, _render_pdf, _render_source_line


class LinkifyTests(unittest.TestCase):
    def test_marker_with_resolvable_url_becomes_anchor(self):
        sources = {"CIT-001": {"url": "https://example.com/a", "domain": "example.com"}}
        result = _linkify("Demand is real [CIT-001].", sources)
        self.assertIn('<a href="https://example.com/a"', result)
        self.assertIn("[CIT-001]", result)

    def test_marker_with_no_url_left_as_plain_text(self):
        sources = {"CIT-001": {"url": None, "domain": "example.com"}}
        result = _linkify("Demand is real [CIT-001].", sources)
        self.assertNotIn("<a href", result)
        self.assertIn("[CIT-001]", result)  # still readable, not dropped

    def test_unknown_marker_left_as_plain_text(self):
        result = _linkify("Demand is real [CIT-999].", sources={})
        self.assertNotIn("<a href", result)
        self.assertIn("[CIT-999]", result)

    def test_html_special_characters_in_text_are_escaped(self):
        result = _linkify("Growth was <huge> & real [CIT-001].", sources={})
        self.assertIn("&lt;huge&gt;", result)
        self.assertIn("&amp;", result)

    def test_escaping_does_not_break_injected_markup(self):
        """The escape() pass must run BEFORE markup injection -- if it ran
        after, the injected <a href> tag itself would get escaped into
        literal &lt;a href&gt; text."""
        sources = {"CIT-001": {"url": "https://example.com?a=1&b=2", "domain": "example.com"}}
        result = _linkify("See [CIT-001].", sources)
        self.assertIn("<a href=", result)  # real tag, not escaped
        self.assertIn("&amp;b=2", result)  # the URL's own & is still escaped

    def test_multiple_markers_all_linkified(self):
        sources = {
            "CIT-001": {"url": "https://a.example.com", "domain": "a.example.com"},
            "CIT-002": {"url": "https://b.example.com", "domain": "b.example.com"},
        }
        result = _linkify("First claim [CIT-001]. Second claim [CIT-002].", sources)
        self.assertIn("https://a.example.com", result)
        self.assertIn("https://b.example.com", result)


class RenderSourceLineTests(unittest.TestCase):
    def setUp(self):
        self.styles = getSampleStyleSheet()

    def test_includes_marker_domain_and_stance(self):
        para = _render_source_line(
            "CIT-001",
            {"url": "https://example.com/a", "domain": "example.com", "stance": "challenges"},
            self.styles,
        )
        text = para.text
        self.assertIn("CIT-001", text)
        self.assertIn("example.com", text)
        self.assertIn("challenges", text)
        self.assertIn("<a href", text)

    def test_missing_url_falls_back_to_plain_domain_text(self):
        para = _render_source_line(
            "CIT-001", {"url": None, "domain": "example.com", "stance": "neutral"}, self.styles
        )
        self.assertNotIn("<a href", para.text)
        self.assertIn("example.com", para.text)

    def test_missing_stance_defaults_to_neutral(self):
        para = _render_source_line(
            "CIT-001", {"url": "https://example.com", "domain": "example.com"}, self.styles
        )
        self.assertIn("neutral", para.text)


class BuildStoryTests(unittest.TestCase):
    """Inspects the .text of each flowable _build_story would hand to
    ReportLab -- exact content assertions without needing to parse PDF
    bytes back out."""

    def _draft(self, **overrides):
        draft = {
            "report_id": "r1",
            "topic": "A meal-prep app for medical residents",
            "verdict": {
                "verdict": "reshape",
                "holding": "Go, but only in the underserved segment.",
                "flip_condition": "If a top incumbent adds this feature within a year.",
                "confidence": "medium",
                "payload": {
                    "case_for_prose": "Demand is real and validated [CIT-001].",
                    "case_against_prose": "Incumbents already own distribution [CIT-002].",
                    "which_won": "The distribution gap outweighs the demand [CIT-002].",
                },
            },
            "sections": [
                {
                    "section_id": "sec-1",
                    "title": "Problem Context & Validation",
                    "order_index": 0,
                    "chunks": [
                        {"chunk_id": "c1", "chunk_index": 1, "text": "Residents lack time [CIT-001]."}
                    ],
                }
            ],
            "sources": {
                "CIT-001": {"url": "https://a.example.com", "domain": "a.example.com", "stance": "supports"},
                "CIT-002": {"url": "https://b.example.com", "domain": "b.example.com", "stance": "challenges"},
            },
            "unresolved_gaps": ["What the typical price point should be."],
        }
        draft.update(overrides)
        return draft

    def _story_text(self, draft) -> str:
        story = _build_story(draft)
        return "\n".join(getattr(flowable, "text", "") for flowable in story)

    def test_topic_is_the_title_not_generic_string(self):
        text = self._story_text(self._draft())
        self.assertIn("A meal-prep app for medical residents", text)
        self.assertNotIn("Stratos Research Report", text)

    def test_verdict_opens_before_the_first_section(self):
        story = _build_story(self._draft())
        texts = [getattr(f, "text", "") for f in story]
        verdict_index = next(i for i, t in enumerate(texts) if "The Verdict" in t)
        section_index = next(i for i, t in enumerate(texts) if "Problem Context" in t)
        self.assertLess(verdict_index, section_index)

    def test_verdict_holding_and_confidence_present(self):
        text = self._story_text(self._draft())
        self.assertIn("Go, but only in the underserved segment", text)
        self.assertIn("medium", text)

    def test_case_against_built_from_challenges_citation(self):
        text = self._story_text(self._draft())
        self.assertIn("Incumbents already own distribution", text)
        self.assertIn("<a href=\"https://b.example.com\"", text)  # CIT-002, tagged challenges

    def test_unresolved_gaps_block_present(self):
        text = self._story_text(self._draft())
        self.assertIn("What We Couldn't Settle", text)
        self.assertIn("typical price point", text)

    def test_no_unresolved_gaps_omits_the_block_entirely(self):
        text = self._story_text(self._draft(unresolved_gaps=[]))
        self.assertNotIn("What We Couldn't Settle", text)

    def test_sources_bibliography_has_real_urls_not_just_markers(self):
        text = self._story_text(self._draft())
        self.assertIn("Sources", text)
        self.assertIn("a.example.com", text)
        self.assertIn("b.example.com", text)
        self.assertIn("supports", text)
        self.assertIn("challenges", text)
        # The old behavior this replaces: "Citations: CIT-001" with no URL.
        self.assertNotIn("Citations: CIT-001", text)

    def test_missing_verdict_omits_heading_but_sections_still_render(self):
        text = self._story_text(self._draft(verdict=None))
        self.assertNotIn("The Verdict", text)
        self.assertIn("Problem Context", text)


class RenderPdfSmokeTests(unittest.TestCase):
    """One real _render_pdf call, actually writing a file -- confirms
    doc.build() accepts the markup _build_story produces. A malformed tag
    (e.g. from an unescaped &) only surfaces here, not in BuildStoryTests."""

    def test_writes_a_real_nonempty_pdf_file(self):
        draft = {
            "report_id": "r1",
            "topic": "A meal-prep app for medical residents",
            "verdict": {
                "verdict": "reshape",
                "holding": "Go, but only in the underserved segment.",
                "flip_condition": "If a top incumbent adds this feature within a year.",
                "confidence": "medium",
                "payload": {
                    "case_for_prose": "Demand is real and validated [CIT-001].",
                    "case_against_prose": "Incumbents already own distribution & control it [CIT-002].",
                    "which_won": "The distribution gap outweighs the demand [CIT-002].",
                },
            },
            "sections": [
                {
                    "section_id": "sec-1",
                    "title": "Problem Context & Validation",
                    "order_index": 0,
                    "chunks": [
                        {"chunk_id": "c1", "chunk_index": 1, "text": "Residents lack time [CIT-001]."}
                    ],
                }
            ],
            "sources": {
                "CIT-001": {"url": "https://a.example.com?x=1&y=2", "domain": "a.example.com", "stance": "supports"},
                "CIT-002": {"url": "https://b.example.com", "domain": "b.example.com", "stance": "challenges"},
            },
            "unresolved_gaps": ["What the typical price point should be."],
        }

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "report.pdf"
            _render_pdf(output_path, draft)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            with open(output_path, "rb") as f:
                self.assertTrue(f.read(5).startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
