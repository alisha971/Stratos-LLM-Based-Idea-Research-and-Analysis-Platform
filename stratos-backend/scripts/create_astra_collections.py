"""Provision the Astra DB collections the app expects.

AstraEvidenceRepository (app/services/astra_evidence_repository.py) calls
get_collection(name) and assumes the collection already exists -- it never
creates one. Run this once against a fresh Astra DB before starting the
research/section-writer pipeline.

Usage:
    python scripts/create_astra_collections.py
"""

from __future__ import annotations

import sys

from astrapy import DataAPIClient

from app.config import settings

# Plain document collections -- no vector search is used by the fast-ship
# pipeline yet, so these are created without a `dimension`.
COLLECTIONS = ["evidence", "trend_items", "evidence_bundles", "competitor_insights"]


def main() -> None:
    if not settings.ASTRA_DB_ENDPOINT or not settings.ASTRA_DB_APPLICATION_TOKEN:
        print("FAIL: ASTRA_DB_API_ENDPOINT / ASTRA_DB_APPLICATION_TOKEN not set in .env")
        sys.exit(1)

    client = DataAPIClient(settings.ASTRA_DB_APPLICATION_TOKEN)
    kwargs = {"keyspace": settings.ASTRA_DB_KEYSPACE} if settings.ASTRA_DB_KEYSPACE else {}
    db = client.get_database_by_api_endpoint(settings.ASTRA_DB_ENDPOINT, **kwargs)

    existing = set(db.list_collection_names())
    print(f"Existing collections: {sorted(existing) or '(none)'}")

    for name in COLLECTIONS:
        if name in existing:
            print(f"  - {name}: already exists, skipping")
            continue
        db.create_collection(name)
        print(f"  - {name}: created")

    print("Astra collections ready.")


if __name__ == "__main__":
    main()
