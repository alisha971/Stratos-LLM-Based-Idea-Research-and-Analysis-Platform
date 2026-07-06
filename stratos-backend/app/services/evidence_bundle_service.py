from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.services.astra_evidence_repository import AstraEvidenceRepository
from app.services.evidence_ranker import EvidenceRanker

logger = logging.getLogger(__name__)


class EvidenceBundleService:
    def __init__(
        self,
        db: Session,
        astra_repository: AstraEvidenceRepository | None = None,
        ranker: EvidenceRanker | None = None,
    ) -> None:
        self.db = db
        self.astra_repository = astra_repository or AstraEvidenceRepository()
        self.ranker = ranker or EvidenceRanker()

    def generate_bundles_for_report(self, report_id: str) -> list[dict[str, Any]]:
        report = self.db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")

        session = self.db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        sections = (
            self.db.query(models.Section)
            .filter_by(report_id=report_id)
            .order_by(models.Section.order_index.asc())
            .all()
        )
        if not sections:
            raise ValueError("No sections found")

        evidence_items = self._load_evidence_items(report_id)
        if not evidence_items:
            logger.warning("[BUNDLE] No evidence found for report_id=%s", report_id)
            return []

        bundles = []
        for section in sections:
            ranked_items = self.ranker.rank_for_section(
                clarified_summary=session.clarified_summary,
                section_title=section.title,
                evidence_items=evidence_items,
                limit=12,
            )
            if not ranked_items:
                logger.warning(
                    "[BUNDLE] No ranked evidence for report_id=%s section_id=%s",
                    report_id,
                    section.id,
                )
                continue

            bundle = {
                "bundle_id": str(uuid.uuid4()),
                "report_id": report_id,
                "section_id": section.id,
                "section_title": section.title,
                "items": ranked_items,
                "created_at": datetime.utcnow().isoformat(),
            }
            self.astra_repository.save_evidence_bundle(bundle)
            bundles.append(bundle)

        return bundles

    def _load_evidence_items(self, report_id: str) -> list[dict[str, Any]]:
        astra_items = self.astra_repository.fetch_evidence(report_id, section_title="")
        if astra_items:
            return astra_items

        return self._load_postgres_evidence_items(report_id)

    def _load_postgres_evidence_items(self, report_id: str) -> list[dict[str, Any]]:
        sources = (
            self.db.query(models.Source)
            .filter_by(report_id=report_id)
            .order_by(models.Source.created_at.asc())
            .all()
        )

        items: list[dict[str, Any]] = []
        for source in sources:
            for evidence in source.evidence:
                items.append(
                    {
                        "evidence_id": None,
                        "source_id": source.id,
                        "url": source.url,
                        "domain": source.domain,
                        "title": source.domain or source.url,
                        "type": source.type,
                        "quote": evidence.snippet,
                        "text": evidence.snippet,
                    }
                )

        return items
