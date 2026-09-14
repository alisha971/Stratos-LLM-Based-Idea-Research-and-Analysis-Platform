"""AstraEvidenceRepository.save_embedding_chunk -- fix-audit Part 4 added
EmbeddingTooLargeError, raised specifically when the insert is rejected for
exceeding the embedding provider's token limit, so EmbeddingService can
shrink and retry once instead of silently dropping the chunk like every
other failure mode here."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.astra_evidence_repository import (
    AstraEvidenceRepository,
    EmbeddingTooLargeError,
)


def _enabled_repo() -> AstraEvidenceRepository:
    repo = AstraEvidenceRepository.__new__(AstraEvidenceRepository)
    repo.endpoint = "https://example.astra.datastax.com"
    repo.token = "AstraCS:fake"
    repo.keyspace = None
    repo._db = None
    return repo


class SaveEmbeddingChunkTests(unittest.TestCase):
    def test_disabled_returns_none_without_touching_collection(self):
        repo = AstraEvidenceRepository.__new__(AstraEvidenceRepository)
        repo.endpoint = None
        repo.token = None
        repo.keyspace = None
        repo._db = None

        self.assertIsNone(repo.save_embedding_chunk({"_id": "c1"}))

    def test_success_returns_chunk_id(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        with patch.object(repo, "_collection", return_value=fake_collection):
            result = repo.save_embedding_chunk({"_id": "c1", "text": "hello"})

        self.assertEqual(result, "c1")
        fake_collection.insert_one.assert_called_once()

    def test_token_limit_error_raises_embedding_too_large_error(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.insert_one.side_effect = RuntimeError(
            "Input length 513 exceeds maximum allowed token size 512"
        )
        with patch.object(repo, "_collection", return_value=fake_collection):
            with self.assertRaises(EmbeddingTooLargeError):
                repo.save_embedding_chunk({"_id": "c1", "text": "x" * 5000})

    def test_unrelated_error_is_swallowed_and_returns_none(self):
        # Every OTHER failure mode keeps the existing fail-soft contract --
        # only the token-limit case is promoted to a distinguishable
        # exception.
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.insert_one.side_effect = RuntimeError("connection reset")
        with patch.object(repo, "_collection", return_value=fake_collection):
            result = repo.save_embedding_chunk({"_id": "c1", "text": "hello"})

        self.assertIsNone(result)

    def test_maximum_context_length_marker_also_raises(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.insert_one.side_effect = RuntimeError(
            "This model's maximum context length is 512 tokens"
        )
        with patch.object(repo, "_collection", return_value=fake_collection):
            with self.assertRaises(EmbeddingTooLargeError):
                repo.save_embedding_chunk({"_id": "c1", "text": "x" * 5000})


class ListEvidenceChunksContentTypesTests(unittest.TestCase):
    """2026-09-14 remediation Phase 1.1: list_evidence_chunks must default
    to ["web_chunk"] for backwards compatibility, but accept a broader
    content_types list so competitor_profile/trend_item chunks are no
    longer structurally excluded from the lexical bundle corpus."""

    def test_default_filters_to_web_chunk_only(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.find.return_value = []
        with patch.object(repo, "_collection", return_value=fake_collection):
            repo.list_evidence_chunks("report-1")

        args, kwargs = fake_collection.find.call_args
        query = args[0]
        self.assertEqual(query["content_type"], {"$in": ["web_chunk"]})

    def test_explicit_content_types_passed_through_as_in_query(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.find.return_value = []
        with patch.object(repo, "_collection", return_value=fake_collection):
            repo.list_evidence_chunks(
                "report-1",
                content_types=["web_chunk", "competitor_profile", "trend_item"],
            )

        args, kwargs = fake_collection.find.call_args
        query = args[0]
        self.assertEqual(
            query["content_type"],
            {"$in": ["web_chunk", "competitor_profile", "trend_item"]},
        )

    def test_fetch_evidence_passes_content_types_through_to_list_evidence_chunks(self):
        repo = _enabled_repo()
        with patch.object(repo, "get_evidence_bundle", return_value=None), \
             patch.object(repo, "list_evidence_chunks", return_value=[{"_id": "c1"}]) as mock_list:
            result = repo.fetch_evidence(
                "report-1",
                section_title="",
                content_types=["web_chunk", "competitor_profile", "trend_item"],
            )

        mock_list.assert_called_once_with(
            "report-1",
            content_types=["web_chunk", "competitor_profile", "trend_item"],
        )
        self.assertEqual(result, [{"_id": "c1"}])


class SaveEmbeddingChunksBatchTests(unittest.TestCase):
    """2026-09-14 remediation Phase 4.3."""

    def test_disabled_returns_empty_without_touching_collection(self):
        repo = AstraEvidenceRepository.__new__(AstraEvidenceRepository)
        repo.endpoint = None
        repo.token = None
        repo.keyspace = None
        repo._db = None

        succeeded, error = repo.save_embedding_chunks_batch([{"_id": "c1"}])

        self.assertEqual(succeeded, set())
        self.assertIsNone(error)

    def test_empty_documents_returns_empty_without_touching_collection(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        with patch.object(repo, "_collection", return_value=fake_collection):
            succeeded, error = repo.save_embedding_chunks_batch([])

        self.assertEqual(succeeded, set())
        self.assertIsNone(error)
        fake_collection.insert_many.assert_not_called()

    def test_full_success_returns_all_ids_no_error(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_result = MagicMock()
        fake_result.inserted_ids = ["c1", "c2", "c3"]
        fake_collection.insert_many.return_value = fake_result

        with patch.object(repo, "_collection", return_value=fake_collection):
            succeeded, error = repo.save_embedding_chunks_batch(
                [{"_id": "c1"}, {"_id": "c2"}, {"_id": "c3"}]
            )

        self.assertEqual(succeeded, {"c1", "c2", "c3"})
        self.assertIsNone(error)
        fake_collection.insert_many.assert_called_once_with(
            [{"_id": "c1"}, {"_id": "c2"}, {"_id": "c3"}], ordered=False
        )

    def test_partial_failure_returns_only_succeeded_ids_and_the_exception(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        partial_exc = RuntimeError("2 of 3 failed")
        partial_exc.inserted_ids = ["c1", "c3"]  # c2 failed
        fake_collection.insert_many.side_effect = partial_exc

        with patch.object(repo, "_collection", return_value=fake_collection):
            succeeded, error = repo.save_embedding_chunks_batch(
                [{"_id": "c1"}, {"_id": "c2"}, {"_id": "c3"}]
            )

        self.assertEqual(succeeded, {"c1", "c3"})
        self.assertIs(error, partial_exc)

    def test_connection_level_failure_with_no_inserted_ids_attribute(self):
        repo = _enabled_repo()
        fake_collection = MagicMock()
        fake_collection.insert_many.side_effect = ConnectionError("Astra down")

        with patch.object(repo, "_collection", return_value=fake_collection):
            succeeded, error = repo.save_embedding_chunks_batch([{"_id": "c1"}])

        self.assertEqual(succeeded, set())
        self.assertIsInstance(error, ConnectionError)


if __name__ == "__main__":
    unittest.main()
