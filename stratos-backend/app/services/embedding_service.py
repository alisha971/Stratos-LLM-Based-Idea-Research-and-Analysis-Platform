# app/services/embedding_service.py
"""
EmbeddingService (gap-closing plan Stage 2b/2c) -- the single place the
embedding provider is chosen, so a future swap touches one file.

Decision, verified live against this project's own Astra database (see
stratos-launch-plan Stage 2b) rather than assumed: Astra server-side
`$vectorize`, provider `nvidia`, model `NV-Embed-QA`, 1024 dimensions.
`nvidia` was confirmed the only provider on this database with keyless
auth (`db.get_database_admin().find_embedding_providers()`), and because
vectorize is server-side, this service sends raw text -- Astra calls
NVIDIA and applies query vs. passage mode itself, so there is no local
prefix-consistency logic to get wrong here.

This is the EVIDENCE embedding path (Stage 2c): scraped web chunks, trend
items, competitor profiles, vectorized on the ingestion (persist) path so
everything is ready by the time the Stage 1b research/trend/competitor
join completes. It is NOT the report-OUTPUT chunk embedding path --
embedding_worker.py's existing no-op dispatch from section_worker.py is
left untouched, the seed of a later deep-dive feature -- and it writes to
a different Astra collection (`embeddings`) than that future one would,
deliberately: see AstraEvidenceRepository.save_embedding_chunk.

Fail-soft throughout, delegating to AstraEvidenceRepository's existing
discipline: every method returns None/[] on any failure rather than
raising, so an Astra/NVIDIA hiccup degrades ranking to lexical-only
(evidence_ranker.py) instead of failing the run.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.services.astra_evidence_repository import (
    AstraEvidenceRepository,
    EmbeddingTooLargeError,
)
from app.utils.degradation import record_degradation

logger = logging.getLogger(__name__)

EMBEDDING_PROVIDER = "nvidia"
EMBEDDING_MODEL = "NV-Embed-QA"
EMBEDDING_DIMENSION = 1024
EMBEDDINGS_COLLECTION = "embeddings"

# Fix-audit Part 4: a hard character backstop before ANY text reaches
# $vectorize, independent of chunk_text's own budget -- three of the four
# call sites here (news snippets, trend item summaries, competitor
# profiles) never go through chunk_text at all, so they had no cap
# whatsoever. ~2 chars/token is a safe worst case for the URL/slug/number
# -dense text this pipeline actually handles (chunk_text budgets 500 chars
# against NV-Embed-QA's 512-TOKEN ceiling and still overflowed on exactly
# that kind of text -- see chunking.py). This is deliberately a coarse
# backstop, not a precise token count: EmbeddingTooLargeError below is the
# defensive second layer for whatever this estimate still gets wrong.
EMBEDDING_MAX_CHARS = 900

# What content_type is set to on documents in the `embeddings` collection.
# Not an exhaustive registry -- just the values this service's own callers
# (research_worker, trend_worker, competitor_worker) use today.
CONTENT_TYPE_WEB_CHUNK = "web_chunk"
CONTENT_TYPE_TREND_ITEM = "trend_item"
CONTENT_TYPE_COMPETITOR_PROFILE = "competitor_profile"


def _truncate_for_embedding(text: str, max_chars: int = EMBEDDING_MAX_CHARS) -> str:
    """Truncate to at most `max_chars`, preferring a word boundary near the
    cut so the tail isn't a mangled partial word. Returns `text` unchanged
    if it already fits."""
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    # Only back off to the word boundary if it doesn't throw away a large
    # chunk of the budget (e.g. one long unbroken run with no spaces at
    # all near the cut) -- a hard cut is better than losing most of the
    # budget for nothing.
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    return truncated.strip()


class EmbeddingService:
    def __init__(self, astra_repository: AstraEvidenceRepository | None = None) -> None:
        self.astra_repository = astra_repository or AstraEvidenceRepository()

    @property
    def enabled(self) -> bool:
        return self.astra_repository.enabled

    def save_chunk(
        self,
        *,
        report_id: str,
        content_type: str,
        text: str,
        source_id: str | None = None,
        evidence_id: str | None = None,
        chunk_index: int = 0,
        url: str | None = None,
        domain: str | None = None,
        stance: str | None = None,
        title: str | None = None,
    ) -> str | None:
        """Persist one evidence chunk, vectorized server-side at insert
        time. Returns the chunk's id, or None on any failure/if disabled.

        This is the single choke point every $vectorize write goes through
        (directly, or via save_chunks below) -- fix-audit Part 4's
        truncation guard and degradation recording both live here so they
        cover all four call sites (web chunks, news snippets, trend items,
        competitor profiles) at once, regardless of whether the caller
        pre-chunks its text.

        `title` (2026-09-14 remediation Phase 1.2): optional, e.g. a
        competitor's product name -- lets a semantic-only hit in
        EvidenceBundleService._item_from_semantic_hit show the real name
        instead of falling back to the bare domain. None for callers that
        don't have a natural title (e.g. plain web chunks); harmless.
        """
        if not text or not text.strip():
            return None

        text = _truncate_for_embedding(text.strip())
        chunk_id = str(uuid.uuid4())
        document = {
            "_id": chunk_id,
            "report_id": report_id,
            "content_type": content_type,
            "source_id": source_id,
            "evidence_id": evidence_id,
            "chunk_index": chunk_index,
            "url": url,
            "domain": domain,
            "stance": stance,
            "title": title,
            "text": text,
            "$vectorize": text,
        }

        if not self.enabled:
            return None

        try:
            saved_id = self.astra_repository.save_embedding_chunk(document)
        except EmbeddingTooLargeError:
            # Defensive second layer: EMBEDDING_MAX_CHARS is a coarse char
            # estimate, not a real token count, and can still be wrong for
            # unusually token-dense text. Halve once and retry with a
            # fresh id before giving up -- if this still overflows, it's
            # treated as a genuine failure like any other below, not
            # retried again.
            halved = _truncate_for_embedding(text[: max(len(text) // 2, 1)])
            document["_id"] = str(uuid.uuid4())
            document["text"] = halved
            document["$vectorize"] = halved
            try:
                saved_id = self.astra_repository.save_embedding_chunk(document)
            except EmbeddingTooLargeError:
                logger.warning(
                    "[EMBEDDING] Chunk still exceeds token limit after "
                    "halving report_id=%s content_type=%s; dropping",
                    report_id,
                    content_type,
                )
                saved_id = None

        if not saved_id:
            # Fix-audit Part 0/4: a dropped chunk degrades this report's
            # semantic ranking silently unless recorded -- every embedding
            # insert used to be able to fail this way with the run still
            # reporting success end to end.
            record_degradation(
                report_id,
                "embedding_chunk_save",
                f"embedding insert failed for content_type={content_type}",
            )
        return saved_id

    def save_chunks(
        self,
        *,
        report_id: str,
        content_type: str,
        chunks: list[str],
        source_id: str | None = None,
        evidence_id: str | None = None,
        url: str | None = None,
        domain: str | None = None,
        stance: str | None = None,
        title: str | None = None,
    ) -> int:
        """Persists every item in `chunks`, indexed in order. Returns how
        many actually saved -- a partial failure (some chunks saved, some
        not) is not itself an error, matching the fail-soft rule.

        2026-09-14 remediation Phase 4.3: tries ONE batched insert_many
        for the whole set first (one round-trip instead of N), then falls
        back to the original per-chunk save_chunk path -- WITH its full
        EmbeddingTooLargeError halve-and-retry and degradation recording
        -- for whichever chunks didn't confirm success in the batch call.
        The common case (every chunk succeeds, which the 2026-09-14 audit
        run's own §5 found true 100% of the time it exercised this path)
        now costs one Astra round-trip instead of len(chunks); the
        failure-handling guarantees are unchanged from before.

        `stance` here is only the Stage 3e provenance PRIOR, recorded on
        the chunk documents for visibility -- the AUTHORITATIVE stance
        used for ranking (Stage 3f) is looked up fresh from `Source.stance`
        after batch LLM classification, since stance is a source-level
        property that can be refined after these chunks are already
        written. See EvidenceBundleService._hybrid_rank_for_section."""
        if not chunks or not self.enabled:
            return 0

        # Build every document up front, truncated exactly as save_chunk
        # truncates a single one, so the batch path and the per-chunk
        # fallback path see byte-identical text.
        prepared: list[tuple[int, str, dict]] = []
        for index, text in enumerate(chunks):
            if not text or not text.strip():
                continue
            truncated = _truncate_for_embedding(text.strip())
            document = {
                "_id": str(uuid.uuid4()),
                "report_id": report_id,
                "content_type": content_type,
                "source_id": source_id,
                "evidence_id": evidence_id,
                "chunk_index": index,
                "url": url,
                "domain": domain,
                "stance": stance,
                "title": title,
                "text": truncated,
                "$vectorize": truncated,
            }
            prepared.append((index, truncated, document))

        if not prepared:
            return 0

        documents = [document for _, _, document in prepared]
        succeeded_ids, error = self.astra_repository.save_embedding_chunks_batch(documents)
        saved = len(succeeded_ids)

        if error is not None or saved < len(documents):
            for index, truncated, document in prepared:
                if document["_id"] in succeeded_ids:
                    continue
                chunk_id = self.save_chunk(
                    report_id=report_id,
                    content_type=content_type,
                    text=truncated,
                    source_id=source_id,
                    evidence_id=evidence_id,
                    chunk_index=index,
                    url=url,
                    domain=domain,
                    stance=stance,
                    title=title,
                )
                if chunk_id:
                    saved += 1

        return saved

    def find_similar(
        self,
        *,
        report_id: str,
        query_text: str,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """The semantic ranked list for one report, best match first. []
        on any failure or when Astra is disabled -- callers should treat
        that as "no semantic signal this time", not an error, and fall
        back to lexical-only ranking (Stage 2d)."""
        return self.astra_repository.find_similar_embeddings(
            report_id=report_id,
            query_text=query_text,
            limit=limit,
        )
