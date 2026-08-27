"""
One-shot, idempotent Astra setup for Stage 2 (chunking/embeddings/hybrid
ranking) of the gap-closing plan.

Creates the `embeddings` collection with server-side `$vectorize` enabled
(provider `nvidia`, model `NV-Embed-QA`, 1024 dimensions -- see
app/services/embedding_service.py for why this specific provider/model was
chosen). Checks `list_collection_names()` first rather than relying on
`create_collection` being a no-op on an existing collection, so this is
safe to run repeatedly.

The dimension is NOT passed explicitly: with a vectorize-configured
collection, Astra infers it from the chosen model (confirmed 1024 for
`nvidia`/`NV-Embed-QA` via a live `find_embedding_providers()` query
against this project's own database -- see the gap-closing plan, Stage 2b).

Run once per environment, same as scripts/add_pipeline_tracking_columns.py
and scripts/add_competitor_columns.py are run once per Postgres database:

    PYTHONPATH=. python scripts/ensure_astra_collections.py
"""

from astrapy import DataAPIClient
from astrapy.info import CollectionDefinition

from app.config import settings
from app.services.embedding_service import EMBEDDING_MODEL, EMBEDDING_PROVIDER, EMBEDDINGS_COLLECTION


def main() -> None:
    if not settings.ASTRA_DB_ENDPOINT or not settings.ASTRA_DB_APPLICATION_TOKEN:
        print("ASTRA_DB_ENDPOINT / ASTRA_DB_APPLICATION_TOKEN not set -- nothing to do.")
        return

    client = DataAPIClient(settings.ASTRA_DB_APPLICATION_TOKEN)
    if settings.ASTRA_DB_KEYSPACE:
        db = client.get_database_by_api_endpoint(
            settings.ASTRA_DB_ENDPOINT, keyspace=settings.ASTRA_DB_KEYSPACE,
        )
    else:
        db = client.get_database_by_api_endpoint(settings.ASTRA_DB_ENDPOINT)

    existing_descriptors = {c.name: c for c in db.list_collections()}
    if EMBEDDINGS_COLLECTION in existing_descriptors:
        current = existing_descriptors[EMBEDDINGS_COLLECTION].definition
        service = current.vector.service if current.vector else None
        if (
            service
            and service.provider == EMBEDDING_PROVIDER
            and service.model_name == EMBEDDING_MODEL
        ):
            print(
                f"Collection '{EMBEDDINGS_COLLECTION}' already configured for "
                f"{EMBEDDING_PROVIDER}/{EMBEDDING_MODEL} -- skipping."
            )
            return

        # Predates this decision -- the pre-Stage-2 collection was created
        # 384-dim/cosine with no vectorize service (expects raw $vector
        # arrays), a leftover from before this codebase used vector search
        # at all. Safe to drop only because it's verifiably unused.
        count = db.get_collection(EMBEDDINGS_COLLECTION).estimated_document_count()
        if count > 0:
            raise RuntimeError(
                f"Collection '{EMBEDDINGS_COLLECTION}' exists with a different "
                f"config (service={service}) AND contains ~{count} documents -- "
                "refusing to drop it automatically. Recreating at a new "
                "dimension is a migration (backfill + re-embed), not a "
                "one-shot script; see stratos-launch-plan Stage 2b."
            )
        print(
            f"Collection '{EMBEDDINGS_COLLECTION}' exists but is empty and "
            f"misconfigured for this decision (service={service}) -- "
            "dropping and recreating."
        )
        db.drop_collection(EMBEDDINGS_COLLECTION)

    definition = (
        CollectionDefinition.builder()
        .with_vector_service(EMBEDDING_PROVIDER, EMBEDDING_MODEL)
        .build()
    )
    print(
        f"Creating collection '{EMBEDDINGS_COLLECTION}' "
        f"(provider={EMBEDDING_PROVIDER}, model={EMBEDDING_MODEL})..."
    )
    db.create_collection(EMBEDDINGS_COLLECTION, definition=definition)
    print(f"Collection '{EMBEDDINGS_COLLECTION}' created successfully!")


if __name__ == "__main__":
    main()
