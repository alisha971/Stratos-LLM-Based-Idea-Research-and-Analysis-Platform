"""Orchestrator state-transition tests (gap-closing plan Stage 1).

Covers the research/trend/competitor join (including its 90s timeout
fallback), the `*_failed` -> FAILED catch-all, and the `Report.topic` fix in
`accept_consent`. Before this file, orchestrator_service.py -- the entire
state machine -- had zero test coverage.

Requires a running local Postgres and Redis (same as test_auth.py / the app
itself) -- clarification_schema is Postgres-only JSONB, so there's no sqlite
swap, and research_join_service is genuinely backed by Redis rather than
mocked, since the join logic *is* the thing under test. Rows and Redis keys
created by these tests are cleaned up in fixture teardown.
"""

from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import models
from app.db.database import SessionLocal
from app.services import research_join_service as join_service
from app.services import section_status_service
from app.services.orchestrator_service import OrchestratorService
from app.utils.redis_pub import redis_client
from app.utils.state_machine import SessionState

_created_user_ids: list[str] = []
_touched_report_ids: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for report_id in _touched_report_ids:
        join_service.clear(report_id)
        section_status_service.clear(report_id)
    _touched_report_ids.clear()

    db = SessionLocal()
    try:
        if _created_user_ids:
            session_ids = [
                row.id
                for row in db.query(models.Session.id).filter(
                    models.Session.user_id.in_(_created_user_ids)
                )
            ]
            if session_ids:
                report_ids = [
                    row.id
                    for row in db.query(models.Report.id).filter(
                        models.Report.session_id.in_(session_ids)
                    )
                ]
                if report_ids:
                    section_ids = [
                        row.id
                        for row in db.query(models.Section.id).filter(
                            models.Section.report_id.in_(report_ids)
                        )
                    ]
                    if section_ids:
                        db.query(models.Chunk).filter(
                            models.Chunk.section_id.in_(section_ids)
                        ).delete(synchronize_session=False)
                    db.query(models.Section).filter(
                        models.Section.report_id.in_(report_ids)
                    ).delete(synchronize_session=False)
                db.query(models.Report).filter(
                    models.Report.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.query(models.ChatMessage).filter(
                    models.ChatMessage.session_id.in_(session_ids)
                ).delete(synchronize_session=False)
                db.query(models.Session).filter(
                    models.Session.id.in_(session_ids)
                ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id.in_(_created_user_ids)
            ).delete(synchronize_session=False)
            db.commit()
        _created_user_ids.clear()
    finally:
        db.close()


def _make_report(db, *, session_status: str, section_count: int = 2):
    """A User + Session + Report + N Sections, wired for the join/failure
    tests below. clarified_summary is set to a minimal non-empty string --
    enough for generate_bundles_for_report's presence check, without needing
    real evidence (it degrades to an empty bundle list, which is fine here)."""
    user = models.User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@example.test")
    db.add(user)
    _created_user_ids.append(user.id)

    session = models.Session(
        id=str(uuid.uuid4()),
        user_id=user.id,
        status=session_status,
        idea_description="A meal-prep app for medical residents.",
        clarified_summary='{"final_schema": {}}',
    )
    db.add(session)

    report = models.Report(
        id=str(uuid.uuid4()),
        session_id=session.id,
        topic="Pending clarification",
        status=session_status,
    )
    db.add(report)
    db.commit()

    for i in range(section_count):
        db.add(
            models.Section(
                id=str(uuid.uuid4()),
                report_id=report.id,
                title=f"Section {i}",
                order_index=i,
            )
        )
    db.commit()

    _touched_report_ids.append(report.id)
    return session, report


class ResearchJoinTests(unittest.TestCase):
    def test_single_leg_does_not_advance(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )

            with patch(
                "app.services.orchestrator_service.run_section_writer"
            ) as mock_writer:
                OrchestratorService.handle_research_done(db, report.id)
                mock_writer.delay.assert_not_called()

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.RESEARCH_RUNNING.value
            assert report.status == SessionState.RESEARCH_RUNNING.value
            assert report.missing_research_legs is None
        finally:
            db.close()

    def test_all_three_legs_advance_to_writing(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value, section_count=3
            )

            with patch(
                "app.services.orchestrator_service.run_section_writer"
            ) as mock_writer:
                OrchestratorService.handle_research_done(db, report.id)
                OrchestratorService.handle_trend_ready(db, report.id)
                OrchestratorService.handle_competitor_ready(db, report.id)
                assert mock_writer.delay.call_count == 3

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.WRITING_SECTIONS.value
            assert report.status == SessionState.WRITING_SECTIONS.value
            assert report.missing_research_legs is None
        finally:
            db.close()

    def test_repeated_leg_arrival_does_not_double_dispatch(self):
        """A duplicate/retried research_done (e.g. a Celery redelivery) must
        not reset the join clock or double-fire once already advanced."""
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )

            with patch(
                "app.services.orchestrator_service.run_section_writer"
            ) as mock_writer:
                OrchestratorService.handle_research_done(db, report.id)
                OrchestratorService.handle_trend_ready(db, report.id)
                OrchestratorService.handle_competitor_ready(db, report.id)
                assert mock_writer.delay.call_count == 2

                # Late duplicate delivery of an already-arrived leg.
                OrchestratorService.handle_research_done(db, report.id)
                assert mock_writer.delay.call_count == 2  # unchanged
        finally:
            db.close()

    def test_timeout_advances_without_missing_legs_and_records_them(self):
        """Simulates the 90s join timeout without a real 90s sleep: the
        `research` leg's Redis timestamp is written directly, far enough in
        the past that join_ready's timeout check trips."""
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )

            redis_client.hset(
                join_service._key(report.id), "research", str(time.time() - 200)
            )

            with patch(
                "app.services.orchestrator_service.run_section_writer"
            ) as mock_writer:
                OrchestratorService.try_advance_to_writing(db, report.id)
                assert mock_writer.delay.call_count == 2

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.WRITING_SECTIONS.value
            assert report.missing_research_legs is not None
            import json

            gaps = json.loads(report.missing_research_legs)
            assert set(gaps) == {"trend", "competitor"}
        finally:
            db.close()

    def test_join_key_cleared_once_advanced(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )
            with patch("app.services.orchestrator_service.run_section_writer"):
                OrchestratorService.handle_research_done(db, report.id)
                OrchestratorService.handle_trend_ready(db, report.id)
                OrchestratorService.handle_competitor_ready(db, report.id)

            assert redis_client.hgetall(join_service._key(report.id)) == {}
        finally:
            db.close()


