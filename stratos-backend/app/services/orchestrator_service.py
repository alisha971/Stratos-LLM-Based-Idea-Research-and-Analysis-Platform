# app/services/orchestrator_service.py

import logging

from sqlalchemy.orm import Session
from fastapi import HTTPException
import uuid, json

from app.db import models
from app.utils.state_machine import SessionState
from app.utils.redis_pub import publish_event
from app.workers.clarification_worker import run_clarification
from app.workers.outline_worker import run_outline
from app.workers.research_worker import run_research
from app.workers.trend_worker import run_trend
from app.workers.section_worker import run_section_writer
from app.workers.assembler_worker import run_assembler
from app.workers.export_worker import run_export
from app.services.evidence_bundle_service import EvidenceBundleService
from app.services.research_join_service import (
    clear as clear_research_join,
    join_ready,
    missing_legs,
    record_leg_arrival,
)
from app.workers.competitor_worker import run_competitor

logger = logging.getLogger(__name__)

# *_failed events that don't kill the run: trend/competitor are best-effort
# legs of the research fan-out, and the join (research_join_service) already
# knows how to proceed without one. Every other *_failed event is fatal --
# the pipeline has no other way to make progress, so it moves to FAILED
# instead of leaving the session/report parked with no signal (see
# handle_stage_failed).
_NON_FATAL_FAILURE_EVENTS = {"trend_failed", "competitor_failed"}


