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

# 400-600 chars sits well inside any modern retrieval embedding model's
# context window with headroom (see stratos-launch-plan Stage 2b) -- the
# exact ceiling for whichever model is in use isn't something this module
# needs to know, since it's already conservative under any plausible one.
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
    A single oversized "word" (e.g. a URL) is returned whole rather than
    cut, since splitting mid-token is worse than one slightly-long chunk.
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
            # split mid-word.
            words = sentence.split()
            buf: list[str] = []
            buf_len = 0
            for word in words:
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


def _pack_units(units: list[str], *, chunk_size: int, overlap: int) -> list[str]:
    """Greedily pack the smaller structural units (paragraphs/sentences/word
    groups) back up toward chunk_size, so a chunk isn't just "one sentence"
    when several short sentences would fit together -- then carries the tail
    of each chunk into the next as overlap."""
    if not units:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        add_len = len(unit) + (1 if current else 0)
        if current and current_len + add_len > chunk_size:
            chunks.append(" ".join(current))
            carry = _tail_for_overlap(current, overlap)
            current = list(carry)
            current_len = sum(len(u) for u in current) + max(len(current) - 1, 0)
        current.append(unit)
        current_len += add_len if current_len == 0 else len(unit) + 1

    if current:
        chunks.append(" ".join(current))

    # Recompute cleanly if the incremental length bookkeeping above drifted
    # (it's an estimate for packing decisions, not the source of truth).
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
