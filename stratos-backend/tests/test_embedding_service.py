"""EmbeddingService tests (gap-closing plan Stage 2b/2c). Uses a fake
AstraEvidenceRepository -- no network, no live Astra dependency -- so this
runs in CI without NVIDIA/vectorize API calls. The live round-trip
(insert -> $vectorize -> semantic search) was verified once by hand against
the real Astra database when the `embeddings` collection was created; see
stratos-launch-plan Stage 2b."""

from pathlib import Path
import sys
import unittest
from unittest.mock import ANY, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.astra_evidence_repository import EmbeddingTooLargeError
from app.services.embedding_service import (
    CONTENT_TYPE_COMPETITOR_PROFILE,
    CONTENT_TYPE_TREND_ITEM,
    CONTENT_TYPE_WEB_CHUNK,
    EMBEDDING_MAX_CHARS,
    EmbeddingService,
)


class FakeAstraRepository:
    """Records every call, never touches the network. Mirrors the
    fail-soft contract of the real AstraEvidenceRepository: save returns
    None when `enabled` is False, find returns [].

    `fail_mode`: "none" (default success), "generic" (returns None, like a
    swallowed network/auth error), or "too_large" (raises
    EmbeddingTooLargeError -- optionally only on the Nth call via
    `too_large_calls`, to simulate the halve-and-retry succeeding on the
    second attempt)."""

    def __init__(self, enabled: bool = True, fail_mode: str = "none", too_large_calls: int = 10**9):
        self.enabled = enabled
        self.fail_mode = fail_mode
        self.too_large_calls = too_large_calls
        self.saved_documents: list[dict] = []
        self.search_calls: list[dict] = []
        self.search_results: list[dict] = []
        self.call_count = 0

    def save_embedding_chunk(self, document: dict):
        self.call_count += 1
        if not self.enabled:
            return None
        if self.fail_mode == "generic":
            return None
        if self.fail_mode == "too_large" and self.call_count <= self.too_large_calls:
            raise EmbeddingTooLargeError("Input length 999 exceeds maximum allowed token size 512")
        self.saved_documents.append(document)
        return document["_id"]

    def save_embedding_chunks_batch(self, documents: list[dict]):
        """2026-09-14 remediation Phase 4.3. Mirrors the real
        AstraEvidenceRepository.save_embedding_chunks_batch contract:
        (successfully_inserted_ids, error_or_none). Any fail_mode other
        than "none" (or `enabled=False`) simulates the WHOLE batch call
        failing outright -- (set(), None) -- so save_chunks' fallback to
        the per-document save_embedding_chunk path (where the existing
        "generic"/"too_large" simulations already live, and are already
        covered by SaveChunkTests) is what actually gets exercised,
        exactly as it would be against the real API on a batch-level
        failure."""
        self.call_count += 1
        if not self.enabled or self.fail_mode != "none":
            return set(), None
        self.saved_documents.extend(documents)
        return {d["_id"] for d in documents}, None

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