class OrchestratorService:
    """
    SINGLE source of truth for session state.
    Orchestrates conversation flow and transitions.
    """

    # --------------------------------------------------
    # Session bootstrap
    # --------------------------------------------------
    @staticmethod
    def start_session(db: Session, user_id: str, idea_description: str):
        session = models.Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status=SessionState.CREATED,
            idea_description=idea_description,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        # Save first user message (context seeding)
        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            message=idea_description,
        ))

        report = models.Report(
            id=str(uuid.uuid4()),
            session_id=session.id,
            topic="Pending clarification",
            status=SessionState.CREATED,
        )
        db.add(report)
        db.commit()

        publish_event("session_created", {
            "session_id": session.id,
            "state": session.status,
        })

        return session, report

    # --------------------------------------------------
    # Start clarification conversation
    # --------------------------------------------------
    @staticmethod
    def start_clarification(db: Session, session: models.Session):
        if session.status != SessionState.CREATED:
            raise HTTPException(400, "Invalid state")

        session.status = SessionState.CLARIFYING
        db.commit()

        publish_event("clarification_started", {
            "session_id": session.id
        })

        run_clarification.delay(session.id)

    # --------------------------------------------------
    # Handle user message during clarification
    # --------------------------------------------------
    @staticmethod
    def handle_user_message(db: Session, session: models.Session, message: str):
        if session.status not in (
            SessionState.CLARIFYING,
            SessionState.AWAITING_CONSENT,
        ):
            raise HTTPException(400, "Clarification not active")

        db.add(models.ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session.id,
            role="user",
            message=message,
        ))
        db.commit()

        # Resume clarification intelligence
        run_clarification.delay(session.id)

    # --------------------------------------------------
    # Transition to consent (no hard logic yet)
    # --------------------------------------------------
    @staticmethod
    def handle_clarification_ready(
        db: Session,
        session_id: str,
        payload: dict,
    ):
        session = db.query(models.Session).filter_by(id=session_id).first()
        if not session or session.status != SessionState.CLARIFYING:
            return

        session.status = SessionState.AWAITING_CONSENT
        session.clarified_summary = json.dumps({
            "final_schema": payload["schema"],
            "hard_constraints": payload.get("hard_constraints", []),
            "hypotheses": payload.get("hypotheses", []),
            "knowledge_gaps": payload.get("knowledge_gaps", []),
            "research_directives": payload.get("research_directives", []),
            "unknown_detected": payload.get("unknown_detected", []),
            "confidence_score": payload["confidence_score"],
        }, indent=2)

        db.commit()

        publish_event(
            "clarification_consent_requested",
            {
                "session_id": session.id,
                "summary": session.clarified_summary,
            }
        )

    # --------------------------------------------------
    # User accepts proposed research plan
    # --------------------------------------------------
    @staticmethod
    def accept_consent(db: Session, session: models.Session):
        if session.status != SessionState.AWAITING_CONSENT:
            raise HTTPException(400, "Consent not requested")

        if not session.clarified_summary:
            raise HTTPException(400, "Missing clarification summary")

        session.status = SessionState.READY_FOR_RESEARCH
        db.commit()
        
        report = (
            db.query(models.Report)
            .filter_by(session_id=session.id)
            .first()
        )

        # Was the literal string "Pending clarification" until now (set at
        # start_session, never updated) -- the section writer prompt reads
        # report.topic (section_writer_service.py) and the PDF title will
        # too (export_worker.py), so this needs to be the real idea before
        # either downstream stage runs.
        if report and session.idea_description:
            report.topic = session.idea_description
            db.commit()

        publish_event(
            "clarification_completed",
            {
                "session_id": session.id,
                "state": session.status,
                "schema": session.clarified_summary,
            }
        )

        # 🔥 Trigger outline
        run_outline.delay(report.id)
        
        
    @staticmethod
    def handle_outline_ready(
        db: Session,
        report_id: str,
        sections: list,
    ):
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        session = (
            db.query(models.Session)
            .filter_by(id=report.session_id)
            .first()
        )
        if not session:
            return

        # 🔒 Idempotency guard
        if session.status != SessionState.READY_FOR_RESEARCH:
            return

        # -----------------------------
        # State transition - Accept Outline
        # -----------------------------
        session.status = SessionState.OUTLINE_GENERATED
        report.status = SessionState.OUTLINE_GENERATED
        db.commit()

        publish_event(
            "outline_accepted",
            {
                "session_id": session.id,
                "report_id": report.id,
                "sections": sections,
            }
        )

        # -----------------------------
        # FAN-OUT (parallel)
        # -----------------------------
        session.status = SessionState.RESEARCH_RUNNING
        report.status = SessionState.RESEARCH_RUNNING
        db.commit()

        publish_event(
            "research_started",
            {
                "session_id": session.id,
                "report_id": report.id,
            }
        )

        run_research.delay(report.id)
        run_trend.delay(report.id)
        run_competitor.delay(report.id)

        # Bounded-timeout fallback for the join below: if trend or
        # competitor never publishes at all (crashed task, dropped message),
        # nothing would otherwise re-check the join, since the orchestrator
        # is purely event-driven. Lazy import to avoid a circular import
        # (join_worker imports OrchestratorService lazily too).
        from app.workers.join_worker import check_research_join
        check_research_join.apply_async(args=[report.id], countdown=90)

    # --------------------------------------------------
    # Research fan-out join: research (required) + trend/competitor
    # (best-effort, bounded by a 90s timeout -- see research_join_service).
    # Each leg's handler just records arrival and re-checks the join; the
    # actual advance-to-writing logic lives once in try_advance_to_writing
    # so the event-driven callers below and the timeout fallback task
    # (join_worker.check_research_join) share one code path.
    # --------------------------------------------------
    @staticmethod
    def handle_research_done(
        db: Session,
        report_id: str,
    ):
        record_leg_arrival(report_id, "research")
        OrchestratorService.try_advance_to_writing(db, report_id)

    @staticmethod
    def handle_trend_ready(
        db: Session,
        report_id: str,
    ):
        record_leg_arrival(report_id, "trend")
        OrchestratorService.try_advance_to_writing(db, report_id)

    @staticmethod
    def handle_competitor_ready(
        db: Session,
        report_id: str,
    ):
        record_leg_arrival(report_id, "competitor")
        OrchestratorService.try_advance_to_writing(db, report_id)

    @staticmethod
    def try_advance_to_writing(
        db: Session,
        report_id: str,
    ):
        """Gate for the fan-out join. Safe to call redundantly -- from any
        of the three leg handlers above, or from the timeout fallback task
        -- since every early-return here is idempotent: the session-status
        check alone prevents double-dispatching section writers once this
        has already fired once for a report."""
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        session = (
            db.query(models.Session)
            .filter_by(id=report.session_id)
            .first()
        )
        if not session:
            return

        if session.status not in (
            SessionState.RESEARCH_RUNNING,
            SessionState.OUTLINE_GENERATED,
        ):
            return

        if not join_ready(report_id):
            return

        gaps = missing_legs(report_id)
        if gaps:
            logger.warning(
                "[ORCHESTRATOR] Proceeding to section writing for "
                "report_id=%s without leg(s)=%s (research_join timeout)",
                report_id,
                gaps,
            )
            report.missing_research_legs = json.dumps(gaps)

        clear_research_join(report_id)

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            publish_event(
                "section_writing_failed",
                {
                    "session_id": session.id,
                    "report_id": report.id,
                    "error": "No sections found",
                },
            )
            return

        bundle_service = EvidenceBundleService(db=db)
        bundles = bundle_service.generate_bundles_for_report(report_id)

        session.status = SessionState.WRITING_SECTIONS
        report.status = SessionState.WRITING_SECTIONS
        db.commit()

        publish_event(
            "section_writing_started",
            {
                "session_id": session.id,
                "report_id": report.id,
                "section_count": len(sections),
                "evidence_bundle_count": len(bundles),
            },
        )

        for section in sections:
            run_section_writer.delay(report.id, section.id)

    @staticmethod
    def handle_section_done(
        db: Session,
        report_id: str,
    ):
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        session = (
            db.query(models.Session)
            .filter_by(id=report.session_id)
            .first()
        )
        if not session or session.status != SessionState.WRITING_SECTIONS:
            return

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            return

        completed_section_ids = {
            chunk.section_id
            for chunk in (
                db.query(models.Chunk)
                .join(models.Section)
                .filter(models.Section.report_id == report_id)
                .all()
            )
        }
        if len(completed_section_ids) < len(sections):
            return

        session.status = SessionState.READY_FOR_ASSEMBLY
        report.status = SessionState.READY_FOR_ASSEMBLY
        db.commit()

        publish_event(
            "sections_done",
            {
                "session_id": session.id,
                "report_id": report.id,
                "section_count": len(sections),
            },
        )

    @staticmethod
    def handle_sections_done(
        db: Session,
        report_id: str,
    ):
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        run_assembler.delay(report_id)

    @staticmethod
    def handle_report_assembled(
        db: Session,
        report_id: str,
    ):
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            return

        session = (
            db.query(models.Session)
            .filter_by(id=report.session_id)
            .first()
        )
        if session:
            session.status = SessionState.READY_FOR_EXPORT
        report.status = SessionState.READY_FOR_EXPORT
        db.commit()

        run_export.delay(report_id)

    # --------------------------------------------------
    # Catch-all for every `*_failed` event (redis_sub.py routes any event
    # type ending in "_failed" here). Before this, a failed stage simply
    # never published a state change, so the session/report sat wherever
    # they were forever -- indistinguishable from "still running" to
    # anyone watching (contract §4, "About ten minutes").
    # --------------------------------------------------
    @staticmethod
    def handle_stage_failed(
        db: Session,
        event_type: str,
        payload: dict,
    ):
        report_id = payload.get("report_id")
        session_id = payload.get("session_id")
        error = payload.get("error")

        if event_type in _NON_FATAL_FAILURE_EVENTS:
            # trend/competitor are best-effort legs of the research
            # fan-out -- research_join_service already knows how to proceed
            # without one via its timeout. A definitive failure should
            # unblock the join immediately rather than waiting it out.
            logger.warning(
                "[ORCHESTRATOR] Non-fatal stage failure event=%s "
                "report_id=%s error=%s",
                event_type,
                report_id,
                error,
            )
            if report_id:
                leg = "trend" if event_type == "trend_failed" else "competitor"
                record_leg_arrival(report_id, leg)
                OrchestratorService.try_advance_to_writing(db, report_id)
            return

        logger.error(
            "[ORCHESTRATOR] Fatal stage failure event=%s report_id=%s "
            "session_id=%s error=%s",
            event_type,
            report_id,
            session_id,
            error,
        )

        report = None
        session = None
        if report_id:
            report = db.query(models.Report).filter_by(id=report_id).first()
            if report:
                session = (
                    db.query(models.Session)
                    .filter_by(id=report.session_id)
                    .first()
                )
        elif session_id:
            session = db.query(models.Session).filter_by(id=session_id).first()

        # Idempotency guard: assembler/export workers auto-retry on
        # exception (up to 3x), so the same *_failed event can arrive more
        # than once for one underlying failure. Only the first should move
        # state and publish.
        already_failed = (
            report is not None and report.status == SessionState.FAILED.value
        ) or (
            session is not None and session.status == SessionState.FAILED.value
        )
        if already_failed:
            return

        if report:
            report.status = SessionState.FAILED.value
        if session:
            session.status = SessionState.FAILED.value
        if report or session:
            db.commit()

        publish_event(
            "pipeline_failed",
            {
                "session_id": session.id if session else session_id,
                "report_id": report.id if report else report_id,
                "stage": event_type,
                "error": error,
            },
        )

    # --------------------------------------------------
    # Read models (report retrieval — contract §3.5/§3.6)
    # --------------------------------------------------
    @staticmethod
    def list_reports(db: Session, user_id: str) -> list:
        rows = (
            db.query(models.Report, models.Session)
            .join(models.Session, models.Report.session_id == models.Session.id)
            .filter(models.Session.user_id == user_id)
            .order_by(models.Report.created_at.desc())
            .all()
        )
        return [
            {
                "report_id": report.id,
                "session_id": session.id,
                "idea_description": session.idea_description,
                "status": report.status,
                "created_at": (
                    report.created_at.isoformat() if report.created_at else None
                ),
            }
            for report, session in rows
        ]

    @staticmethod
    def get_report_view(db: Session, report_id: str) -> dict:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise HTTPException(404, "Report not found")

        session = (
            db.query(models.Session).filter_by(id=report.session_id).first()
        )
        idea = session.idea_description if session else report.topic

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )

        sections_view = []
        for section in sections:
            chunks = (
                db.query(models.Chunk)
                .filter_by(section_id=section.id)
                .order_by(models.Chunk.chunk_index.asc())
                .all()
            )
            chunks_view = []
            for chunk in chunks:
                citations = []
                for citation in chunk.citations:
                    source = citation.source
                    citations.append(
                        {
                            "marker": citation.citation_marker,
                            "url": source.url if source else None,
                            "domain": source.domain if source else None,
                            "title": source.domain if source else None,
                        }
                    )
                chunks_view.append(
                    {
                        "chunk_id": chunk.id,
                        "order_index": chunk.chunk_index,
                        "text": chunk.chunk_text,
                        "citations": citations,
                    }
                )
            sections_view.append(
                {
                    "section_id": section.id,
                    "title": section.title,
                    "order_index": section.order_index,
                    "chunks": chunks_view,
                }
            )

        return {
            "report_id": report.id,
            "status": report.status,
            "title": f"Market Research: {idea}" if idea else "Market Research Report",
            "sections": sections_view,
        }