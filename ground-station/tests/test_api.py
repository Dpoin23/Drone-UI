from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "test.db",
        uploads_dir=tmp_path / "uploads",
        web_dist=tmp_path / "no-dist",
        token_ttl_hours=1,
        max_image_bytes=1024,
        max_images_per_issue=3,
    )
    with TestClient(create_app(settings)) as c:
        c.uploads_dir = settings.uploads_dir
        yield c


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


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


def test_image_upload_view_delete(client):
    h = signup(client)
    issue = client.post("/api/issues", headers=h, json={"category": "security", "title": "Gate open"}).json()
    assert issue["images"] == []

    res = client.post(
        f"/api/issues/{issue['id']}/images",
        headers=h,
        files=[("files", ("a.png", PNG, "image/png")), ("files", ("b.jpg", JPEG, "image/jpeg"))],
    )
    assert res.status_code == 201, res.text
    images = res.json()["images"]
    assert [(i["filename"], i["content_type"]) for i in images] == [("a.png", "image/png"), ("b.jpg", "image/jpeg")]

    listed = client.get("/api/issues", headers=h).json()
    assert [i["id"] for i in listed[0]["images"]] == [i["id"] for i in images]

    img = client.get(f"/api/issues/{issue['id']}/images/{images[0]['id']}", headers=h)
    assert img.status_code == 200 and img.content == PNG
    assert img.headers["content-type"] == "image/png"

    after = client.delete(f"/api/issues/{issue['id']}/images/{images[0]['id']}", headers=h).json()
    assert [i["filename"] for i in after["images"]] == ["b.jpg"]

    client.delete(f"/api/issues/{issue['id']}", headers=h)
    assert not any(client.uploads_dir.rglob("*.*"))


def test_image_validation(client):
    h = signup(client)
    issue_id = client.post("/api/issues", headers=h, json={"category": "maintenance", "title": "Debris"}).json()["id"]
    url = f"/api/issues/{issue_id}/images"

    fake = client.post(url, headers=h, files=[("files", ("x.png", b"<svg onload=alert(1)>", "image/png"))])
    assert fake.status_code == 415

    big = client.post(url, headers=h, files=[("files", ("big.png", PNG + b"\x00" * 2048, "image/png"))])
    assert big.status_code == 413

    too_many = client.post(url, headers=h, files=[("files", (f"{n}.png", PNG, "image/png")) for n in range(4)])
    assert too_many.status_code == 400


def test_images_are_scoped_per_account(client):
    alice = signup(client, "alice")
    bob = signup(client, "bob")
    issue_id = client.post("/api/issues", headers=alice, json={"category": "security", "title": "Car"}).json()["id"]
    image_id = client.post(
        f"/api/issues/{issue_id}/images", headers=alice, files=[("files", ("a.png", PNG, "image/png"))]
    ).json()["images"][0]["id"]

    assert client.get(f"/api/issues/{issue_id}/images/{image_id}", headers=bob).status_code == 404
    assert client.post(
        f"/api/issues/{issue_id}/images", headers=bob, files=[("files", ("a.png", PNG, "image/png"))]
    ).status_code == 404
    assert client.delete(f"/api/issues/{issue_id}/images/{image_id}", headers=bob).status_code == 404


def test_stream_settings_persist(client):
    h = signup(client)
    assert client.get("/api/stream-settings", headers=h).json() == {"transport": "demo", "url": ""}
    body = {"transport": "webrtc", "url": "http://drone.local:8889/cam/whep"}
    assert client.put("/api/stream-settings", headers=h, json=body).json() == body
    assert client.get("/api/stream-settings", headers=h).json() == body
