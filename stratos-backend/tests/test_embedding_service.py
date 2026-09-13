"""EmbeddingService tests (gap-closing plan Stage 2b/2c). Uses a fake
AstraEvidenceRepository -- no network, no live Astra dependency -- so this
runs in CI without NVIDIA/vectorize API calls. The live round-trip
(insert -> $vectorize -> semantic search) was verified once by hand against
the real Astra database when the `embeddings` collection was created; see
stratos-launch-plan Stage 2b."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.embedding_service import (
    CONTENT_TYPE_COMPETITOR_PROFILE,
    CONTENT_TYPE_TREND_ITEM,
    CONTENT_TYPE_WEB_CHUNK,
    EmbeddingService,
)


class FakeAstraRepository:
    """Records every call, never touches the network. Mirrors the
    fail-soft contract of the real AstraEvidenceRepository: save returns
    None when `enabled` is False, find returns []."""

    def __init__(self, enabled: bool = True, fail_saves: bool = False):
        self.enabled = enabled
        self.fail_saves = fail_saves
        self.saved_documents: list[dict] = []
        self.search_calls: list[dict] = []
        self.search_results: list[dict] = []

    def save_embedding_chunk(self, document: dict):
        if not self.enabled or self.fail_saves:
            return None
        self.saved_documents.append(document)
        return document["_id"]

    def find_similar_embeddings(self, report_id, query_text, limit=25):
        self.search_calls.append(
            {"report_id": report_id, "query_text": query_text, "limit": limit}
        )
        if not self.enabled:
            return []
        return self.search_results


class SaveChunkTests(unittest.TestCase):
    def test_save_chunk_sets_vectorize_field_to_the_text(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        chunk_id = service.save_chunk(
            report_id="r1",
            content_type=CONTENT_TYPE_WEB_CHUNK,
            text="Three funded incumbents already own tier-one distribution.",
            source_id="src1",
            url="https://example.com/a",
            domain="example.com",
        )

        self.assertIsNotNone(chunk_id)
        self.assertEqual(len(repo.saved_documents), 1)
        doc = repo.saved_documents[0]
        self.assertEqual(doc["$vectorize"], doc["text"])
        self.assertEqual(doc["content_type"], CONTENT_TYPE_WEB_CHUNK)
        self.assertEqual(doc["report_id"], "r1")
        self.assertEqual(doc["source_id"], "src1")

    def test_empty_text_is_not_saved(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        self.assertIsNone(
            service.save_chunk(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="")
        )
        self.assertIsNone(
            service.save_chunk(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="   ")
        )
        self.assertEqual(repo.saved_documents, [])

    def test_disabled_repository_saves_nothing_no_exception(self):
        repo = FakeAstraRepository(enabled=False)
        service = EmbeddingService(astra_repository=repo)

        result = service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="some text"
        )
        self.assertIsNone(result)

    def test_stance_field_carried_through_for_stage_3(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(
            report_id="r1",
            content_type=CONTENT_TYPE_WEB_CHUNK,
            text="Incumbents already own tier-one distribution.",
            stance="challenges",
        )
        self.assertEqual(repo.saved_documents[0]["stance"], "challenges")


class SaveChunksBatchTests(unittest.TestCase):
    def test_batch_shape_indexes_in_order(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        saved_count = service.save_chunks(
            report_id="r1",
            content_type=CONTENT_TYPE_WEB_CHUNK,
            chunks=["first chunk text", "second chunk text", "third chunk text"],
            source_id="src1",
        )

        self.assertEqual(saved_count, 3)
        self.assertEqual([d["chunk_index"] for d in repo.saved_documents], [0, 1, 2])
        self.assertEqual(
            [d["text"] for d in repo.saved_documents],
            ["first chunk text", "second chunk text", "third chunk text"],
        )

    def test_partial_failure_is_not_fatal(self):
        repo = FakeAstraRepository(fail_saves=True)
        service = EmbeddingService(astra_repository=repo)

        saved_count = service.save_chunks(
            report_id="r1",
            content_type=CONTENT_TYPE_TREND_ITEM,
            chunks=["a", "b"],
        )
        self.assertEqual(saved_count, 0)  # degrades silently, doesn't raise

    def test_empty_chunk_list_saves_nothing(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        self.assertEqual(
            service.save_chunks(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, chunks=[]),
            0,
        )

    def test_stance_prior_forwarded_to_every_chunk(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunks(
            report_id="r1",
            content_type=CONTENT_TYPE_WEB_CHUNK,
            chunks=["a", "b"],
            stance="challenges",
        )
        self.assertTrue(all(d["stance"] == "challenges" for d in repo.saved_documents))


class FindSimilarTests(unittest.TestCase):
    def test_delegates_scoped_to_report(self):
        repo = FakeAstraRepository()
        repo.search_results = [{"text": "match one"}, {"text": "match two"}]
        service = EmbeddingService(astra_repository=repo)

        results = service.find_similar(
            report_id="r1", query_text="evidence about pricing", limit=10
        )

        self.assertEqual(results, repo.search_results)
        self.assertEqual(len(repo.search_calls), 1)
        self.assertEqual(repo.search_calls[0]["report_id"], "r1")
        self.assertEqual(repo.search_calls[0]["query_text"], "evidence about pricing")
        self.assertEqual(repo.search_calls[0]["limit"], 10)

    def test_disabled_returns_empty_list_not_none(self):
        repo = FakeAstraRepository(enabled=False)
        service = EmbeddingService(astra_repository=repo)

        results = service.find_similar(report_id="r1", query_text="anything")
        self.assertEqual(results, [])


class ContentTypeSeparationTests(unittest.TestCase):
    """Evidence chunks carry a content_type discriminator; there is no
    separate 'chunk' collection for report-output text at this stage (see
    Stage 2c) -- these constants are the full registry today."""

    def test_content_type_constants_are_distinct(self):
        values = {
            CONTENT_TYPE_WEB_CHUNK,
            CONTENT_TYPE_TREND_ITEM,
            CONTENT_TYPE_COMPETITOR_PROFILE,
        }
        self.assertEqual(len(values), 3)

    def test_saved_document_never_omits_content_type(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)
        service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_COMPETITOR_PROFILE, text="a profile"
        )
        self.assertIn("content_type", repo.saved_documents[0])
        self.assertEqual(
            repo.saved_documents[0]["content_type"], CONTENT_TYPE_COMPETITOR_PROFILE
        )


if __name__ == "__main__":
    unittest.main()
