# app/utils/ranking_fusion.py
"""
Reciprocal Rank Fusion + near-duplicate diversification (gap-closing plan,
Stage 2f/2g).

RRF combines two independently-ranked lists (lexical, semantic) that score
on incomparable scales -- lexical is a hand-rolled sum of small integer/half
bonuses in roughly 0-15, cosine similarity is bounded 0-1 -- by using only
each list's *rank*, never its raw score, so nothing needs normalizing.
"""

from __future__ import annotations

import re
from typing import Hashable, TypeVar

T = TypeVar("T")

# From Cormack, Clarke & Buettcher (2009). Deliberately flattens the curve
# so that *appearing* in a ranked list matters far more than exact position
# within it -- see stratos-launch-plan Stage 2f for the worked example this
# constant is chosen to reproduce.
DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[Hashable]],
    *,
    k: int = DEFAULT_RRF_K,
) -> dict[Hashable, float]:
    """Fuse any number of ranked lists of item ids into one score per id.

    Each `ranked_lists[i]` is a sequence of ids, best first. An id absent
    from a list simply doesn't contribute a term for that list -- it isn't
    penalized beyond not getting the bonus, so a document only one system
    saw still ranks, just lower than one both systems agreed on.
    """
    scores: dict[Hashable, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_and_sort(
    ranked_lists: list[list[Hashable]],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[Hashable]:
    """Convenience wrapper: fuse, then return ids sorted best-first. Ties
    (e.g. an id that appeared in only one list, tied with another such id)
    keep their first-encountered relative order for determinism."""
    scores = reciprocal_rank_fusion(ranked_lists, k=k)
    return sorted(scores.keys(), key=lambda item_id: -scores[item_id])


# --------------------------------------------------------------------------
# Near-duplicate diversification.
#
# True MMR trades relevance against *embedding* similarity between
# candidates, which needs a per-item vector fetched back from Astra beyond
# what a plain query-time vector search returns. The concrete failure mode
# Stage 2g exists to fix -- "eight near-duplicate rewrites of one press
# release" -- is actually better caught by lexical overlap on the quote
# text than by semantic similarity: near-duplicate wire copy shares literal
# phrasing, which n-gram overlap detects directly and cheaply, with no
# extra Astra round-trip. This is a deliberate simplification, not an
# oversight -- see stratos-launch-plan Stage 2g.
# --------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")
_SHINGLE_SIZE = 5
_DEFAULT_SIMILARITY_THRESHOLD = 0.7


def _shingles(text: str, size: int = _SHINGLE_SIZE) -> set[str]:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


def diversify(
    items: list[T],
    *,
    text_fn,
    limit: int,
    similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
) -> list[T]:
    """Greedily select up to `limit` items from `items` (already ranked
    best-first), skipping any item whose text is a near-duplicate (5-word
    shingle Jaccard overlap above `similarity_threshold`) of one already
    selected. `text_fn(item) -> str` extracts the text to compare.

    A near-duplicate is dropped, not replaced by a runner-up search -- the
    next-best distinct item simply falls through from the ranked list on
    the next iteration, same as a normal top-k walk.
    """
    selected: list[T] = []
    selected_shingles: list[set[str]] = []

    for item in items:
        if len(selected) >= limit:
            break
        candidate_shingles = _shingles(text_fn(item))
        is_duplicate = any(
            _jaccard(candidate_shingles, existing) >= similarity_threshold
            for existing in selected_shingles
        )
        if is_duplicate:
            continue
        selected.append(item)
        selected_shingles.append(candidate_shingles)

    return selected
