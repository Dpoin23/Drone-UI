from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(db_path=tmp_path / "test.db", web_dist=tmp_path / "no-dist", token_ttl_hours=1)
    with TestClient(create_app(settings)) as c:
        yield c


def signup(client: TestClient, username: str = "pilot", password: str = "hunter22!") -> dict:
    res = client.post("/api/auth/register", json={"username": username, "password": password})
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


def test_register_login_me_logout(client):
    signup(client)
    assert client.post("/api/auth/register", json={"username": "PILOT", "password": "whatever1"}).status_code == 409

    bad = client.post("/api/auth/login", json={"username": "pilot", "password": "wrong-pass"})
    assert bad.status_code == 401

    res = client.post("/api/auth/login", json={"username": "pilot", "password": "hunter22!"})
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['token']}"}

    assert client.get("/api/auth/me", headers=headers).json()["username"] == "pilot"
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_requires_auth(client):
    assert client.get("/api/issues").status_code == 401
    assert client.get("/api/issues", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_issue_crud_and_status_transitions(client):
    h = signup(client)
    created = client.post(
        "/api/issues",
        headers=h,
        json={"category": "security", "title": "Person at north gate", "severity": "high"},
    ).json()
    assert created["status"] == "open" and created["resolved_at"] is None

    client.post("/api/issues", headers=h, json={"category": "maintenance", "title": "Fence sag"})

    security = client.get("/api/issues", headers=h, params={"category": "security"}).json()
    assert [i["title"] for i in security] == ["Person at north gate"]

    resolved = client.patch(f"/api/issues/{created['id']}", headers=h, json={"status": "resolved"}).json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]

    reopened = client.patch(f"/api/issues/{created['id']}", headers=h, json={"status": "open"}).json()
    assert reopened["resolved_at"] is None

    assert client.delete(f"/api/issues/{created['id']}", headers=h).status_code == 204
    assert len(client.get("/api/issues", headers=h).json()) == 1


def test_issues_are_scoped_per_account(client):
    alice = signup(client, "alice")
    bob = signup(client, "bob")
    issue = client.post("/api/issues", headers=alice, json={"category": "maintenance", "title": "Debris"}).json()

    assert client.get("/api/issues", headers=bob).json() == []
    assert client.patch(f"/api/issues/{issue['id']}", headers=bob, json={"status": "resolved"}).status_code == 404
    assert client.delete(f"/api/issues/{issue['id']}", headers=bob).status_code == 404


def test_stream_settings_persist(client):
    h = signup(client)
    assert client.get("/api/stream-settings", headers=h).json() == {"transport": "demo", "url": ""}
    body = {"transport": "webrtc", "url": "http://drone.local:8889/cam/whep"}
    assert client.put("/api/stream-settings", headers=h, json=body).json() == body
    assert client.get("/api/stream-settings", headers=h).json() == body