class TruncationAndDegradationTests(unittest.TestCase):
    """Fix-audit Part 4: save_chunk is the single choke point every
    $vectorize write goes through (directly or via save_chunks), so its
    truncation guard and degradation recording cover all four call sites
    (web chunks, news snippets, trend items, competitor profiles) at once."""

    def test_oversized_text_is_truncated_before_reaching_vectorize(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(
            report_id="r1",
            content_type=CONTENT_TYPE_TREND_ITEM,
            text="word " * 400,  # 2000 chars, well over EMBEDDING_MAX_CHARS
        )

        saved_text = repo.saved_documents[0]["text"]
        self.assertLessEqual(len(saved_text), EMBEDDING_MAX_CHARS)
        self.assertEqual(repo.saved_documents[0]["$vectorize"], saved_text)

    def test_short_text_is_untouched(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="a short chunk"
        )
        self.assertEqual(repo.saved_documents[0]["text"], "a short chunk")

    def test_truncation_prefers_a_word_boundary(self):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="word " * 400
        )
        saved_text = repo.saved_documents[0]["text"]
        self.assertFalse(saved_text.endswith("wor"))  # not a mid-word cut

    def test_too_large_error_halves_and_retries_once_and_succeeds(self):
        # First attempt raises EmbeddingTooLargeError, second (halved)
        # attempt succeeds -- the chunk is saved, not dropped.
        repo = FakeAstraRepository(fail_mode="too_large", too_large_calls=1)
        service = EmbeddingService(astra_repository=repo)

        chunk_id = service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="word " * 100
        )

        self.assertIsNotNone(chunk_id)
        self.assertEqual(repo.call_count, 2)
        self.assertEqual(len(repo.saved_documents), 1)

    @patch("app.services.embedding_service.record_degradation")
    def test_too_large_error_persisting_after_halving_drops_and_records(self, mock_degraded):
        # Both attempts raise EmbeddingTooLargeError -- exactly one retry,
        # then give up (fail-soft, not fatal) and record the degradation.
        repo = FakeAstraRepository(fail_mode="too_large")  # always raises
        service = EmbeddingService(astra_repository=repo)

        chunk_id = service.save_chunk(
            report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="word " * 100
        )

        self.assertIsNone(chunk_id)
        self.assertEqual(repo.call_count, 2)  # exactly one retry, not a loop
        self.assertEqual(repo.saved_documents, [])
        mock_degraded.assert_called_once()
        args, _ = mock_degraded.call_args
        self.assertEqual(args[0], "r1")
        self.assertEqual(args[1], "embedding_chunk_save")

    @patch("app.services.embedding_service.record_degradation")
    def test_generic_failure_records_degradation(self, mock_degraded):
        repo = FakeAstraRepository(fail_mode="generic")
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="x")

        mock_degraded.assert_called_once_with("r1", "embedding_chunk_save", ANY)

    @patch("app.services.embedding_service.record_degradation")
    def test_disabled_repository_does_not_record_degradation(self, mock_degraded):
        # Disabled (no Astra credentials configured) is a config fact, not
        # a degradation -- must not spam the tally in an environment that
        # simply doesn't have Astra set up.
        repo = FakeAstraRepository(enabled=False)
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="x")

        mock_degraded.assert_not_called()

    @patch("app.services.embedding_service.record_degradation")
    def test_successful_save_does_not_record_degradation(self, mock_degraded):
        repo = FakeAstraRepository()
        service = EmbeddingService(astra_repository=repo)

        service.save_chunk(report_id="r1", content_type=CONTENT_TYPE_WEB_CHUNK, text="x")

        mock_degraded.assert_not_called()


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

    @patch("app.services.embedding_service.record_degradation")
    def test_partial_failure_is_not_fatal(self, mock_degraded):
        repo = FakeAstraRepository(fail_mode="generic")
        service = EmbeddingService(astra_repository=repo)

        saved_count = service.save_chunks(
            report_id="r1",
            content_type=CONTENT_TYPE_TREND_ITEM,
            chunks=["a", "b"],
        )
        self.assertEqual(saved_count, 0)  # degrades silently, doesn't raise
        # Fix-audit Part 0/4: but it's still counted, once per chunk.
        self.assertEqual(mock_degraded.call_count, 2)

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

    def test_partial_batch_failure_only_retries_the_failed_subset(self):
        """2026-09-14 remediation Phase 4.3: when the batch call succeeds
        for SOME documents and fails for others, only the failed ones
        should go through the per-document fallback -- a succeeded
        document must not be saved twice."""
        repo = FakeAstraRepository()
        # Simulate a genuine partial success: the batch call itself
        # reports 2 of 3 ids succeeded, with no error object (mirrors a
        # real CollectionInsertManyException's inserted_ids).
        original_batch = repo.save_embedding_chunks_batch

        def partial_batch(documents):
            repo.call_count += 1
            succeeded_docs = documents[:2]
            repo.saved_documents.extend(succeeded_docs)
            return {d["_id"] for d in succeeded_docs}, None

        repo.save_embedding_chunks_batch = partial_batch
        service = EmbeddingService(astra_repository=repo)

        saved_count = service.save_chunks(
            report_id="r1",
            content_type=CONTENT_TYPE_WEB_CHUNK,
            chunks=["first", "second", "third"],
        )

        # 2 saved by the batch call + 1 recovered via the per-document
        # fallback for the one that didn't confirm success.
        self.assertEqual(saved_count, 3)
        texts_saved = [d["text"] for d in repo.saved_documents]
        self.assertEqual(texts_saved.count("first"), 1)
        self.assertEqual(texts_saved.count("second"), 1)
        self.assertEqual(texts_saved.count("third"), 1)


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
