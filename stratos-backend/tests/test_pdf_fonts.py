"""app/utils/pdf_fonts.py (fix-audit Part 6a). Font registration is
idempotent and glyph-coverage checks run against Vera's REAL glyph table,
not a hand-maintained guess-list -- these tests pin down the specific
gap (U+2011 non-breaking hyphen, the reported symptom) and confirm
characters Vera already covers are left untouched."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.pdf_fonts import (
    FONT_BOLD,
    FONT_BOLD_ITALIC,
    FONT_ITALIC,
    FONT_NAME,
    register_pdf_fonts,
    sanitize_for_pdf_font,
)


class RegisterPdfFontsTests(unittest.TestCase):
    def test_idempotent_second_call_does_not_raise(self):
        register_pdf_fonts()
        register_pdf_fonts()  # must not raise (double registerFont, etc.)

    def test_registers_all_four_style_variants(self):
        from reportlab.pdfbase.pdfmetrics import getFont

        register_pdf_fonts()
        for name in (FONT_NAME, FONT_BOLD, FONT_ITALIC, FONT_BOLD_ITALIC):
            self.assertIsNotNone(getFont(name))  # raises KeyError if unregistered


class SanitizeForPdfFontTests(unittest.TestCase):
    def test_empty_and_none_pass_through(self):
        self.assertEqual(sanitize_for_pdf_font(""), "")

    def test_plain_ascii_untouched(self):
        text = "A perfectly ordinary sentence, with punctuation!"
        self.assertEqual(sanitize_for_pdf_font(text), text)

    def test_the_reported_symptom_non_breaking_hyphen(self):
        # The exact bug: "type 2\u2011diabetes" rendered as "type 2\u25a0diabetes"
        # (ReportLab's missing-glyph box) because U+2011 isn't in cp1252
        # AND isn't in Vera's own glyph table either.
        result = sanitize_for_pdf_font("type 2\u2011diabetes")
        self.assertEqual(result, "type 2-diabetes")

    def test_one_size_fits_all_example_from_the_bug_report(self):
        result = sanitize_for_pdf_font("a one\u2011size\u2011fits\u2011all approach")
        self.assertEqual(result, "a one-size-fits-all approach")

    def test_characters_vera_covers_are_left_untouched(self):
        # These must NOT be folded -- Vera has real glyphs for them, so
        # folding would be an unnecessary (and lossy) simplification.
        text = "em\u2014dash en\u2013dash \u201ccurly\u201d \u2018quotes\u2019 \u2022bullet\u2026 caf\u00e9 \u20ac100 \u2122"
        self.assertEqual(sanitize_for_pdf_font(text), text)

    def test_minus_sign_is_covered_by_vera_and_untouched(self):
        # Verified directly against Vera's glyph table: U+2212 IS present,
        # unlike U+2011 -- must not be folded either.
        text = "the result was \u22125"
        self.assertEqual(sanitize_for_pdf_font(text), text)

    def test_manual_fold_table_entries(self):
        self.assertEqual(sanitize_for_pdf_font("\u2010"), "-")  # hyphen
        self.assertEqual(sanitize_for_pdf_font("\u2012"), "-")  # figure dash
        self.assertEqual(sanitize_for_pdf_font("\u2032"), "'")  # prime
        self.assertEqual(sanitize_for_pdf_font("\u2044"), "/")  # fraction slash
        self.assertEqual(sanitize_for_pdf_font("\u2192"), "->")  # right arrow

    def test_common_accented_latin_already_covered_by_vera_is_untouched(self):
        # Vera's Latin-1 Supplement coverage is broad -- a common accented
        # character like "i with diaeresis" already has a real glyph and
        # must be left alone, not needlessly degraded to ASCII.
        result = sanitize_for_pdf_font("na\u00efve")
        self.assertEqual(result, "na\u00efve")

    def test_uncovered_accented_latin_degrades_via_nfkd_rather_than_boxing(self):
        # Verified directly against Vera's glyph table: Vietnamese
        # combining-diacritic characters (dot-below) are a real gap --
        # the generic NFKD fallback must still produce something
        # readable instead of a missing-glyph box.
        result = sanitize_for_pdf_font("Vi\u1ec7t Nam")  # "Vi\u1ec7t Nam"
        self.assertEqual(result, "Viet Nam")

    def test_emoji_is_dropped_not_boxed(self):
        result = sanitize_for_pdf_font("Great idea \u2705\U0001F680!")
        self.assertNotIn("\u2705", result)
        self.assertNotIn("\U0001F680", result)
        self.assertIn("Great idea", result)
        self.assertIn("!", result)

    def test_mixed_content_folds_only_what_needs_folding(self):
        result = sanitize_for_pdf_font("Cost\u2011effective solutions cost $10\u201320 per unit.")
        self.assertEqual(result, "Cost-effective solutions cost $10\u201320 per unit.")


if __name__ == "__main__":
    unittest.main()
