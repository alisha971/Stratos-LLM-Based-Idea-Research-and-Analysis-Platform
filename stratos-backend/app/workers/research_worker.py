from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.db.session import SessionLocal
from app.db import models
from app.services.research_service import ResearchService
from app.utils.redis_pub import publish_event


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def run_research(self, report_id: str):
    """
    Research Worker
    - Fetches external evidence
    - Stores raw evidence in Astra
    - Stores metadata in Postgres
    """
    
    db = SessionLocal()

    try:
        report = db.query(models.Report).filter_by(id=report_id).first()
        if not report:
            raise ValueError("Report not found")
        
        session = db.query(models.Session).filter_by(id=report.session_id).first()
        if not session or not session.clarified_summary:
            raise ValueError("Clarified summary missing")

        publish_event("searching_sources", {"report_id": report_id})

        service = ResearchService(db=db)

        queries = service.generate_queries(session.clarified_summary)

        for query in queries:
            results = service.search(query)

            for result in results:
                source = service.create_source(report_id, result)

                snippets, full_text = service.scrape_and_extract(result["url"])

                if not snippets:
                    continue

                service.save_evidence(source.id, snippets)

                service.save_to_astra(
                    report_id=report_id,
                    source_id=source.id,
                    url=result["url"],
                    text=full_text,
                    metadata=result,
                )

        publish_event("research_done", {"report_id": report_id})

    except Exception as e:
        publish_event("research_failed", {
            "report_id": report_id,
            "error": str(e)
        })
        raise
    finally:
        db.close()
