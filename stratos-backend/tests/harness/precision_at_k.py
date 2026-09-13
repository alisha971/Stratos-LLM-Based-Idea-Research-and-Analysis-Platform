# tests/harness/precision_at_k.py
"""
Precision@k measurement (gap-closing plan Stage 6) -- NOT a pytest test, a
standalone script run by hand, same pattern as scripts/run_pipeline_smoke.py.
Hits live Astra (both nvidia models are keyless, so no API key setup is
needed anywhere in this script). Groq is never called -- this measures
ranking only, not generation.

Answers the two questions Stage 2 deliberately deferred to this harness
rather than settling from a leaderboard:
  1. lexical-only vs hybrid -- does adding the embedding side actually
     change (and improve) which evidence gets selected on this corpus?
  2. nvidia/NV-Embed-QA (the pinned default) vs nvidia/nv-embedqa-e5-v5
     (the keyless comparison point) -- does the specific model choice
     matter here, or was the zero-setup argument alone unfalsifiable?

Usage:
    PYTHONPATH=. python tests/harness/precision_at_k.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fixture_loader import (
    clarified_summary_json,
    evidence_items_for_ranker,
    list_fixture_names,
    load_fixture,
    relevance_ground_truth,
    stance_by_source,
)

from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.embedding_service import CONTENT_TYPE_WEB_CHUNK, EmbeddingService
from app.services.evidence_bundle_service import EvidenceBundleService

# Deliberately smaller than every fixture's candidate pool size (checked
# empirically: 4-8 items per section, and _hybrid_rank_for_section returns
# the whole pool unless BUNDLE_SIZE=12 or a lexical score <=0 excludes
# something -- neither triggers at this fixture scale). If k >= pool size,
# "top k" IS the whole pool regardless of ranking order, and Precision@k
# degenerates to "background relevant rate in the ground truth" -- a
# property of the fixture alone, identical across every ranking method by
# construction. k=3 keeps this a real measurement of ranking quality
# instead of an unconditionally-passing metric.
REPORT_ID_PREFIX = "harness-precision-at-k"
K = 3

# Second collection for the model-vs-model comparison -- Astra vectorize is
# configured per COLLECTION, not per request, so comparing two models needs
# two collections. Created/torn down by this script; not used anywhere in
# the app itself.
E5_COLLECTION = "embeddings_harness_e5_v5_comparison"
E5_PROVIDER = "nvidia"
E5_MODEL = "nvidia/nv-embedqa-e5-v5"


class LexicalOnlyEmbeddingService:
    """find_similar always returns [] -- degrades hybrid ranking to pure
    lexical order, per Stage 2d's rule. Used as the "lexical-only" arm of
    the comparison without needing a second EvidenceRanker code path."""

    def find_similar(self, *, report_id: str, query_text: str, limit: int = 25):
        return []


class RawCollectionEmbeddingService:
    """Same find_similar() contract as EmbeddingService, but against an
    arbitrary Astra collection name instead of the app's fixed "embeddings"
    -- lets this script compare a second model without threading a
    configurable collection name through production code for a one-off
    comparison tool."""

    def __init__(self, database, collection_name: str):
        self._collection = database.get_collection(collection_name)

    def find_similar(self, *, report_id: str, query_text: str, limit: int = 25):
        if not query_text or not query_text.strip():
            return []
        try:
            cursor = self._collection.find(
                {"report_id": report_id}, sort={"$vectorize": query_text}, limit=limit
            )
            return [dict(item) for item in cursor]
        except Exception:
            return []


def precision_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return float("nan")
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for item_id in top_k if item_id in relevant_ids)
    return hits / len(top_k)


def _seed_evidence_items(report_id: str, fixture: dict[str, Any], save_chunk) -> None:
    for item in fixture["evidence_items"]:
        save_chunk(
            report_id=report_id,
            content_type=CONTENT_TYPE_WEB_CHUNK,
            text=item["quote"],
            source_id=item["source_id"],
            evidence_id=item["evidence_id"],
            url=item.get("url"),
            domain=item.get("domain"),
            stance=item.get("stance"),
        )


def run_configuration(
    embedding_service,
    report_id_for: dict[str, str],
    k: int = K,
) -> dict[str, float]:
    """{fixture_name:section_title -> precision@k} for one embedding
    configuration (or LexicalOnlyEmbeddingService as the lexical-only
    stand-in). `report_id_for` maps fixture name -> the report_id its
    evidence was actually seeded under for this run, so repeated runs
    never collide on stale data from a previous one."""
    results: dict[str, float] = {}
    for fixture_name in list_fixture_names():
        fixture = load_fixture(fixture_name)
        service = EvidenceBundleService(db=None, embedding_service=embedding_service)
        for section_title in fixture["sections"]:
            relevant_ids = relevance_ground_truth(fixture, section_title)
            if not relevant_ids:
                continue
            ranked = service._hybrid_rank_for_section(
                report_id=report_id_for[fixture_name],
                clarified_summary=clarified_summary_json(fixture),
                section_title=section_title,
                evidence_items=evidence_items_for_ranker(fixture),
                stance_by_source=stance_by_source(fixture),
            )
            ranked_ids = [item["evidence_id"] for item in ranked]
            results[f"{fixture_name}:{section_title}"] = precision_at_k(ranked_ids, relevant_ids, k)
    return results


def _print_results(label: str, results: dict[str, float]) -> None:
    print(f"\n--- {label} (P@{K}) ---")
    for key, value in results.items():
        shown = "n/a" if value != value else f"{value:.2f}"
        print(f"  {key:60s} {shown}")
    values = [v for v in results.values() if v == v]
    if values:
        print(f"  {'MEAN':60s} {sum(values) / len(values):.2f}")


def _print_comparison(name_a: str, results_a: dict[str, float], name_b: str, results_b: dict[str, float]) -> None:
    print(f"\n--- {name_a}  ->  {name_b} ---")
    for key in results_a:
        a, b = results_a[key], results_b.get(key, float("nan"))
        if a != a or b != b:
            continue
        arrow = "better" if b > a else ("worse" if b < a else "same")
        print(f"  {key:60s} {a:.2f} -> {b:.2f}  ({arrow})")


def _ensure_e5_collection(database) -> None:
    from astrapy.info import CollectionDefinition

    existing = set(database.list_collection_names())
    if E5_COLLECTION in existing:
        return
    definition = CollectionDefinition.builder().with_vector_service(E5_PROVIDER, E5_MODEL).build()
    database.create_collection(E5_COLLECTION, definition=definition)


def main() -> None:
    astra_repository = AstraEvidenceRepository()
    if not astra_repository.enabled:
        print("Astra is not configured (ASTRA_DB_ENDPOINT/TOKEN unset).")
        print("Running lexical-only in isolation -- no hybrid or model comparison possible.")
        report_id_for = {name: f"{REPORT_ID_PREFIX}-{name}" for name in list_fixture_names()}
        _print_results("lexical-only", run_configuration(LexicalOnlyEmbeddingService(), report_id_for))
        return

    default_embedding_service = EmbeddingService(astra_repository)
    database = astra_repository._database()

    report_ids = [f"{REPORT_ID_PREFIX}-{name}-{uuid.uuid4().hex[:8]}" for name in list_fixture_names()]
    fixture_to_report_id = dict(zip(list_fixture_names(), report_ids))

    print("Seeding fixture evidence into `embeddings` (nvidia/NV-Embed-QA, the pinned default)...")
    for fixture_name, report_id in fixture_to_report_id.items():
        _seed_evidence_items(report_id, load_fixture(fixture_name), default_embedding_service.save_chunk)

    print(f"Ensuring comparison collection `{E5_COLLECTION}` ({E5_MODEL})...")
    _ensure_e5_collection(database)
    e5_embedding_service = RawCollectionEmbeddingService(database, E5_COLLECTION)

    def _seed_e5(report_id: str, evidence_id: str, text: str, **fields) -> None:
        doc = {"_id": str(uuid.uuid4()), "report_id": report_id, "evidence_id": evidence_id, "text": text, "$vectorize": text, **fields}
        database.get_collection(E5_COLLECTION).insert_one(doc)

    print("Seeding the same fixture evidence into the comparison collection...")
    for fixture_name, report_id in fixture_to_report_id.items():
        for item in load_fixture(fixture_name)["evidence_items"]:
            _seed_e5(report_id, item["evidence_id"], item["quote"], source_id=item["source_id"])

    try:
        lexical_results = run_configuration(LexicalOnlyEmbeddingService(), fixture_to_report_id)
        hybrid_default_results = run_configuration(default_embedding_service, fixture_to_report_id)
        hybrid_e5_results = run_configuration(e5_embedding_service, fixture_to_report_id)

        _print_results("lexical-only", lexical_results)
        _print_results("hybrid (nvidia/NV-Embed-QA, pinned default)", hybrid_default_results)
        _print_results("hybrid (nvidia/nv-embedqa-e5-v5, comparison)", hybrid_e5_results)

        _print_comparison("lexical-only", lexical_results, "hybrid (NV-Embed-QA)", hybrid_default_results)
        _print_comparison("NV-Embed-QA (default)", hybrid_default_results, "nv-embedqa-e5-v5 (comparison)", hybrid_e5_results)

    finally:
        print("\nCleaning up seeded fixture data...")
        for report_id in fixture_to_report_id.values():
            astra_repository._delete_many("embeddings", {"report_id": report_id})
            database.get_collection(E5_COLLECTION).delete_many({"report_id": report_id})


if __name__ == "__main__":
    main()
