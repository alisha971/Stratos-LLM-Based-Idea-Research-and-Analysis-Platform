"""VerdictService tests (gap-closing plan Stage 4). Validation tests mirror
test_section_writer_service.py's style (db=None, hand-built context).
build_verdict_context tests use the real local Postgres (it genuinely
queries Section/Chunk/Citation/Source, and Session.clarification_schema is
Postgres JSONB -- same reason test_orchestrator_transitions.py doesn't use
an in-memory sqlite swap) with a fake Astra repository so
unresolved_directives doesn't touch the network."""

from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.db import models
from app.db.database import SessionLocal
from app.services.verdict_service import VerdictService


def _context(**overrides):
    base = {
        "marker_map": {
            "CIT-001": {"source_id": "s1", "stance": "supports", "url": "https://a.example.com"},
            "CIT-002": {"source_id": "s2", "stance": "challenges", "url": "https://b.example.com"},
        },
    }
    base.update(overrides)
    return base


def _valid_draft(**overrides):
    draft = {
        "verdict": "reshape",
        "holding": "Go, but only in the underserved segment.",
        "case_for_prose": "Demand is real and validated [CIT-001].",
        "case_against_prose": "Incumbents already own distribution [CIT-002].",
        "which_won": "The distribution gap outweighs the validated demand [CIT-002].",
        "flip_condition": "If a top-three incumbent adds this exact feature within a year.",
        "confidence": "medium",
    }
    draft.update(overrides)
    return draft


