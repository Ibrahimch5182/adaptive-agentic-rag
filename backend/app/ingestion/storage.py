"""File storage abstraction: local filesystem (dev) or S3-compatible (production).

Contract used by the rest of the app:
  save(workspace_id, document_id, data) -> storage_key
  materialize(storage_key)              -> context manager yielding a local Path
                                            (for Docling, which needs a real file)
  delete(storage_key)                   -> None

Backend and worker may run as separate ephemeral containers, so a document's original
must be reachable from either without relying on shared local disk — that's what
`materialize` abstracts: local storage just hands back the real path, S3 storage
downloads to a temp file that is deleted afterward.
"""
from __future__ import annotations
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from app.config import settings


class LocalFileStorage:
    def __init__(self, base_dir: str | None = None):
        self._base = Path(base_dir or settings.UPLOAD_DIR)

    def save(self, workspace_id: str, document_id: str, data: bytes) -> str:
        """Persist file bytes; returns opaque storage key."""
        # Key is workspace_id/document_id — never uses client filename in path
        key = f"{workspace_id}/{document_id}"
        dest = self._base / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return key

    @contextmanager
    def materialize(self, storage_key: str) -> Iterator[Path]:
        yield self._base / storage_key

    def delete(self, storage_key: str) -> None:
        path = self._base / storage_key
        path.unlink(missing_ok=True)
        # Clean up empty parent directories
        for parent in [path.parent, path.parent.parent]:
            try:
                parent.rmdir()
            except OSError:
                break


class S3FileStorage:
    """S3-compatible object storage. Originals are private — no public ACLs, no
    public URLs handed to the frontend. Server-side credentials only."""

    def __init__(self):
        self._bucket = settings.S3_BUCKET

    def _client(self):
        import boto3
        kwargs = {}
        if settings.S3_REGION:
            kwargs["region_name"] = settings.S3_REGION
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY picked up from env by boto3's
        # standard credential chain — never read or logged here.
        return boto3.client("s3", **kwargs)

    def save(self, workspace_id: str, document_id: str, data: bytes) -> str:
        key = f"{workspace_id}/{document_id}"
        self._client().put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    @contextmanager
    def materialize(self, storage_key: str) -> Iterator[Path]:
        import tempfile
        suffix = Path(storage_key).suffix
        fd, tmp_name = tempfile.mkstemp(prefix="cg-", suffix=suffix)
        tmp_path = Path(tmp_name)
        try:
            import os
            os.close(fd)
            self._client().download_file(self._bucket, storage_key, str(tmp_path))
            yield tmp_path
        finally:
            tmp_path.unlink(missing_ok=True)

    def delete(self, storage_key: str) -> None:
        self._client().delete_object(Bucket=self._bucket, Key=storage_key)


def _build_storage():
    if settings.STORAGE_BACKEND == "s3":
        return S3FileStorage()
    return LocalFileStorage()


# Module-level singleton — overridable in tests
storage = _build_storage()
