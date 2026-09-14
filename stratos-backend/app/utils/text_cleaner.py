# TODO: BeautifulSoup-based boilerplate removal
# TODO: Min-length threshold

from bs4 import BeautifulSoup

# Fix-audit Part 4: block-level tags whose text is joined with a blank line
# between them, so chunking.py's paragraph-boundary splitter (`\n\s*\n`)
# has real paragraph boundaries to find. Not exhaustive HTML -- just the
# common containers of a distinct "paragraph" of meaning on a scraped page.
_BLOCK_TAGS = [
    "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "td", "th", "article", "section", "pre",
]


def clean_html(html: str) -> str:
    """Strip boilerplate tags and return text with paragraph structure
    preserved (blocks joined by a blank line).

    Previously used `soup.get_text(separator="\\n")` globally, which put a
    single newline between EVERY tag's text indiscriminately -- a
    paragraph break and a mid-paragraph line break in the source HTML
    became indistinguishable, `_PARAGRAPH_SPLIT` in chunking.py
    (`\\n\\s*\\n`) never matched, and the entire page arrived at
    chunk_text as one giant
    "paragraph". That forced the sentence tier, and on boilerplate-heavy
    pages (nav/menus/link lists with little punctuation) the word tier --
    exactly the token-dense text that overflowed the embedding model's
    token limit. Joining at actual block-element boundaries instead gives
    chunk_text real paragraphs to split on, independent of that size fix.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    blocks = []
    for element in soup.find_all(_BLOCK_TAGS):
        # Skip a block whose own text is already covered by a nested block
        # collected separately (e.g. a <div> wrapping a <p>) -- avoids
        # duplicating the same text once per ancestor.
        if element.find(_BLOCK_TAGS):
            continue
        text = element.get_text(separator=" ").strip()
        if text:
            blocks.append(text)

    if not blocks:
        # No block-level structure at all (a bare text node, a malformed
        # fragment) -- fall back to the whole document as one block rather
        # than returning nothing.
        whole = soup.get_text(separator=" ").strip()
        blocks = [whole] if whole else []

    normalized = []
    for block in blocks:
        # normalize unicode, then collapse whitespace runs WITHIN a block
        # (get_text(separator=" ") can leave doubled spaces/newlines from
        # nested inline tags) without touching the blank-line boundaries
        # between blocks.
        block = block.replace("\u00a0", " ").replace("\u200b", "")
        block = " ".join(block.split())
        if block:
            normalized.append(block)

    return "\n\n".join(normalized)