class ValidateVerdictDraftTests(unittest.TestCase):
    def setUp(self):
        self.service = VerdictService(db=None)
        self.context = _context()

    def test_accepts_well_formed_grounded_draft(self):
        self.service.validate_verdict_draft(_valid_draft(), self.context)

    def test_rejects_invalid_verdict_value(self):
        draft = _valid_draft(verdict="definitely_build_it")
        with self.assertRaisesRegex(ValueError, "verdict"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_rejects_invalid_confidence_value(self):
        draft = _valid_draft(confidence="extremely_high")
        with self.assertRaisesRegex(ValueError, "confidence"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_rejects_missing_prose_field(self):
        draft = _valid_draft()
        del draft["which_won"]
        with self.assertRaisesRegex(ValueError, "which_won"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_rejects_empty_prose_field(self):
        draft = _valid_draft(flip_condition="   ")
        with self.assertRaisesRegex(ValueError, "flip_condition"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_rejects_unknown_citation_marker(self):
        draft = _valid_draft(case_for_prose="Demand is real and validated [CIT-999].")
        with self.assertRaisesRegex(ValueError, "not present"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_rejects_zero_citations_as_ungrounded_filler(self):
        draft = _valid_draft(
            case_for_prose="Demand is real and validated.",
            case_against_prose="Incumbents already own distribution.",
            which_won="The distribution gap outweighs the validated demand.",
        )
        with self.assertRaisesRegex(ValueError, "no evidence markers"):
            self.service.validate_verdict_draft(draft, self.context)

    def test_thin_evidence_honest_abstain_is_accepted_not_rejected(self):
        """The validator must not penalize an honest low-confidence verdict
        that says outright there was no real case against -- that's the
        'No confident filler' guardrail working as intended, not a defect
        to reject. Still needs at least one citation somewhere to pass the
        ungrounded-filler check."""
        draft = _valid_draft(
            case_against_prose=(
                "The research did not surface a credible case against this "
                "idea beyond general market uncertainty [CIT-001]."
            ),
            which_won=(
                "Absent real opposing evidence, the case for wins by default, "
                "but that default is weak, not a strong endorsement [CIT-001]."
            ),
            confidence="low",
        )
        self.service.validate_verdict_draft(draft, self.context)  # must not raise


class FakeAstraRepository:
    """No live Astra dependency for unresolved_directives -- report has no
    evidence stored there in these tests."""

    def fetch_evidence(self, report_id, section_title=""):
        return []


@pytest.mark.usefixtures("_verdict_context_fixture")
class BuildVerdictContextTests(unittest.TestCase):
    """Requires a running local Postgres (same as test_auth.py /
    test_orchestrator_transitions.py) -- clarification_schema is Postgres
    JSONB, and Session (unlike Source/SourceEvidence in
    test_research_service.py) has that column, so there's no sqlite swap.
    Rows created here are removed in the fixture's teardown."""

    def test_builds_marker_map_from_persisted_citations(self):
        context = self.service.build_verdict_context(self.report_id)
        self.assertIn("CIT-001", context["marker_map"])
        self.assertEqual(context["marker_map"]["CIT-001"]["source_id"], self.source_id)
        self.assertEqual(context["marker_map"]["CIT-001"]["stance"], "supports")

    def test_includes_section_text(self):
        context = self.service.build_verdict_context(self.report_id)
        self.assertEqual(len(context["sections"]), 1)
        self.assertIn("Residents lack time", context["sections"][0]["text"])

    def test_report_not_found_raises(self):
        with self.assertRaises(ValueError):
            self.service.build_verdict_context("does-not-exist")

    def test_section_with_no_chunks_is_skipped_not_fatal(self):
        """Gap-closing plan Stage 1 / partial-report survival: a section
        that failed to write (no chunks) must not block the verdict from
        the sections that DID succeed -- this used to raise here."""
        empty_section = models.Section(
            id=str(uuid.uuid4()),
            report_id=self.report_id,
            title="Risks & Open Questions",
            order_index=1,
        )
        self.db.add(empty_section)
        self.db.commit()

        context = self.service.build_verdict_context(self.report_id)

        self.assertEqual(len(context["sections"]), 1)
        self.assertEqual(
            context["sections"][0]["title"], "Problem Context & Validation"
        )

    def test_all_sections_without_chunks_raises(self):
        """Genuinely fatal, unlike the partial case above: if NO section
        has chunks there is nothing to synthesize a verdict from."""
        chunks = (
            self.db.query(models.Chunk)
            .join(models.Section)
            .filter(models.Section.report_id == self.report_id)
            .all()
        )
        for chunk in chunks:
            self.db.query(models.Citation).filter_by(chunk_id=chunk.id).delete()
            self.db.delete(chunk)
        self.db.commit()

        with self.assertRaisesRegex(ValueError, "No section has chunks"):
            self.service.build_verdict_context(self.report_id)


@pytest.fixture
def _verdict_context_fixture(request):
    db = SessionLocal()
    session_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())
    section_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    db.add(models.Session(id=session_id, clarified_summary='{"final_schema": {}}'))
    db.add(models.Report(id=report_id, session_id=session_id, topic="A meal-prep app"))
    db.add(
        models.Section(
            id=section_id,
            report_id=report_id,
            title="Problem Context & Validation",
            order_index=0,
        )
    )
    db.add(models.Source(id=source_id, report_id=report_id, url="https://a.example.com", stance="supports"))
    db.add(
        models.Chunk(
            id=chunk_id,
            section_id=section_id,
            chunk_text="Residents lack time [CIT-001].",
            chunk_index=1,
        )
    )
    db.add(
        models.Citation(
            id=str(uuid.uuid4()),
            chunk_id=chunk_id,
            source_id=source_id,
            citation_marker="CIT-001",
            quote="Residents report severe time scarcity.",
        )
    )
    db.commit()

    request.instance.db = db
    request.instance.service = VerdictService(db=db, astra_repository=FakeAstraRepository())
    request.instance.report_id = report_id
    request.instance.source_id = source_id

    yield

    db.query(models.Citation).filter(models.Citation.chunk_id == chunk_id).delete(synchronize_session=False)
    db.query(models.Chunk).filter(models.Chunk.section_id.in_([section_id])).delete(synchronize_session=False)
    db.query(models.Section).filter(models.Section.report_id == report_id).delete(synchronize_session=False)
    db.query(models.Source).filter(models.Source.id == source_id).delete(synchronize_session=False)
    db.query(models.Report).filter(models.Report.id == report_id).delete(synchronize_session=False)
    db.query(models.Session).filter(models.Session.id == session_id).delete(synchronize_session=False)
    db.commit()
    db.close()


if __name__ == "__main__":
    unittest.main()
