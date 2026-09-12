"""Tests: user registration, login, logout, and auth guard."""

_ALICE = {"email": "alice@example.com", "full_name": "Alice", "password": "pass123"}


def test_register_success(client):
    resp = client.post("/api/auth/register", json=_ALICE)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == _ALICE["email"]
    assert data["full_name"] == _ALICE["full_name"]
    assert "id" in data
    assert "access_token" in resp.cookies


def test_register_duplicate_rejected(client):
    client.post("/api/auth/register", json=_ALICE)
    resp = client.post("/api/auth/register", json=_ALICE)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


def test_login_success(client):
    client.post("/api/auth/register", json=_ALICE)
    # Clear cookie to simulate fresh login
    client.cookies.clear()
    resp = client.post("/api/auth/login", json={
        "email": _ALICE["email"],
        "password": _ALICE["password"],
    })
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_wrong_password(client):
    client.post("/api/auth/register", json=_ALICE)
    client.cookies.clear()
    resp = client.post("/api/auth/login", json={
        "email": _ALICE["email"],
        "password": "wrong",
    })
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post("/api/auth/login", json={
        "email": "nobody@example.com",
        "password": "pass",
    })
    assert resp.status_code == 401


def test_unauthenticated_me_fails(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_authenticated_me_succeeds(client):
    client.post("/api/auth/register", json=_ALICE)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == _ALICE["email"]


def test_logout_clears_session(client):
    client.post("/api/auth/register", json=_ALICE)
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