class StageFailureTests(unittest.TestCase):
    def test_fatal_failure_sets_terminal_state_once(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )

            with patch(
                "app.services.orchestrator_service.publish_event"
            ) as mock_publish:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="research_failed",
                    payload={"report_id": report.id, "error": "boom"},
                )
                assert mock_publish.call_count == 1
                assert mock_publish.call_args[0][0] == "pipeline_failed"

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.FAILED.value
            assert report.status == SessionState.FAILED.value

            # A duplicate delivery of the same failure (e.g. Celery
            # autoretry on assembler/export) must not publish again.
            with patch(
                "app.services.orchestrator_service.publish_event"
            ) as mock_publish:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="research_failed",
                    payload={"report_id": report.id, "error": "boom"},
                )
                mock_publish.assert_not_called()
        finally:
            db.close()

    def test_clarification_failed_resolves_via_session_id(self):
        """clarification_failed carries session_id, not report_id -- confirm
        the session_id-only branch also reaches FAILED."""
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.CLARIFYING.value
            )

            OrchestratorService.handle_stage_failed(
                db,
                event_type="clarification_failed",
                payload={"session_id": session.id, "error": "llm down"},
            )

            db.refresh(session)
            assert session.status == SessionState.FAILED.value
        finally:
            db.close()

    def test_non_fatal_failure_does_not_set_failed_and_unblocks_join(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.RESEARCH_RUNNING.value
            )

            with patch("app.services.orchestrator_service.publish_event") as mock_publish:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="trend_failed",
                    payload={"report_id": report.id, "error": "provider down"},
                )
                # Non-fatal: no pipeline_failed publish.
                assert all(
                    call.args[0] != "pipeline_failed"
                    for call in mock_publish.call_args_list
                )

            db.refresh(session)
            assert session.status == SessionState.RESEARCH_RUNNING.value
            assert "trend" not in join_service.missing_legs(report.id)
        finally:
            db.close()


