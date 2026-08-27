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

import uuid
from typing import Any

from app.services.astra_evidence_repository import AstraEvidenceRepository

EMBEDDING_PROVIDER = "nvidia"
EMBEDDING_MODEL = "NV-Embed-QA"
EMBEDDING_DIMENSION = 1024
EMBEDDINGS_COLLECTION = "embeddings"

# What content_type is set to on documents in the `embeddings` collection.
# Not an exhaustive registry -- just the values this service's own callers
# (research_worker, trend_worker, competitor_worker) use today.
CONTENT_TYPE_WEB_CHUNK = "web_chunk"
CONTENT_TYPE_TREND_ITEM = "trend_item"
CONTENT_TYPE_COMPETITOR_PROFILE = "competitor_profile"


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
    ) -> str | None:
        """Persist one evidence chunk, vectorized server-side at insert
        time. Returns the chunk's id, or None on any failure/if disabled."""
        if not text or not text.strip():
            return None

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
            "text": text,
            "$vectorize": text,
        }
        return self.astra_repository.save_embedding_chunk(document)

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
    ) -> int:
        """save_chunk for each item in `chunks`, indexed in order. Returns
        how many actually saved -- a partial failure (some chunks saved,
        some not) is not itself an error, matching the fail-soft rule."""
        saved = 0
        for index, text in enumerate(chunks):
            chunk_id = self.save_chunk(
                report_id=report_id,
                content_type=content_type,
                text=text,
                source_id=source_id,
                evidence_id=evidence_id,
                chunk_index=index,
                url=url,
                domain=domain,
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
