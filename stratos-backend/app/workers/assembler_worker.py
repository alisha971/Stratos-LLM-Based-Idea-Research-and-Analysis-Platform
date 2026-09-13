from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings
from app.db import models
from app.db.session import SessionLocal
from app.services.competitor_service import (
    COMPETITOR_COVERAGE_NOTE,
    COMPETITOR_SECTION_TITLE,
)
from app.utils.redis_pub import publish_event
from app.utils.state_machine import SessionState
from app.utils.verdict_view import verdict_view
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Gap-closing plan Stage 1 / partial-report survival: a section that failed
# to write has no chunks by the time the assembler runs. Deterministic,
# LLM-free, same convention as COMPETITOR_COVERAGE_NOTE -- rendered by any
# export format without re-deriving it.
SECTION_UNAVAILABLE_NOTE = (
    "This section could not be completed during research and writing; "
    "the rest of the report reflects what was successfully gathered."
)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_assembler(self, report_id: str):
    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        sections = (
            db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            raise ValueError("No sections found")

        assembled_sections = []
        chunk_count = 0
        for section in sections:
            chunks = (
                db.query(models.Chunk)
                .filter_by(section_id=section.id)
                .order_by(models.Chunk.chunk_index.asc())
                .all()
            )
            if not chunks:
                # Section writer failed for this one (gap-closing plan
                # Stage 1) -- the orchestrator only reaches the assembler
                # once at least one section succeeded (see
                # OrchestratorService.handle_section_done's degenerate-case
                # guard), so skipping here can never produce an
                # all-empty report.
                logger.warning(
                    "[ASSEMBLER] Section has no chunks (writer failed) "
                    "section_id=%s report_id=%s",
                    section.id,
                    report_id,
                )
                assembled_sections.append(
                    {
                        "section_id": section.id,
                        "title": section.title,
                        "order_index": section.order_index,
                        "chunks": [],
                        "coverage_note": SECTION_UNAVAILABLE_NOTE,
                    }
                )
                continue

            assembled_chunks = []
            for chunk in chunks:
                citations = [
                    {
                        "marker": citation.citation_marker,
                        "source_id": citation.source_id,
                        "quote": citation.quote,
                    }
                    for citation in chunk.citations
                ]
                assembled_chunks.append(
                    {
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.chunk_text,
                        "citations": citations,
                    }
                )
                chunk_count += 1

            section_dict = {
                "section_id": section.id,
                "title": section.title,
                "order_index": section.order_index,
                "chunks": assembled_chunks,
            }

            # Deterministic, LLM-free coverage caveat — the section writer is
            # barred from discussing the research process, so this can't
            # come from the model. Carried here so any export format can
            # render it without re-deriving it. Never names the discovery
            # platforms (product launch surfaces), only that coverage isn't
            # exhaustive.
            if section.title == COMPETITOR_SECTION_TITLE:
                competitor_count = (
                    db.query(models.Competitor)
                    .filter_by(report_id=report_id)
                    .count()
                )
                if competitor_count > 0:
                    section_dict["coverage_note"] = COMPETITOR_COVERAGE_NOTE

            assembled_sections.append(section_dict)

        # Carried into the draft so the export layer can render an "Open
        # Questions" block deterministically, even if the writing model
        # under-delivered on them.
        unresolved_gaps = _unresolved_gaps(db, report)

        draft = {
            "report_id": report_id,
            # The user's actual idea, not the literal string
            # "Stratos Research Report" the PDF used to print (Stage 5a).
            "topic": report.topic,
            # None when verdict_failed happened (Stage 4d, non-fatal) --
            # the export must render a normal report without one rather
            # than failing.
            "verdict": verdict_view(report),
            "sections": assembled_sections,
            # marker -> {url, domain, title, stance}, resolved once here
            # rather than by the export layer -- the verdict only ever
            # cites markers already present in some section's citations
            # (see VerdictService.build_verdict_context), so this single
            # pass over the report's citations covers both.
            "sources": _resolve_sources(db, report_id),
            "unresolved_gaps": unresolved_gaps,
        }
        draft_path = _draft_path(report_id)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")

        report.status = SessionState.READY_FOR_EXPORT.value
        db.commit()

        publish_event(
            "report_assembled",
            {
                "report_id": report_id,
                "section_count": len(assembled_sections),
                "chunk_count": chunk_count,
                "draft_path": str(draft_path),
                "unresolved_count": len(unresolved_gaps),
            },
        )

    except Exception as exc:
        publish_event(
            "assembler_failed",
            {
                "report_id": report_id,
                "error": str(exc),
            },
        )
        raise
    finally:
        db.close()


def _resolve_sources(db, report_id: str) -> dict[str, dict]:
    """marker -> {url, domain, title, stance} for every citation across
    every section of this report. This is what lets the export layer turn
    inline [CIT-001] markers into real links and build a bibliography,
    instead of the old "Citations: CIT-001" plain-text line with no URL."""
    citations = (
        db.query(models.Citation)
        .join(models.Chunk, models.Citation.chunk_id == models.Chunk.id)
        .join(models.Section, models.Chunk.section_id == models.Section.id)
        .filter(models.Section.report_id == report_id)
        .all()
    )

    sources: dict[str, dict] = {}
    for citation in citations:
        marker = citation.citation_marker
        if not marker or marker in sources:
            continue
        source = citation.source
        url = source.url if source else None
        domain = source.domain if source else None
        # Real title (SERP result title / competitor product name, Stage
        # 5b) when one was captured; domain otherwise -- was hardcoded to
        # domain unconditionally before.
        title = (source.title if source else None) or domain or url
        sources[marker] = {
            "url": url,
            "domain": domain,
            "title": title,
            "stance": (source.stance if source else None) or "neutral",
        }

    return sources


def _unresolved_gaps(db, report) -> list[str]:
    """What research could not establish. Never fatal — a gap in the gap list
    must not fail an otherwise complete report."""
    try:
        session = db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            return []

        from app.services.evidence_bundle_service import EvidenceBundleService

        return EvidenceBundleService(db).unresolved_directives(
            report.id,
            session.clarified_summary,
        )
    except Exception:
        logger.exception(
            "[ASSEMBLER] Could not compute unresolved gaps for report_id=%s",
            report.id,
        )
        return []


def _draft_path(report_id: str) -> Path:
    return Path(settings.EXPORT_DIR) / f"{report_id}.json"