class SectionFailureTests(unittest.TestCase):
    """Gap-closing plan Stage 1 / partial-report survival. Before this,
    `section_failed` fell into Stage 1a's `*_failed` catch-all with no entry
    in `_STAGE_FATALITY`'s predecessor (`_NON_FATAL_FAILURE_EVENTS`), so a
    single failed section marked the whole report FAILED -- discarding
    every other section that succeeded. Naively adding it to the non-fatal
    set alone would have made the run hang forever instead (`handle_section_
    done`'s old completion count never reached len(sections) once one
    section could never produce chunks); these tests cover both halves of
    the actual fix together."""

    def _mark_done(self, db, section_id: str) -> None:
        db.add(
            models.Chunk(
                id=str(uuid.uuid4()),
                section_id=section_id,
                chunk_text="Some finished section text [CIT-001].",
                chunk_index=1,
            )
        )
        db.commit()

    def test_one_section_failed_others_done_reaches_ready_for_assembly(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_SECTIONS.value, section_count=2
            )
            sections = (
                db.query(models.Section)
                .filter_by(report_id=report.id)
                .order_by(models.Section.order_index)
                .all()
            )
            self._mark_done(db, sections[0].id)

            with patch(
                "app.services.orchestrator_service.publish_event"
            ) as mock_publish:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="section_failed",
                    payload={
                        "report_id": report.id,
                        "section_id": sections[1].id,
                        "error": "both Groq keys exhausted",
                    },
                )
                assert all(
                    call.args[0] != "pipeline_failed"
                    for call in mock_publish.call_args_list
                )
                sections_done_calls = [
                    call for call in mock_publish.call_args_list
                    if call.args[0] == "sections_done"
                ]
                assert len(sections_done_calls) == 1
                assert sections_done_calls[0].args[1]["failed_section_count"] == 1

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.READY_FOR_ASSEMBLY.value
            assert report.status == SessionState.READY_FOR_ASSEMBLY.value
        finally:
            db.close()

    def test_all_sections_failed_sets_terminal_state(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_SECTIONS.value, section_count=2
            )
            sections = (
                db.query(models.Section)
                .filter_by(report_id=report.id)
                .order_by(models.Section.order_index)
                .all()
            )

            with patch(
                "app.services.orchestrator_service.publish_event"
            ) as mock_publish:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="section_failed",
                    payload={
                        "report_id": report.id,
                        "section_id": sections[0].id,
                        "error": "boom",
                    },
                )
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="section_failed",
                    payload={
                        "report_id": report.id,
                        "section_id": sections[1].id,
                        "error": "boom",
                    },
                )
                pipeline_failed_calls = [
                    call for call in mock_publish.call_args_list
                    if call.args[0] == "pipeline_failed"
                ]
                assert len(pipeline_failed_calls) == 1
                assert pipeline_failed_calls[0].args[1]["stage"] == "section"

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.FAILED.value
            assert report.status == SessionState.FAILED.value
        finally:
            db.close()

    def test_duplicate_section_failed_does_not_double_count(self):
        """A retried/redelivered section_failed for the same section_id
        must not unblock the join twice or count it as two failures."""
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_SECTIONS.value, section_count=2
            )
            sections = (
                db.query(models.Section)
                .filter_by(report_id=report.id)
                .order_by(models.Section.order_index)
                .all()
            )
            self._mark_done(db, sections[0].id)

            with patch(
                "app.services.orchestrator_service.publish_event"
            ) as mock_publish:
                for _ in range(3):
                    OrchestratorService.handle_stage_failed(
                        db,
                        event_type="section_failed",
                        payload={
                            "report_id": report.id,
                            "section_id": sections[1].id,
                            "error": "boom",
                        },
                    )
                sections_done_calls = [
                    call for call in mock_publish.call_args_list
                    if call.args[0] == "sections_done"
                ]
                # Advances once, on the first delivery -- session.status is
                # no longer WRITING_SECTIONS afterward, so handle_section_
                # done's own early-return guard absorbs the 2nd/3rd retries.
                assert len(sections_done_calls) == 1
        finally:
            db.close()


