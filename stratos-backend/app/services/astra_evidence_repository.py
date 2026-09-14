from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Fix-audit Part 4: substrings NVIDIA/Astra's $vectorize error carries when
# an insert is rejected for exceeding the embedding model's token limit
# (observed: "Input length 513 exceeds maximum allowed token size 512").
# Matched against str(exc) rather than a specific SDK exception class/
# attribute, since that's robust to astrapy version differences and to
# whether the error body is even valid JSON.
_TOKEN_LIMIT_MARKERS = ("exceeds maximum allowed token size", "maximum context length")


class EmbeddingTooLargeError(Exception):
    """Raised by save_embedding_chunk specifically when the embedding
    provider rejects an insert for exceeding its token limit. Every OTHER
    failure mode (network, auth, Astra down, collection missing) is still
    swallowed and returns None, per this repository's fail-soft contract --
    this one exception exists only so a caller that can do something about
    it (EmbeddingService.save_chunk: shrink the text and retry once) has a
    way to tell the two apart. Callers that don't care can ignore it
    entirely and the insert still just quietly didn't happen."""


class AstraEvidenceRepository:
    """
    Thin, fail-soft Astra repository for MVP evidence handoff.

    The research worker stores raw evidence in `evidence`. Section writing can
    first read cached per-section bundles from `evidence_bundles`, then fall
    back to flattened raw evidence from `evidence`.
    """

    def __init__(self) -> None:
        self.endpoint = settings.ASTRA_DB_ENDPOINT
        self.token = settings.ASTRA_DB_APPLICATION_TOKEN
        self.keyspace = os.getenv("ASTRA_DB_KEYSPACE")
        self._db = None

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.token)

    def save_evidence_document(self, document: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        evidence_id = document.get("evidence_id")
        payload = dict(document)
        if evidence_id:
            payload.setdefault("_id", evidence_id)

        try:
            self._collection("evidence").insert_one(payload)
            return evidence_id
        except Exception:
            logger.exception("[ASTRA] Failed to save evidence document")
            return None

    def save_trend_item(self, document: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        trend_item_id = document.get("trend_item_id")
        payload = dict(document)
        if trend_item_id:
            payload.setdefault("_id", trend_item_id)

        try:
            self._collection("trend_items").insert_one(payload)
            return trend_item_id
        except Exception:
            logger.exception("[ASTRA] Failed to save trend item")
            return None

    def save_competitor_insight(self, document: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        insight_id = document.get("insight_id")
        payload = dict(document)
        if insight_id:
            payload.setdefault("_id", insight_id)

        try:
            self._collection("competitor_insights").insert_one(payload)
            return insight_id
        except Exception:
            logger.exception("[ASTRA] Failed to save competitor insight")
            return None

    def list_evidence(self, report_id: str, limit: int = 500) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        try:
            cursor = self._collection("evidence").find(
                {"report_id": report_id},
                limit=limit,
            )
            return [dict(item) for item in cursor]
        except Exception:
            logger.exception("[ASTRA] Failed to list evidence for report_id=%s", report_id)
            return []

    def save_evidence_bundle(self, bundle: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        bundle_id = bundle.get("bundle_id")
        payload = dict(bundle)
        if bundle_id:
            payload.setdefault("_id", bundle_id)

        try:
            query = {
                "report_id": bundle["report_id"],
                "section_id": bundle["section_id"],
            }
            self._delete_many("evidence_bundles", query)
            self._collection("evidence_bundles").insert_one(payload)
            return bundle_id
        except Exception:
            logger.exception("[ASTRA] Failed to save evidence bundle")
            return None

    def get_evidence_bundle(
        self,
        report_id: str,
        section_id: str | None = None,
        section_title: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        query: dict[str, Any] = {"report_id": report_id}
        if section_id:
            query["section_id"] = section_id
        elif section_title:
            query["section_title"] = section_title
        else:
            return None

        try:
            result = self._collection("evidence_bundles").find_one(query)
            return dict(result) if result else None
        except Exception:
            logger.exception("[ASTRA] Failed to get evidence bundle")
            return None

    # --------------------------------------------------
    # Vector collection (gap-closing plan Stage 2b/2c/2d)
    #
    # Separate collection from `evidence`/`trend_items`/`competitor_insights`
    # above -- those hold the raw ingested documents; `embeddings` holds
    # chunked, vectorized evidence for semantic ranking. Also deliberately
    # separate from any future report-OUTPUT chunk collection: mixing input
    # evidence and a report's own written chunks in one collection would let
    # a query that forgets a content_type filter pull the section writer's
    # own text back in as if it were fresh evidence. See EmbeddingService
    # for the provider/model this collection is configured with, and
    # scripts/ensure_astra_collections.py for how it gets created.
    # --------------------------------------------------
    def save_embedding_chunk(self, document: dict[str, Any]) -> str | None:
        """Returns the chunk id, or None on any failure/if disabled.

        Raises `EmbeddingTooLargeError` specifically when the provider
        rejected the insert for exceeding its token limit -- every other
        failure is still swallowed here per the fail-soft contract above.
        """
        if not self.enabled:
            return None

        chunk_id = document.get("_id")
        try:
            self._collection("embeddings").insert_one(dict(document))
            return chunk_id
        except Exception as exc:
            message = str(exc).lower()
            if any(marker in message for marker in _TOKEN_LIMIT_MARKERS):
                raise EmbeddingTooLargeError(str(exc)) from exc
            logger.exception("[ASTRA] Failed to save embedding chunk")
            return None

    def save_embedding_chunks_batch(
        self, documents: list[dict[str, Any]]
    ) -> tuple[set[str], Exception | None]:
        """2026-09-14 remediation Phase 4.3: batched insert -- one
        round-trip for the common case where every document succeeds,
        instead of EmbeddingService.save_chunks' old per-chunk insert_one
        loop (the audited E2E run's own §5 found 35 serial embedding
        writes in one research pass alone).

        `ordered=False` (astrapy's own default) so one bad document in
        the batch doesn't block the rest from being attempted.

        Returns (successfully_inserted_ids, error_or_none). Deliberately
        does NOT attempt per-document EmbeddingTooLargeError detection
        here -- astrapy's CollectionInsertManyException exposes a pooled
        set of underlying exceptions, not a clean per-document mapping.
        Instead: the caller (EmbeddingService.save_chunks) falls back to
        the proven single-document save_embedding_chunk path -- which DOES
        do that detection, plus the halve-and-retry -- for whatever isn't
        in `successfully_inserted_ids`. This never regresses correctness
        versus the old per-document loop; it only removes the round-trips
        for the common fully-successful case."""
        if not self.enabled or not documents:
            return set(), None

        try:
            result = self._collection("embeddings").insert_many(documents, ordered=False)
            return set(result.inserted_ids), None
        except Exception as exc:
            # astrapy's CollectionInsertManyException carries inserted_ids
            # for the documents that DID succeed before/around the
            # failure(s); a connection-level exception won't have this
            # attribute at all, hence the getattr default.
            inserted = set(getattr(exc, "inserted_ids", None) or [])
            logger.warning(
                "[ASTRA] Batch embedding insert partial/full failure "
                "(%d/%d succeeded): %s",
                len(inserted),
                len(documents),
                exc,
            )
            return inserted, exc

    def find_similar_embeddings(
        self,
        report_id: str,
        query_text: str,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Vector search scoped to one report, ranked by similarity to
        `query_text`. Both the stored chunks and this query are embedded
        server-side by Astra's `$vectorize` using the same model, so no
        local embedding call or prefix handling is needed on either side.
        Returns [] on any failure (Astra down, collection not yet created,
        NVIDIA endpoint hiccup) -- callers fall back to lexical-only
        ranking, per Stage 2d's rule."""
        if not self.enabled or not query_text or not query_text.strip():
            return []

        try:
            cursor = self._collection("embeddings").find(
                {"report_id": report_id},
                sort={"$vectorize": query_text},
                limit=limit,
            )
            return [dict(item) for item in cursor]
        except Exception:
            logger.exception(
                "[ASTRA] Vector search failed for report_id=%s", report_id
            )
            return []

    def list_evidence_chunks(
        self,
        report_id: str,
        limit: int = 500,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Plain (non-vector) lexical read of the `embeddings` collection.

        `content_types` defaults to `["web_chunk"]` for backwards
        compatibility with existing callers. "web_chunk"/"trend_item"/
        "competitor_profile" must match
        EmbeddingService.CONTENT_TYPE_WEB_CHUNK/CONTENT_TYPE_TREND_ITEM/
        CONTENT_TYPE_COMPETITOR_PROFILE -- kept as literals here rather than
        importing that module, since embedding_service.py already imports
        this one and this repository intentionally stays the lower layer.

        2026-09-14 remediation Phase 1.1: EvidenceBundleService._load_evidence_items
        (the only feed into generate_bundles_for_report) now passes all three
        content types, so competitor/trend chunks are no longer structurally
        excluded from the lexical half of bundle ranking -- previously they
        could only enter a bundle by winning unfiltered vector search.
        fetch_trend_items/fetch_competitor_insights remain separate read
        paths for callers that want ONLY one type.

        No vector sort -- this is the lexical corpus for EvidenceRanker,
        not semantic search (see find_similar_embeddings for that). This
        is the fix for the fusion join in
        EvidenceBundleService._hybrid_rank_for_section, which used to match
        lexical and semantic hits on a 180-char text-prefix fingerprint
        because the two sides had no shared id -- sourcing both from this
        one collection means they share a real per-chunk `_id`."""
        if not self.enabled:
            return []

        types = content_types if content_types is not None else ["web_chunk"]

        try:
            cursor = self._collection("embeddings").find(
                {"report_id": report_id, "content_type": {"$in": types}},
                limit=limit,
            )
            return [dict(item) for item in cursor]
        except Exception:
            logger.exception(
                "[ASTRA] Failed to list evidence chunks for report_id=%s",
                report_id,
            )
            return []

    def fetch_evidence(
        self,
        report_id: str,
        section_title: str,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """`content_types` passes through to list_evidence_chunks (default
        ["web_chunk"] when None) -- see Phase 1.1 note there."""
        bundle = self.get_evidence_bundle(
            report_id=report_id,
            section_title=section_title,
        )
        if bundle and isinstance(bundle.get("items"), list):
            return list(bundle["items"])

        chunks = self.list_evidence_chunks(report_id, content_types=content_types)
        if chunks:
            return chunks

        # Legacy fallback: reports ingested before evidence chunks moved to
        # the `embeddings` collection still have `evidence.snippets[]` and
        # no matching `embeddings` docs (or embeddings were disabled at
        # ingestion time) -- flatten the old shape so they keep working.
        return self._flatten_evidence_documents(self.list_evidence(report_id))

    def fetch_trend_items(self, report_id: str, section_title: str) -> list[dict[str, Any]]:
        return self._list_collection_by_report("trend_items", report_id)

    def fetch_competitor_insights(self, report_id: str, section_title: str) -> list[dict[str, Any]]:
        return self._list_collection_by_report("competitor_insights", report_id)

    def _database(self):
        if self._db is not None:
            return self._db

        try:
            from astrapy import DataAPIClient

            client = DataAPIClient(self.token)
            if self.keyspace:
                self._db = client.get_database_by_api_endpoint(
                    self.endpoint,
                    keyspace=self.keyspace,
                )
            else:
                self._db = client.get_database_by_api_endpoint(self.endpoint)
            return self._db
        except Exception:
            logger.exception("[ASTRA] Failed to initialize Astra database")
            raise

    def _collection(self, name: str):
        return self._database().get_collection(name)

    def _delete_many(self, collection_name: str, query: dict[str, Any]) -> None:
        try:
            self._collection(collection_name).delete_many(query)
        except Exception:
            logger.info(
                "[ASTRA] delete_many skipped collection=%s query=%s",
                collection_name,
                query,
            )

    def _list_collection_by_report(
        self,
        collection_name: str,
        report_id: str,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        try:
            cursor = self._collection(collection_name).find(
                {"report_id": report_id},
                limit=200,
            )
            return [dict(item) for item in cursor]
        except Exception:
            logger.info(
                "[ASTRA] Optional collection unavailable: %s",
                collection_name,
            )
            return []

    def _flatten_evidence_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for doc in documents:
            snippets = doc.get("snippets") or []
            if not snippets and doc.get("raw_text"):
                snippets = [str(doc["raw_text"])[:1200]]

            for snippet in snippets:
                items.append(
                    {
                        "evidence_id": doc.get("evidence_id") or doc.get("_id"),
                        "source_id": doc.get("source_id"),
                        "url": doc.get("url"),
                        "domain": doc.get("domain"),
                        "title": doc.get("title") or doc.get("domain") or doc.get("url"),
                        "type": doc.get("type", "web"),
                        "quote": str(snippet),
                        "text": str(snippet),
                    }
                )

        return items
