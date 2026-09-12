"""Document upload, listing, retrieval, deletion and retry."""
from __future__ import annotations
import hashlib
import uuid
from typing import Optional
from uuid import UUID
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.workspace import WorkspaceMembership
from app.models.document import Document, DocumentStatus
from app.ingestion.pipeline import validate_and_detect_type
from app.ingestion.storage import storage
from app.config import settings

router = APIRouter(prefix="/api/workspaces", tags=["documents"])


class DocumentOut(BaseModel):
    id: str
    workspace_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: Optional[int]
    error_message: Optional[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_doc(cls, doc: Document) -> "DocumentOut":
        return cls(
            id=str(doc.id),
            workspace_id=str(doc.workspace_id),
            filename=doc.filename,
            content_type=doc.content_type,
            size_bytes=doc.size_bytes,
            status=doc.status.value,
            chunk_count=doc.chunk_count,
            error_message=doc.error_message,
            created_at=doc.created_at.isoformat(),
            updated_at=doc.updated_at.isoformat(),
        )


def _require_member(db: Session, user_id, workspace_id) -> WorkspaceMembership:
    m = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return m


def _get_doc_or_404(db: Session, workspace_id, document_id) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.workspace_id == workspace_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{workspace_id}/documents", response_model=DocumentOut, status_code=202)
async def upload_document(
    workspace_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)

    if not file.filename:
        raise HTTPException(400, "Filename is required")

    # Validate extension
    try:
        content_type = validate_and_detect_type(file.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Read content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file is not allowed")
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit")

    # Compute SHA-256
    content_hash = hashlib.sha256(content).hexdigest()

    # Duplicate check within this workspace
    existing = (
        db.query(Document)
        .filter(
            Document.workspace_id == workspace_id,
            Document.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            f"Identical document already exists: {existing.filename}",
            headers={"X-Existing-Document-Id": str(existing.id)},
        )

    # Persist file
    doc_id = uuid.uuid4()
    storage_key = storage.save(str(workspace_id), str(doc_id), content)

    # Create DB record
    doc = Document(
        id=doc_id,
        workspace_id=workspace_id,
        filename=Path(file.filename).name,  # strip any path components from client name
        content_type=content_type,
        size_bytes=len(content),
        storage_key=storage_key,
        content_hash=content_hash,
        status=DocumentStatus.queued,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Enqueue ingestion. If this fails, the document row already exists — mark it
    # FAILED rather than leaving it silently stuck in QUEUED with no job behind it.
    from app.worker.jobs import enqueue_ingestion
    try:
        enqueue_ingestion(str(doc.id))
    except Exception as exc:
        doc.status = DocumentStatus.failed
        doc.error_message = f"Failed to enqueue ingestion job: {exc}"[:500]
        db.commit()
        db.refresh(doc)

    return DocumentOut.from_doc(doc)


@router.get("/{workspace_id}/documents", response_model=list[DocumentOut])
def list_documents(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)
    docs = (
        db.query(Document)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [DocumentOut.from_doc(d) for d in docs]


@router.get("/{workspace_id}/documents/{document_id}", response_model=DocumentOut)
def get_document(
    workspace_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)
    return DocumentOut.from_doc(_get_doc_or_404(db, workspace_id, document_id))


@router.delete("/{workspace_id}/documents/{document_id}", status_code=204)
def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)
    doc = _get_doc_or_404(db, workspace_id, document_id)

    # Remove Qdrant points first (best-effort)
    try:
        from app.ingestion.qdrant_mgr import delete_document_points
        delete_document_points(str(doc.id))
    except Exception:
        pass  # Don't block deletion if Qdrant is unavailable

    # Remove file
    storage.delete(doc.storage_key)

    db.delete(doc)
    db.commit()


@router.post("/{workspace_id}/documents/{document_id}/retry", response_model=DocumentOut)
def retry_document(
    workspace_id: UUID,
    document_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_member(db, current_user.id, workspace_id)
    doc = _get_doc_or_404(db, workspace_id, document_id)

    if doc.status != DocumentStatus.failed:
        raise HTTPException(400, "Only FAILED documents can be retried")

    doc.status = DocumentStatus.queued
    doc.error_message = None
    db.commit()
    db.refresh(doc)

    from app.worker.jobs import enqueue_ingestion
    enqueue_ingestion(str(doc.id))

    return DocumentOut.from_doc(doc)
