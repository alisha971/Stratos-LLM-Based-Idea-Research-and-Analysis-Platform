# app/services/markdown_pdf.py
"""Markdown -> ReportLab flowables (fix-audit Part 6b).

`chunk.text` is already markdown: the frontend renders it with
react-markdown (ReportSplitPanel.tsx) and globals.css styles
p/ul/ol/li/strong/a/h1-h4/blockquote. export_worker.py used to XML-escape
the whole string and hand it to a single Paragraph, which flattened all of
that structure to literal characters ("**bold**", "- bullet") and
collapsed every newline into one run-on paragraph. This module parses the
same text with mistune (AST mode, GFM table plugin) and maps it onto
ReportLab flowables -- Paragraph, ListFlowable, Table -- so the web and
PDF views of one chunk render as the same document, not two different
ones.

Security posture, matching the frontend's own deliberate choice not to
pass rehype-raw to react-markdown: a markdown LINK's href is authored by
the model, not vetted (a quick manual check confirms mistune parses
`[text](javascript:alert(1))` into a real link token with that href
verbatim), so it is never turned into a clickable `<a>` tag here -- only
this module's own citation-marker substitution, against the assembler's
`sources` dict (built from real ingested Source rows), ever creates a
link. A markdown link's visible text still renders; its href is discarded.
Any raw inline/block HTML in the markdown is treated as plain text (never
passed through unescaped), for the same reason.
"""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

import mistune
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.utils.pdf_fonts import sanitize_for_pdf_font

_MARKER_RE = re.compile(r"\[CIT-\d{3}\]")
_LINK_COLOR = "#245c3d"  # the existing brand moss green, matches export_worker.py

# Usable width inside SimpleDocTemplate's default letter-page margins
# (1 inch each side of an 8.5in page) -- tables are explicitly sized to
# this so long cell text wraps instead of overflowing the page.
_PAGE_CONTENT_WIDTH = 6.3 * inch

_markdown_parser = mistune.create_markdown(renderer=None, plugins=["table", "strikethrough"])


def render_markdown(text: str, sources: dict[str, Any], styles) -> list:
    """Parse `text` as markdown and return a list of ReportLab flowables
    (Paragraph / ListFlowable / Table / Spacer). `sources` is the
    assembler's `marker -> {url, domain, title, stance}` dict, used to
    turn a `[CIT-001]`-style marker into a real link -- the SAME lookup
    export_worker.py's own `_linkify` already used, just reachable from
    inside table cells and list items now too.

    Runs `sanitize_for_pdf_font` (fix-audit Part 6a) before parsing, so
    this function is self-sufficient for producing PDF-safe output
    regardless of caller discipline -- sanitizing again if a caller
    already did is a harmless no-op (ASCII text short-circuits instantly).

    Returns [] for empty/whitespace-only input.
    """
    if not text or not text.strip():
        return []

    tokens = _markdown_parser(sanitize_for_pdf_font(text))

    flowables: list = []
    for token in tokens:
        flowables.extend(_render_block(token, sources, styles))
    return flowables


def _fold_unicode(text: str) -> str:
    for src, dst in _UNICODE_FOLD.items():
        text = text.replace(src, dst)
    return text


def _blockquote_style(styles) -> ParagraphStyle:
    base = styles["BodyText"]
    return ParagraphStyle(
        "MarkdownBlockquote",
        parent=base,
        leftIndent=base.leftIndent + 16,
        borderColor=colors.HexColor("#c9c9c9"),
        borderWidth=0,
        textColor=colors.HexColor("#555555"),
    )


def _render_block(token: dict, sources: dict, styles) -> list:
    ttype = token.get("type")

    if ttype == "paragraph":
        return [Paragraph(_render_inline(token.get("children", []), sources), styles["BodyText"])]

    if ttype == "heading":
        level = token.get("attrs", {}).get("level", 3)
        # Capped at Heading4: a chunk's own heading must never visually
        # outrank the section's own Heading2 in export_worker.py.
        style_name = "Heading3" if level <= 3 else "Heading4"
        style = styles.get(style_name) or styles["Heading3"]
        return [Paragraph(_render_inline(token.get("children", []), sources), style)]

    if ttype == "list":
        return [_render_list(token, sources, styles)]

    if ttype == "table":
        return [_render_table(token, sources, styles), Spacer(1, 8)]

    if ttype == "block_quote":
        style = _blockquote_style(styles)
        flowables = []
        for child in token.get("children", []):
            for rendered in _render_block(child, sources, styles):
                # Re-style plain paragraphs to the indented blockquote
                # look; leave anything else (a nested list/table) as-is.
                if isinstance(rendered, Paragraph):
                    flowables.append(Paragraph(rendered.text, style))
                else:
                    flowables.append(rendered)
        return flowables

    if ttype == "block_text":
        # Tight list-item text -- return the inline markup string, not a
        # Paragraph; _render_list wraps it.
        return [_render_inline(token.get("children", []), sources)]

    if ttype in ("blank_line", "thematic_break"):
        return []

    if ttype == "block_html":
        # Raw block-level HTML the model wrote -- escape and keep it
        # VISIBLE, same posture as inline_html below: never rendered as
        # markup, but not silently dropped either.
        raw = token.get("raw", "")
        return [Paragraph(escape(raw), styles["BodyText"])] if raw.strip() else []

    # Unknown/unhandled block type: recurse into children rather than
    # silently dropping content the model wrote.
    children = token.get("children")
    if isinstance(children, list):
        flowables = []
        for child in children:
            if isinstance(child, dict) and "type" in child:
                flowables.extend(_render_block(child, sources, styles))
        return flowables
    return []


