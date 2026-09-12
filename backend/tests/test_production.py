"""Phase 6 focused tests: storage abstraction (local + mocked S3), config validation,
upload size enforcement. No Docker/live S3/live Qdrant required.
"""
import io
import pytest


# ── Local storage: materialize() contract ───────────────────────────────────

def test_local_storage_materialize_yields_real_path(tmp_path):
    from app.ingestion.storage import LocalFileStorage
    store = LocalFileStorage(str(tmp_path))
    key = store.save("ws1", "doc1", b"hello world")
    with store.materialize(key) as path:
        assert path.exists()
        assert path.read_bytes() == b"hello world"


def test_local_storage_delete_removes_file(tmp_path):
    from app.ingestion.storage import LocalFileStorage
    store = LocalFileStorage(str(tmp_path))
    key = store.save("ws1", "doc1", b"data")
    store.delete(key)
    with store.materialize(key) as path:
        assert not path.exists()


# ── S3 storage: mocked boto3 client ──────────────────────────────────────────

class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def download_file(self, Bucket, Key, Filename):
        with open(Filename, "wb") as f:
            f.write(self.objects[Key])

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


def test_s3_storage_save_and_materialize(monkeypatch):
    from app.ingestion.storage import S3FileStorage
    fake = _FakeS3Client()
    store = S3FileStorage()
    monkeypatch.setattr(store, "_client", lambda: fake)

    key = store.save("ws1", "doc1", b"pdf bytes")
    assert fake.objects[key] == b"pdf bytes"

    with store.materialize(key) as path:
        assert path.exists()
        assert path.read_bytes() == b"pdf bytes"
    # temp file cleaned up after the context manager exits
    assert not path.exists()


def test_s3_storage_delete(monkeypatch):
    from app.ingestion.storage import S3FileStorage
    fake = _FakeS3Client()
    store = S3FileStorage()
    monkeypatch.setattr(store, "_client", lambda: fake)

    key = store.save("ws1", "doc1", b"x")
    store.delete(key)
    assert key in fake.deleted
    assert key not in fake.objects


def test_storage_factory_selects_backend(monkeypatch):
    from app import config as config_mod
    from app.ingestion.storage import _build_storage, LocalFileStorage, S3FileStorage

    monkeypatch.setattr(config_mod.settings, "STORAGE_BACKEND", "local")
    assert isinstance(_build_storage(), LocalFileStorage)

    monkeypatch.setattr(config_mod.settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(config_mod.settings, "S3_BUCKET", "test-bucket")
    assert isinstance(_build_storage(), S3FileStorage)


# ── Config validation ────────────────────────────────────────────────────────

def test_settings_rejects_short_secret_key(monkeypatch):
    from app.config import Settings
    with pytest.raises(Exception):
        Settings(DATABASE_URL="postgresql://x/y", SECRET_KEY="too-short")


def test_settings_rejects_invalid_storage_backend():
    from app.config import Settings
    with pytest.raises(Exception):
        Settings(
            DATABASE_URL="postgresql://x/y",
            SECRET_KEY="a" * 32,
            STORAGE_BACKEND="ftp",
        )


def test_settings_accepts_valid_config():
    from app.config import Settings
    s = Settings(DATABASE_URL="postgresql://x/y", SECRET_KEY="a" * 32)
    assert s.STORAGE_BACKEND == "local"
    assert s.COOKIE_SECURE is False


# ── Upload size enforcement ──────────────────────────────────────────────────

_ALICE = {"email": "sizecap@test.com", "full_name": "Cap", "password": "pass123"}


def test_upload_exceeding_max_size_rejected(client, monkeypatch):
    from app.api import documents as documents_mod
    monkeypatch.setattr(documents_mod.settings, "MAX_UPLOAD_SIZE_MB", 1)

    client.post("/api/auth/register", json=_ALICE)
    client.post("/api/auth/login", json={"email": _ALICE["email"], "password": _ALICE["password"]})
    ws_id = client.post("/api/workspaces", json={"name": "WS"}).json()["id"]

    oversized = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB cap
    resp = client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert resp.status_code == 413


# ── /ready endpoint shape ────────────────────────────────────────────────────

def test_ready_endpoint_reports_per_dependency_checks(client):
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert set(data["checks"].keys()) == {"database", "redis", "qdrant"}
