"""Document API tests — fast, no Qdrant/Redis required (queue is mocked)."""
import io

_ALICE = {"email": "alice@test.com", "full_name": "Alice", "password": "pass123"}
_BOB = {"email": "bob@test.com", "full_name": "Bob", "password": "pass456"}


def _register_login(client, user):
    client.post("/api/auth/register", json=user)
    client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})


def _create_ws(client, name="My WS"):
    return client.post("/api/workspaces", json={"name": name}).json()["id"]


def _upload(client, ws_id, content=b"hello pdf content", filename="test.pdf"):
    return client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


# ── Upload ─────────────────────────────────────────────────────────────

def test_upload_returns_queued(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    resp = _upload(client, ws_id, sample_pdf_bytes, "report.pdf")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["filename"] == "report.pdf"
    assert data["workspace_id"] == ws_id


def test_upload_unauthenticated_rejected(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    client.post("/api/auth/logout")
    resp = _upload(client, ws_id, sample_pdf_bytes)
    assert resp.status_code == 401


def test_upload_wrong_workspace_rejected(client, sample_pdf_bytes):
    """User B cannot upload to User A's workspace."""
    _register_login(client, _ALICE)
    ws_a = _create_ws(client, "Alice WS")

    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    resp = _upload(client, ws_a, sample_pdf_bytes)
    assert resp.status_code == 404


def test_upload_unsupported_format_rejected(client):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    resp = _upload(client, ws_id, b"not an exe", "malware.exe")
    assert resp.status_code == 400


def test_upload_empty_file_rejected(client):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    resp = _upload(client, ws_id, b"", "empty.pdf")
    assert resp.status_code == 400


def test_upload_duplicate_content_rejected(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    r1 = _upload(client, ws_id, sample_pdf_bytes, "first.pdf")
    assert r1.status_code == 202
    r2 = _upload(client, ws_id, sample_pdf_bytes, "second.pdf")  # same bytes
    assert r2.status_code == 409
    assert "X-Existing-Document-Id" in r2.headers


def test_duplicate_allowed_in_different_workspaces(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws1 = _create_ws(client, "WS1")
    ws2 = _create_ws(client, "WS2")
    r1 = _upload(client, ws1, sample_pdf_bytes)
    r2 = _upload(client, ws2, sample_pdf_bytes)  # same content, different workspace
    assert r1.status_code == 202
    assert r2.status_code == 202


# ── List / Get ─────────────────────────────────────────────────────────

def test_list_documents(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    _upload(client, ws_id, sample_pdf_bytes)
    resp = client.get(f"/api/workspaces/{ws_id}/documents")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_documents_cross_user_isolated(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_a = _create_ws(client, "Alice WS")
    _upload(client, ws_a, sample_pdf_bytes)

    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    resp = client.get(f"/api/workspaces/{ws_a}/documents")
    assert resp.status_code == 404


def test_get_document_cross_user_isolated(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_a = _create_ws(client, "Alice WS")
    doc_id = _upload(client, ws_a, sample_pdf_bytes).json()["id"]

    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    resp = client.get(f"/api/workspaces/{ws_a}/documents/{doc_id}")
    assert resp.status_code == 404


def test_get_nonexistent_document(client):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    resp = client.get(
        f"/api/workspaces/{ws_id}/documents/00000000-0000-0000-0000-000000000000"
    )
    assert resp.status_code == 404


# ── Delete ─────────────────────────────────────────────────────────────

def test_delete_document(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    doc_id = _upload(client, ws_id, sample_pdf_bytes).json()["id"]
    resp = client.delete(f"/api/workspaces/{ws_id}/documents/{doc_id}")
    assert resp.status_code == 204
    # Should be gone
    assert client.get(f"/api/workspaces/{ws_id}/documents/{doc_id}").status_code == 404


def test_delete_cross_user_rejected(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_a = _create_ws(client, "Alice WS")
    doc_id = _upload(client, ws_a, sample_pdf_bytes).json()["id"]

    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    resp = client.delete(f"/api/workspaces/{ws_a}/documents/{doc_id}")
    assert resp.status_code == 404


# ── Retry ─────────────────────────────────────────────────────────────

def test_retry_non_failed_document_rejected(client, sample_pdf_bytes):
    _register_login(client, _ALICE)
    ws_id = _create_ws(client)
    doc_id = _upload(client, ws_id, sample_pdf_bytes).json()["id"]
    resp = client.post(f"/api/workspaces/{ws_id}/documents/{doc_id}/retry")
    assert resp.status_code == 400  # not FAILED
