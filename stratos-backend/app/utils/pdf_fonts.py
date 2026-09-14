# app/utils/pdf_fonts.py
"""Unicode font registration and glyph-coverage sanitization for the PDF
export path (fix-audit Part 6a).

Root cause: app/workers/export_worker.py used `getSampleStyleSheet()`
unmodified, so every style resolved to a built-in Type 1 font (Helvetica)
under WinAnsiEncoding (cp1252). Any codepoint outside cp1252 renders as
ReportLab's substitution box -- cp1252 covers the plain em/en dash, so the
"boxes wherever the model wrote an en-dash/non-breaking hyphen" symptom
was almost certainly U+2011 (non-breaking hyphen) and similar punctuation
cp1252 does not cover.

Font choice: Bitstream Vera Sans, bundled with reportlab itself
(reportlab/fonts/Vera*.ttf) -- not a separately vendored TTF. Verified
directly against this font's own glyph table (see `_covered` below) rather
than assumed: it covers the vast majority of punctuation an LLM emits
(en/em dash, curly quotes, bullet, ellipsis, NBSP, degree, trademark,
comparison operators) but NOT U+2011 specifically, nor a few rarer marks
(U+2010 hyphen, U+2012 figure dash, prime, fraction slash, arrows) or
emoji. Since it ships inside reportlab -- already a hard dependency -- it
requires no new vendored binary, no download step, and is guaranteed
present in exactly the same form on Windows and in the deployed
container, which a system font would not be.

`sanitize_for_pdf_font` closes the remaining gap generically: it checks
the font's ACTUAL glyph table for each character (a small manual table
only for cases with an obvious same-width ASCII substitute, e.g. an
en-dash-like hyphen variant), rather than hand-maintaining an
enumeration of every character an LLM might ever emit -- a character
nobody thought to test still degrades to a sensible fallback (or is
dropped) instead of reproducing this exact bug in a new guise.
"""

from __future__ import annotations

import os
import unicodedata

import reportlab
from reportlab.pdfbase.pdfmetrics import registerFont, registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = "Vera"
FONT_BOLD = "Vera-Bold"
FONT_ITALIC = "Vera-Italic"
FONT_BOLD_ITALIC = "Vera-BoldItalic"

_FONT_DIR = os.path.join(os.path.dirname(reportlab.__file__), "fonts")

# Characters with a real, correctly-shaped glyph in Vera that some OTHER
# character merely looks similar to -- a same-width ASCII substitute is
# strictly better here than the generic NFKD fallback below would produce.
_MANUAL_FOLD = {
    "‐": "-",   # hyphen
    "‑": "-",   # non-breaking hyphen -- the reported symptom
    "‒": "-",   # figure dash
    "′": "'",   # prime
    "⁄": "/",   # fraction slash
    "←": "<-",  # leftwards arrow
    "→": "->",  # rightwards arrow
    "↔": "<->", # left-right arrow
}

_registered = False
_face = None


def register_pdf_fonts() -> None:
    """Idempotent -- safe to call at the top of every export task."""
    global _registered
    if _registered:
        return

    registerFont(TTFont(FONT_NAME, os.path.join(_FONT_DIR, "Vera.ttf")))
    registerFont(TTFont(FONT_BOLD, os.path.join(_FONT_DIR, "VeraBd.ttf")))
    registerFont(TTFont(FONT_ITALIC, os.path.join(_FONT_DIR, "VeraIt.ttf")))
    registerFont(TTFont(FONT_BOLD_ITALIC, os.path.join(_FONT_DIR, "VeraBI.ttf")))
    registerFontFamily(
        FONT_NAME,
        normal=FONT_NAME,
        bold=FONT_BOLD,
        italic=FONT_ITALIC,
        boldItalic=FONT_BOLD_ITALIC,
    )
    _registered = True


def _covered(ch: str) -> bool:
    global _face
    if _face is None:
        _face = TTFont("_VeraCoverageCheck", os.path.join(_FONT_DIR, "Vera.ttf")).face
    return _face.charToGlyph.get(ord(ch)) is not None


def sanitize_for_pdf_font(text: str) -> str:
    """Fold/strip characters the registered font can't render, so an
    unmapped codepoint degrades to a readable substitute instead of
    ReportLab's missing-glyph box. Plain ASCII short-circuits immediately;
    only non-ASCII characters pay the per-character glyph-table check."""
    if not text:
        return text

    out: list[str] = []
    for ch in text:
        if ch in _MANUAL_FOLD:
            out.append(_MANUAL_FOLD[ch])
            continue
        if ord(ch) < 128 or _covered(ch):
            out.append(ch)
            continue
        # Generic fallback for anything not explicitly handled above:
        # strip accents via NFKD decomposition (an accented Latin letter
        # not directly in Vera still degrades to its unaccented base
        # letter), and drop anything that still isn't ASCII-representable
        # (emoji, CJK, etc.) rather than emit an unreadable box.
        decomposed = unicodedata.normalize("NFKD", ch)
        out.append(decomposed.encode("ascii", "ignore").decode("ascii"))

    return "".join(out)
