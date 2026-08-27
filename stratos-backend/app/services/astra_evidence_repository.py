from __future__ import annotations

import logging
import os
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


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
        if not self.enabled:
            return None

        chunk_id = document.get("_id")
        try:
            self._collection("embeddings").insert_one(dict(document))
            return chunk_id
        except Exception:
            logger.exception("[ASTRA] Failed to save embedding chunk")
            return None

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

    def fetch_evidence(self, report_id: str, section_title: str) -> list[dict[str, Any]]:
        bundle = self.get_evidence_bundle(
            report_id=report_id,
            section_title=section_title,
        )
        if bundle and isinstance(bundle.get("items"), list):
            return list(bundle["items"])

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
