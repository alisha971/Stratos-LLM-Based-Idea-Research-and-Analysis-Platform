# app/utils/chunking.py
"""
Recursive character chunking (gap-closing plan, Stage 2a).

Replaces the old "first 5 valid lines" extraction in
research_service.scrape_and_extract, which threw away everything below the
fold on a page and treated each raw HTML line -- often a heading or half a
sentence -- as an independent unit of meaning.

Splits on the largest natural boundary that fits within the size budget:
paragraph -> sentence -> word. This is the standard default (popularized by
LangChain's RecursiveCharacterTextSplitter) and needs no new dependency.
"""

from __future__ import annotations

import re

# 400-600 chars was assumed to sit well inside any modern retrieval
# embedding model's context window (see stratos-launch-plan Stage 2b), on
# the premise that this module doesn't need to know the exact per-model
# token ceiling since it's already conservative under any plausible one.
# Fix-audit Part 4: that premise doesn't hold -- this budget is CHARACTERS
# while NV-Embed-QA's limit is 512 TOKENS, and on token-dense text (URLs,
# slugs, numbers, punctuation -- exactly what boilerplate-heavy scraped
# pages are full of) a 500-char chunk can still overflow it. This module
# still doesn't need to know the exact ceiling, but the two bugs that made
# an emitted chunk exceed even ITS OWN budget are fixed below (an oversized
# single "word" is now hard-split instead of emitted whole, and the pack
# loop re-checks actual joined length instead of an incremental estimate);
# EMBEDDING_MAX_CHARS in embedding_service.py is the actual hard backstop
# against the token limit, independent of this budget.
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP_RATIO = 0.12

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
# Sentence boundary: a run of .!? followed by whitespace and a capital/digit,
# or end of string. Deliberately simple -- this doesn't need to be a full
# sentence tokenizer, just good enough to avoid mid-sentence cuts most of
# the time.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    """Split `text` into chunks of roughly `chunk_size` characters, preferring
    to break on paragraph boundaries, then sentence boundaries, then words --
    never mid-word. Adjacent chunks overlap by `overlap_ratio` so a claim
    straddling a boundary survives intact in at least one chunk.

    Returns [] for empty/whitespace-only input. A single chunk shorter than
    `chunk_size` is returned as-is (no padding, no empty overlap).
    """
    text = (text or "").strip()
    if not text:
        return []

    overlap = int(chunk_size * overlap_ratio)
    units = _split_into_units(text, chunk_size)
    return _pack_units(units, chunk_size=chunk_size, overlap=overlap)


def _split_into_units(text: str, chunk_size: int) -> list[str]:
    """Break text into pieces no larger than chunk_size, preferring the
    largest structural boundary that fits: paragraph -> sentence -> word.

    Fix-audit Part 4: a single oversized "word" (a URL, a base64 blob, a
    concatenated nav string with no spaces) used to be returned whole,
    which is exactly the kind of token-dense text that overflows an
    embedding model's token limit at a fraction of chunk_size's character
    budget. There's no natural boundary inside it anyway, so it is now
    hard-split on character count -- no worse than the token-dense text
    already is, and every OTHER unit returned by this function is still
    cut only at a word boundary.
    """
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= chunk_size:
            units.append(paragraph)
            continue

        for sentence in _SENTENCE_SPLIT.split(paragraph):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= chunk_size:
                units.append(sentence)
                continue

            # Sentence itself is too long (rare: no punctuation, a long
            # run-on) -- fall back to word-level packing so we still never
            # split mid-word, except for a single word that is itself
            # over budget (see docstring).
            words = sentence.split()
            buf: list[str] = []
            buf_len = 0
            for word in words:
                if len(word) > chunk_size:
                    if buf:
                        units.append(" ".join(buf))
                        buf, buf_len = [], 0
                    units.extend(
                        word[start : start + chunk_size]
                        for start in range(0, len(word), chunk_size)
                    )
                    continue

                add_len = len(word) + (1 if buf else 0)
                if buf and buf_len + add_len > chunk_size:
                    units.append(" ".join(buf))
                    buf, buf_len = [], 0
                    add_len = len(word)
                buf.append(word)
                buf_len += add_len
            if buf:
                units.append(" ".join(buf))

    return units


def _joined_len(parts: list[str]) -> int:
    return sum(len(p) for p in parts) + max(len(parts) - 1, 0)


def _pack_units(units: list[str], *, chunk_size: int, overlap: int) -> list[str]:
    """Greedily pack the smaller structural units (paragraphs/sentences/word
    groups) back up toward chunk_size, so a chunk isn't just "one sentence"
    when several short sentences would fit together -- then carries the tail
    of each chunk into the next as overlap.

    Fix-audit Part 4: re-checks the ACTUAL joined length before adding a
    unit (not an incrementally-tracked estimate -- the previous version's
    bookkeeping could drift, and its own comment admitted as much without
    actually correcting for it), both before AND after seeding the overlap
    carry, so an emitted chunk can no longer exceed chunk_size. Previously
    the carry -- built from whole units, itself up to `overlap` chars --
    was appended to unconditionally, letting a chunk reach roughly 2x
    chunk_size before the next boundary check fired.
    """
    if not units:
        return []

    chunks: list[str] = []
    current: list[str] = []

    for unit in units:
        if current and _joined_len(current) + 1 + len(unit) > chunk_size:
            chunks.append(" ".join(current))
            current = _tail_for_overlap(current, overlap)
            if current and _joined_len(current) + 1 + len(unit) > chunk_size:
                # The overlap carry alone already leaves no room -- flush
                # it standalone rather than stacking the next unit on top.
                chunks.append(" ".join(current))
                current = []
        current.append(unit)

    if current:
        chunks.append(" ".join(current))

    return chunks


def _tail_for_overlap(units: list[str], overlap: int) -> list[str]:
    """The last few units of a just-finished chunk, up to `overlap` chars,
    carried forward as the start of the next chunk."""
    if overlap <= 0:
        return []

    tail: list[str] = []
    tail_len = 0
    for unit in reversed(units):
        tail_len += len(unit) + (1 if tail else 0)
        tail.insert(0, unit)
        if tail_len >= overlap:
            break
    return tail
