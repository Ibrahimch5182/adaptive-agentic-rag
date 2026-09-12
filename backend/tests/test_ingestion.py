"""
Integration tests: actual Docling pipeline + Qdrant + full ingestion.
Requires: Qdrant at QDRANT_URL, Docling model downloads on first run.

Run with:  pytest tests/test_ingestion.py -v -m integration
Skip with: pytest tests/ -v -m "not integration"
"""
import os
import time
import pytest
from pathlib import Path

pytestmark = pytest.mark.integration

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

# ── Helpers ─────────────────────────────────────────────────────────────

def _qdrant_available() -> bool:
    try:
        from qdrant_client import QdrantClient
        QdrantClient(url=QDRANT_URL).get_collections()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_qdrant():
    if not _qdrant_available():
        pytest.skip(f"Qdrant not reachable at {QDRANT_URL}")


@pytest.fixture(scope="module")
def qdrant_clean():
    """Ensure the test collection exists and is clean before/after module."""
    from app.ingestion import qdrant_mgr
    qdrant_mgr.ensure_collection()
    yield
    # Cleanup is per-document via delete_document_points


# ── Pipeline unit tests ─────────────────────────────────────────────────

def test_pdf_parses_to_chunks(sample_pdf_bytes, tmp_path):
    from app.ingestion.pipeline import parse_and_chunk
    p = tmp_path / "test.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    assert len(chunks) >= 1
    assert all(c.raw_text.strip() for c in chunks)
    assert all(isinstance(c.chunk_index, int) for c in chunks)


def test_docx_parses_to_chunks(sample_docx_bytes, tmp_path):
    from app.ingestion.pipeline import parse_and_chunk
    p = tmp_path / "test.docx"
    p.write_bytes(sample_docx_bytes)
    chunks = parse_and_chunk(
        p, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert len(chunks) >= 1
    assert any(c.section_title for c in chunks)


def test_markdown_parses_to_chunks(sample_md_bytes, tmp_path):
    from app.ingestion.pipeline import parse_and_chunk
    p = tmp_path / "test.md"
    p.write_bytes(sample_md_bytes)
    chunks = parse_and_chunk(p, "text/markdown")
    assert len(chunks) >= 1
    assert any("Section" in c.section_title for c in chunks)


def test_chunk_provenance_fields(sample_pdf_bytes, tmp_path):
    from app.ingestion.pipeline import parse_and_chunk
    p = tmp_path / "test.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    for c in chunks:
        assert hasattr(c, "raw_text")
        assert hasattr(c, "retrieval_text")
        assert hasattr(c, "section_title")
        assert hasattr(c, "page_numbers")
        assert hasattr(c, "chunk_index")


def test_retrieval_text_differs_from_raw(sample_docx_bytes, tmp_path):
    """Retrieval text should include section context beyond raw text for at least some chunks."""
    from app.ingestion.pipeline import parse_and_chunk
    p = tmp_path / "test.docx"
    p.write_bytes(sample_docx_bytes)
    chunks = parse_and_chunk(
        p, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    # At least one chunk should have retrieval_text != raw_text (heading context added)
    has_contextual = any(c.retrieval_text.strip() != c.raw_text.strip() for c in chunks)
    assert has_contextual or len(chunks) == 1  # single-chunk docs may be identical


# ── Full indexing tests ─────────────────────────────────────────────────

def test_pdf_indexing(sample_pdf_bytes, tmp_path, qdrant_clean):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    import uuid

    doc_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())

    p = tmp_path / "index_test.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")

    qdrant_mgr.index_document(ws_id, doc_id, "index_test.pdf", chunks)

    count = qdrant_mgr.count_document_points(doc_id)
    assert count == len(chunks)
    assert count >= 1


def test_docx_indexing(sample_docx_bytes, tmp_path, qdrant_clean):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    import uuid

    doc_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())
    ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    p = tmp_path / "index_test.docx"
    p.write_bytes(sample_docx_bytes)
    chunks = parse_and_chunk(p, ct)
    qdrant_mgr.index_document(ws_id, doc_id, "index_test.docx", chunks)
    assert qdrant_mgr.count_document_points(doc_id) == len(chunks)


def test_delete_removes_only_target_document(sample_pdf_bytes, tmp_path, qdrant_clean):
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    import uuid

    ws_id = str(uuid.uuid4())
    doc_a = str(uuid.uuid4())
    doc_b = str(uuid.uuid4())

    p = tmp_path / "a.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")

    qdrant_mgr.index_document(ws_id, doc_a, "a.pdf", chunks)
    qdrant_mgr.index_document(ws_id, doc_b, "b.pdf", chunks)

    qdrant_mgr.delete_document_points(doc_a)

    assert qdrant_mgr.count_document_points(doc_a) == 0
    assert qdrant_mgr.count_document_points(doc_b) == len(chunks)