class ConsentTopicTests(unittest.TestCase):
    def test_accept_consent_sets_report_topic_from_idea(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.AWAITING_CONSENT.value
            )
            assert report.topic == "Pending clarification"

            with patch("app.services.orchestrator_service.run_outline"):
                OrchestratorService.accept_consent(db, session)

            db.refresh(report)
            assert report.topic == "A meal-prep app for medical residents."
        finally:
            db.close()


class VerdictTransitionTests(unittest.TestCase):
    """Gap-closing plan Stage 4d: sections_done -> verdict -> assembler.
    Only one link changed from the pre-Stage-4 chain (sections_done used to
    dispatch the assembler directly) -- these confirm the new link and that
    a verdict failure is non-fatal, per the same _NON_FATAL_FAILURE_EVENTS
    mechanism ResearchJoinTests/StageFailureTests already cover for
    trend/competitor."""

    def test_sections_done_moves_to_writing_verdict_and_dispatches_verdict(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_SECTIONS.value
            )

            with patch("app.services.orchestrator_service.run_verdict") as mock_verdict:
                OrchestratorService.handle_sections_done(db, report.id)
                assert mock_verdict.delay.call_count == 1
                assert mock_verdict.delay.call_args[0][0] == report.id

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.WRITING_VERDICT.value
            assert report.status == SessionState.WRITING_VERDICT.value
        finally:
            db.close()

    def test_verdict_ready_dispatches_assembler(self):
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_VERDICT.value
            )

            with patch("app.services.orchestrator_service.run_assembler") as mock_assembler:
                OrchestratorService.handle_verdict_ready(db, report.id)
                assert mock_assembler.delay.call_count == 1
                assert mock_assembler.delay.call_args[0][0] == report.id
        finally:
            db.close()

    def test_verdict_failed_is_non_fatal_and_proceeds_to_assembler(self):
        """Sections are already fully written by the time the verdict
        runs -- a verdict failure must not lose the report; it proceeds
        straight to assembly instead of moving to FAILED."""
        db = SessionLocal()
        try:
            session, report = _make_report(
                db, session_status=SessionState.WRITING_VERDICT.value
            )

            with patch("app.services.orchestrator_service.publish_event") as mock_publish, \
                 patch("app.services.orchestrator_service.run_assembler") as mock_assembler:
                OrchestratorService.handle_stage_failed(
                    db,
                    event_type="verdict_failed",
                    payload={"report_id": report.id, "error": "LLM validation exhausted"},
                )
                assert all(
                    call.args[0] != "pipeline_failed"
                    for call in mock_publish.call_args_list
                )
                assert mock_assembler.delay.call_count == 1
                assert mock_assembler.delay.call_args[0][0] == report.id

            db.refresh(session)
            db.refresh(report)
            assert session.status == SessionState.WRITING_VERDICT.value  # untouched, not FAILED
            assert report.status == SessionState.WRITING_VERDICT.value
        finally:
            db.close()
