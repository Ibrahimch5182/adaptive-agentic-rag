"""
Test setup:
- session-scoped: creates contextguard_test DB, runs Alembic migrations
- function-scoped: per-test client with mocked queue and tmp storage, tables truncated after each test
- integration fixtures: Qdrant-connected client for pipeline tests
"""
import io
import os
import subprocess
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.config import settings as _settings  # loads .env

_base_url = _settings.DATABASE_URL
TEST_DATABASE_URL = _base_url.rsplit("/", 1)[0] + "/contextguard_test"
ADMIN_DATABASE_URL = _base_url.rsplit("/", 1)[0] + "/postgres"
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


# ──────────────────────────────────────────────
# Session-level DB setup
# ──────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _create_test_db():
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS contextguard_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE contextguard_test"))
    admin_engine.dispose()

    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=_backend_dir, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"Migrations failed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    yield

    admin_engine2 = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine2.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS contextguard_test WITH (FORCE)"))
    admin_engine2.dispose()


@pytest.fixture(scope="session")
def test_engine(_create_test_db):
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


def _truncate_all(engine):
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM workspace_memberships"))
        conn.execute(text("DELETE FROM workspaces"))
        conn.execute(text("DELETE FROM users"))
        conn.commit()


# ──────────────────────────────────────────────
# Per-test client (mocked queue + tmp storage)
# ──────────────────────────────────────────────

@pytest.fixture
def client(test_engine, tmp_path, monkeypatch):
    from app.main import app
    from app.api.deps import get_db
    from app.ingestion.storage import LocalFileStorage
    import app.ingestion.storage as storage_mod
    import app.worker.jobs as jobs_mod

    # Patch storage to use tmp dir
    test_storage = LocalFileStorage(str(tmp_path))
    monkeypatch.setattr(storage_mod, "storage", test_storage)

    # Patch enqueue to no-op (no Redis needed for API tests)
    monkeypatch.setattr(jobs_mod, "enqueue_ingestion", lambda doc_id: None)

    # Patch settings for storage dir
    monkeypatch.setattr("app.api.documents.storage", test_storage)

    TestSession = sessionmaker(bind=test_engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
    _truncate_all(test_engine)


# ──────────────────────────────────────────────
# Document test fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def sample_pdf_bytes():
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 10, "Test Document", ln=True)
    pdf.set_font("Helvetica", "B", size=13)
    pdf.cell(0, 10, "Section 1: Introduction", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "This section provides an introduction to the test document. "
                          "It contains multiple sentences to ensure proper chunking behavior.")
    pdf.set_font("Helvetica", "B", size=13)
    pdf.cell(0, 10, "Section 2: Details", ln=True)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 8, "This section contains detailed information about the topic. "
                          "The purpose is to verify that Docling extracts structured content correctly.")
    return pdf.output()


@pytest.fixture
def sample_docx_bytes():
    from io import BytesIO
    from docx import Document as DocxDoc
    doc = DocxDoc()
    doc.add_heading("Test DOCX Document", 0)
    doc.add_heading("Section A", 1)
    doc.add_paragraph("This is section A with enough content to form a meaningful chunk.")
    doc.add_heading("Section B", 1)
    doc.add_paragraph("This is section B with additional content for testing purposes.")
    bio = BytesIO()
    doc.save(bio)
    return bio.getvalue()


@pytest.fixture
def sample_md_bytes():
    return b"""# Test Markdown Document

## Section One

This is the first section of the markdown test document.
It contains multiple lines to ensure proper parsing.

## Section Two

This is the second section with more content.
Docling should preserve the heading structure.
"""