def test_retry_no_duplicate_points(sample_pdf_bytes, tmp_path, qdrant_clean):
    """Indexing same document twice (retry) must not double the point count."""
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    import uuid

    doc_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())

    p = tmp_path / "retry.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")

    qdrant_mgr.index_document(ws_id, doc_id, "retry.pdf", chunks)
    count_first = qdrant_mgr.count_document_points(doc_id)

    # Simulate retry: delete + re-index
    qdrant_mgr.delete_document_points(doc_id)
    qdrant_mgr.index_document(ws_id, doc_id, "retry.pdf", chunks)
    count_retry = qdrant_mgr.count_document_points(doc_id)

    assert count_retry == count_first


def test_chunk_payload_fields(sample_pdf_bytes, tmp_path, qdrant_clean):
    """Verify all required payload fields are present on indexed points."""
    from app.ingestion.pipeline import parse_and_chunk
    from app.ingestion import qdrant_mgr
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    from app.config import settings
    import uuid

    doc_id = str(uuid.uuid4())
    ws_id = str(uuid.uuid4())

    p = tmp_path / "payload_check.pdf"
    p.write_bytes(sample_pdf_bytes)
    chunks = parse_and_chunk(p, "application/pdf")
    qdrant_mgr.index_document(ws_id, doc_id, "payload_check.pdf", chunks)

    client = QdrantClient(url=QDRANT_URL)
    results = client.scroll(
        collection_name=settings.QDRANT_COLLECTION,
        scroll_filter=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]),
        limit=5,
        with_payload=True,
    )
    points = results[0]
    assert points, "No points found"
    for pt in points:
        payload = pt.payload
        assert payload["workspace_id"] == ws_id
        assert payload["document_id"] == doc_id
        assert "raw_text" in payload and payload["raw_text"]
        assert "retrieval_text" in payload and payload["retrieval_text"]
        assert "section_title" in payload
        assert "page_numbers" in payload
        assert "source_filename" in payload
        assert isinstance(payload["chunk_index"], int)


def test_full_pipeline_via_job(sample_pdf_bytes, tmp_path, test_engine, qdrant_clean, monkeypatch):
    """End-to-end: create Document record, run job directly, verify READY + Qdrant."""
    from sqlalchemy.orm import sessionmaker
    import app.database as db_mod
    # Redirect pipeline's SessionLocal to the test database
    monkeypatch.setattr(db_mod, "SessionLocal", sessionmaker(bind=test_engine))
    from app.models.document import Document, DocumentStatus
    from app.models.workspace import Workspace, WorkspaceMembership, MemberRole
    from app.models.user import User
    from app.ingestion.storage import LocalFileStorage
    from app.worker.jobs import run_ingestion_pipeline
    import uuid, bcrypt

    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # Create user + workspace
        user = User(email=f"pipeline_{uuid.uuid4()}@test.com", full_name="P",
                    hashed_password=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode())
        db.add(user)
        db.flush()
        ws = Workspace(name="Pipeline WS")
        db.add(ws)
        db.flush()
        db.add(WorkspaceMembership(user_id=user.id, workspace_id=ws.id, role=MemberRole.owner))

        # Save file
        test_storage = LocalFileStorage(str(tmp_path))
        content = sample_pdf_bytes
        doc_id = uuid.uuid4()
        storage_key = test_storage.save(str(ws.id), str(doc_id), content)

        import hashlib
        doc = Document(
            id=doc_id,
            workspace_id=ws.id,
            filename="pipeline_test.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            storage_key=storage_key,
            content_hash=hashlib.sha256(content).hexdigest(),
            status=DocumentStatus.queued,
        )
        db.add(doc)
        db.commit()

        # Patch storage singleton
        import app.ingestion.storage as storage_mod
        original = storage_mod.storage
        storage_mod.storage = test_storage

        try:
            run_ingestion_pipeline(str(doc_id))
        finally:
            storage_mod.storage = original

        # Verify READY
        db.refresh(doc)
        assert doc.status == DocumentStatus.ready
        assert doc.chunk_count >= 1

        # Verify Qdrant
        from app.ingestion import qdrant_mgr
        assert qdrant_mgr.count_document_points(str(doc_id)) == doc.chunk_count

    finally:
        db.close()
