"""RQ job definitions and queue helper."""
from __future__ import annotations
import logging
from app.config import settings

log = logging.getLogger(__name__)


def enqueue_ingestion(document_id: str) -> None:
    """Enqueue a document for background ingestion."""
    from redis import Redis
    from rq import Queue
    redis_conn = Redis.from_url(settings.REDIS_URL)
    q = Queue("ingestion", connection=redis_conn)
    q.enqueue(
        run_ingestion_pipeline,
        document_id,
        job_timeout=3600,  # generous for cold-start model downloads
        job_id=f"ingest-{document_id}",  # rq job IDs: letters/numbers/underscores/dashes only
        on_failure=_on_job_failure,
    )


def _on_job_failure(job, connection, type, value, traceback):
    """RQ failure callback — mark document as FAILED if not already."""
    document_id = job.args[0] if job.args else None
    if document_id:
        _mark_failed(document_id, f"{type.__name__}: {value}")


def run_ingestion_pipeline(document_id: str) -> None:
    """
    Called by RQ worker. Full ingestion pipeline:
    QUEUED/FAILED → PROCESSING → READY (or FAILED on error).
    """
    from sqlalchemy.orm import Session
    from app.database import SessionLocal
    from app.models.document import Document, DocumentStatus
    from app.ingestion.storage import storage
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr

    db: Session = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            log.warning("Document %s not found — skipping ingestion", document_id)
            return
        if doc.status not in (DocumentStatus.queued, DocumentStatus.failed):
            log.info("Document %s already in status %s — skipping", document_id, doc.status)
            return

        doc.status = DocumentStatus.processing
        db.commit()
        log.info("Processing document %s (%s)", document_id, doc.filename)

        try:
            with storage.materialize(doc.storage_key) as file_path:
                chunks = parse_and_chunk(file_path, doc.content_type)

            # Delete any existing points before (re-)indexing — safe for retry
            qdrant_mgr.delete_document_points(str(doc.id))
            qdrant_mgr.index_document(
                workspace_id=str(doc.workspace_id),
                document_id=str(doc.id),
                source_filename=doc.filename,
                chunks=chunks,
            )

            doc.status = DocumentStatus.ready
            doc.chunk_count = len(chunks)
            doc.error_message = None
            db.commit()
            log.info("Document %s READY (%d chunks)", document_id, len(chunks))

        except Exception as exc:
            log.exception("Ingestion failed for document %s", document_id)
            doc.status = DocumentStatus.failed
            doc.error_message = str(exc)[:500]
            db.commit()
            raise  # re-raise so RQ records failure

    finally:
        db.close()


def _mark_failed(document_id: str, error: str) -> None:
    from app.database import SessionLocal
    from app.models.document import Document, DocumentStatus
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc and doc.status == DocumentStatus.processing:
            doc.status = DocumentStatus.failed
            doc.error_message = error[:500]
            db.commit()
    finally:
        db.close()
