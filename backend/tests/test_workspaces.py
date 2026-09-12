"""Tests: workspace creation, listing, and cross-user authorization."""

_ALICE = {"email": "alice@example.com", "full_name": "Alice", "password": "passA"}
_BOB = {"email": "bob@example.com", "full_name": "Bob", "password": "passB"}


def _register_login(client, user: dict):
    client.post("/api/auth/register", json=user)
    client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})


def test_create_workspace_authenticated(client):
    _register_login(client, _ALICE)
    resp = client.post("/api/workspaces", json={"name": "Alice KB"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice KB"
    assert data["role"] == "owner"
    assert "id" in data


def test_create_workspace_unauthenticated(client):
    resp = client.post("/api/workspaces", json={"name": "No Auth"})
    assert resp.status_code == 401


def test_list_workspaces_shows_own_only(client):
    _register_login(client, _ALICE)
    client.post("/api/workspaces", json={"name": "WS 1"})
    client.post("/api/workspaces", json={"name": "WS 2"})
    resp = client.get("/api/workspaces")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_workspace(client):
    _register_login(client, _ALICE)
    ws_id = client.post("/api/workspaces", json={"name": "My WS"}).json()["id"]
    resp = client.get(f"/api/workspaces/{ws_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == ws_id


def test_get_nonexistent_workspace(client):
    _register_login(client, _ALICE)
    resp = client.get("/api/workspaces/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_cross_user_workspace_isolation(client):
    """User A cannot access workspace belonging to User B, and vice versa."""
    # Alice logs in and creates her workspace
    _register_login(client, _ALICE)
    alice_ws_id = client.post("/api/workspaces", json={"name": "Alice WS"}).json()["id"]

    # Switch to Bob
    client.post("/api/auth/logout")
    _register_login(client, _BOB)
    bob_ws_id = client.post("/api/workspaces", json={"name": "Bob WS"}).json()["id"]

    # Bob cannot see Alice's workspace
    resp = client.get(f"/api/workspaces/{alice_ws_id}")
    assert resp.status_code == 404

    # Bob's list does not contain Alice's workspace
    ids = [w["id"] for w in client.get("/api/workspaces").json()]
    assert alice_ws_id not in ids
    assert bob_ws_id in ids

    # Switch back to Alice
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": _ALICE["email"], "password": _ALICE["password"]})

    # Alice cannot see Bob's workspace
    resp = client.get(f"/api/workspaces/{bob_ws_id}")
    assert resp.status_code == 404

    ids = [w["id"] for w in client.get("/api/workspaces").json()]
    assert bob_ws_id not in ids
    assert alice_ws_id in ids


def test_migration_tables_exist(test_engine):
    """Verify Alembic migrations established the full schema from a clean state."""
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(test_engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "workspaces" in tables
    assert "workspace_memberships" in tables
    assert "alembic_version" in tables