def _render_list(token: dict, sources: dict, styles) -> ListFlowable:
    ordered = bool(token.get("attrs", {}).get("ordered"))
    items = []
    for item in token.get("children", []):
        item_flowables: list = []
        for child in item.get("children", []):
            if child.get("type") == "block_text":
                item_flowables.append(
                    Paragraph(
                        _render_inline(child.get("children", []), sources),
                        styles["BodyText"],
                    )
                )
            else:
                item_flowables.extend(_render_block(child, sources, styles))
        if not item_flowables:
            continue
        items.append(ListItem(item_flowables, spaceAfter=4))

    return ListFlowable(
        items,
        bulletType="1" if ordered else "bullet",
        leftIndent=20,
        bulletFontSize=styles["BodyText"].fontSize,
    )


def _render_table(token: dict, sources: dict, styles) -> Table:
    header_cells: list[str] = []
    body_rows: list[list[str]] = []

    for section in token.get("children", []):
        row_source = section.get("children", [])
        if section.get("type") == "table_head":
            header_cells = [_table_cell_paragraph(c, sources, styles, header=True) for c in row_source]
        elif section.get("type") == "table_body":
            for row in row_source:
                body_rows.append(
                    [
                        _table_cell_paragraph(c, sources, styles, header=False)
                        for c in row.get("children", [])
                    ]
                )

    data = ([header_cells] if header_cells else []) + body_rows
    if not data:
        return Table([[""]])

    col_count = max(len(row) for row in data)
    col_width = _PAGE_CONTENT_WIDTH / col_count

    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1 if header_cells else 0)
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d0d0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if header_cells:
        style_commands.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ee")))
        style_commands.append(("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"))
    table.setStyle(TableStyle(style_commands))
    return table


def _table_cell_paragraph(cell: dict, sources: dict, styles, *, header: bool) -> Paragraph:
    style = styles["BodyText"]
    inline = _render_inline(cell.get("children", []), sources)
    if header:
        inline = f"<b>{inline}</b>"
    return Paragraph(inline, style)


def _render_inline(children: list[dict], sources: dict) -> str:
    """Render inline AST nodes to a ReportLab mini-HTML string: escape
    text leaves, then inject markup -- never the other way around, or an
    injected tag would itself get escaped into literal text (the same
    rule export_worker.py's original `_linkify` already followed)."""
    return "".join(_render_inline_node(child, sources) for child in children)


def _render_inline_node(node: dict, sources: dict) -> str:
    ntype = node.get("type")

    if ntype == "text":
        return _linkify_citations(escape(node.get("raw", "")), sources)

    if ntype == "codespan":
        return f'<font face="Courier">{escape(node.get("raw", ""))}</font>'

    if ntype in ("linebreak", "softbreak"):
        return "<br/>"

    if ntype == "strong":
        return f"<b>{_render_inline(node.get('children', []), sources)}</b>"

    if ntype == "emphasis":
        return f"<i>{_render_inline(node.get('children', []), sources)}</i>"

    if ntype == "strikethrough":
        return f"<strike>{_render_inline(node.get('children', []), sources)}</strike>"

    if ntype == "link":
        # Security: the href is model-authored and never trusted (see
        # module docstring) -- render the link's visible text only.
        return _render_inline(node.get("children", []), sources)

    if ntype == "image":
        return escape(node.get("attrs", {}).get("alt", "") or "")

    if ntype == "inline_html":
        # Raw HTML-like text the model wrote (e.g. "<huge>", "<100") --
        # mistune tags ANY <word>-shaped run as inline_html per CommonMark,
        # not just real tags. Escape and keep it VISIBLE as plain text
        # (same posture as the frontend's no-rehype-raw choice: never
        # rendered as markup, but not silently dropped either).
        return escape(node.get("raw", ""))

    # Unknown inline type -- render children as plain text if any, else
    # drop silently rather than risk unescaped markup reaching the PDF.
    children = node.get("children")
    if isinstance(children, list):
        return _render_inline(children, sources)
    return ""


def _linkify_citations(escaped_text: str, sources: dict) -> str:
    """Turn `[CIT-001]` into a real link when `sources` has a URL for it --
    operates on ALREADY-ESCAPED text, exactly like export_worker.py's
    original `_linkify`, just reusable from inside table cells and list
    items."""

    def _replace(match: re.Match) -> str:
        marker = match.group(0)[1:-1]
        info = sources.get(marker)
        url = info.get("url") if info else None
        if not url:
            return match.group(0)
        return f'<a href="{escape(url)}" color="{_LINK_COLOR}"><u>{match.group(0)}</u></a>'

    return _MARKER_RE.sub(_replace, escaped_text)
