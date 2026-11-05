import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.storage import videos
from app.storage.db import init_db


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "test.db",
        uploads_dir=tmp_path / "uploads",
        videos_dir=tmp_path / "videos",
        web_dist=tmp_path / "no-dist",
        token_ttl_hours=1,
        max_image_bytes=1024,
        max_images_per_issue=3,
        max_video_bytes=4096,
    )
    with TestClient(create_app(settings)) as c:
        c.uploads_dir = settings.uploads_dir
        c.videos_dir = settings.videos_dir
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

    deleted = client.delete(f"/api/issues/{created['id']}", headers=h)
    assert deleted.status_code == 204
    assert len(client.get("/api/issues", headers=h).json()) == 1


def test_issues_are_scoped_per_account(client):
    alice = signup(client, "alice")
    bob = signup(client, "bob")
    issue = client.post("/api/issues", headers=alice, json={"category": "maintenance", "title": "Debris"}).json()

    assert client.get("/api/issues", headers=bob).json() == []
    assert client.patch(f"/api/issues/{issue['id']}", headers=bob, json={"status": "resolved"}).status_code == 404
    deleted = client.delete(f"/api/issues/{issue['id']}", headers=bob)
    assert deleted.status_code == 404


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
    deleted = client.delete(f"/api/issues/{issue_id}/images/{image_id}", headers=bob)
    assert deleted.status_code == 404


def test_stream_settings_persist(client):
    h = signup(client)
    assert client.get("/api/stream-settings", headers=h).json() == {"transport": "demo", "url": ""}
    body = {"transport": "webrtc", "url": "http://drone.local:8889/cam/whep"}
    assert client.put("/api/stream-settings", headers=h, json=body).json() == body
    assert client.get("/api/stream-settings", headers=h).json() == body


MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 1000


def upload_video(client: TestClient, headers: dict, data: bytes = MP4, name: str = "Gate cam.mp4"):
    return client.post("/api/videos/upload", headers=headers, files={"file": (name, data, "video/mp4")})


def wait_for_import(client: TestClient, headers: dict, video_id: int) -> dict:
    for _ in range(200):
        video = client.get(f"/api/videos/{video_id}", headers=headers).json()
        if video["status"] != "downloading":
            return video
        time.sleep(0.01)
    raise AssertionError("import never finished")


def test_video_upload_playback_and_delete(client):
    h = signup(client)
    res = upload_video(client, h)
    assert res.status_code == 201, res.text
    video = res.json()
    assert (video["title"], video["status"], video["content_type"], video["size_bytes"]) == (
        "Gate cam", "ready", "video/mp4", len(MP4)
    )
    assert [v["id"] for v in client.get("/api/videos", headers=h).json()] == [video["id"]]

    url = client.get(f"/api/videos/{video['id']}/playback", headers=h).json()["url"]
    full = client.get(url)
    assert full.status_code == 200 and full.content == MP4
    assert full.headers["accept-ranges"] == "bytes"

    partial = client.get(url, headers={"Range": "bytes=4-11"})
    assert partial.status_code == 206 and partial.content == b"ftypisom"

    assert client.get(url.replace("sig=", "sig=0")).status_code == 403
    assert client.get(f"/api/videos/{video['id']}/file").status_code == 422

    deleted = client.delete(f"/api/videos/{video['id']}", headers=h)
    assert deleted.status_code == 204
    assert client.get(url).status_code == 404
    assert not any(client.videos_dir.rglob("*.*"))


def test_video_upload_validation(client):
    h = signup(client)
    assert upload_video(client, h, data=b"<html>not a video</html>").status_code == 415
    assert upload_video(client, h, data=MP4 * 5).status_code == 413
    assert client.get("/api/videos", headers=h).json() == []
    assert not any(client.videos_dir.rglob("*.*"))


def test_videos_are_scoped_per_account(client):
    alice = signup(client, "alice")
    bob = signup(client, "bob")
    video_id = upload_video(client, alice).json()["id"]

    assert client.get("/api/videos", headers=bob).json() == []
    assert client.get(f"/api/videos/{video_id}", headers=bob).status_code == 404
    assert client.get(f"/api/videos/{video_id}/playback", headers=bob).status_code == 404
    deleted = client.delete(f"/api/videos/{video_id}", headers=bob)
    assert deleted.status_code == 404
    bad = client.put("/api/stream-settings", headers=bob, json={"transport": "video", "url": str(video_id)})
    assert bad.status_code == 400


def test_video_transport_setting(client):
    h = signup(client)
    video_id = upload_video(client, h).json()["id"]
    body = {"transport": "video", "url": str(video_id)}
    assert client.put("/api/stream-settings", headers=h, json=body).json() == body
    assert client.put("/api/stream-settings", headers=h, json={"transport": "video", "url": "x"}).status_code == 400

    client.delete(f"/api/videos/{video_id}", headers=h)
    assert client.get("/api/stream-settings", headers=h).json() == {"transport": "video", "url": ""}


def test_video_import_from_link(client, monkeypatch):
    def fake_download(url, dest_stem, *, max_bytes, on_info, on_progress, cancelled):
        on_info(videos.RemoteInfo(title="Perimeter flyover", duration_s=12.5, fps=30.0))
        on_progress(0.5)
        path = dest_stem.with_suffix(".mp4")
        path.write_bytes(MP4)
        return path

    monkeypatch.setattr(videos, "download_remote", fake_download)
    h = signup(client)
    res = client.post("/api/videos/import", headers=h, json={"url": "https://www.youtube.com/watch?v=abc"})
    assert res.status_code == 202 and res.json()["status"] == "downloading"

    video = wait_for_import(client, h, res.json()["id"])
    assert (video["status"], video["title"], video["duration_s"], video["fps"], video["source"]) == (
        "ready", "Perimeter flyover", 12.5, 30.0, "url"
    )
    url = client.get(f"/api/videos/{video['id']}/playback", headers=h).json()["url"]
    assert client.get(url).content == MP4


def test_video_import_failure(client, monkeypatch):
    def failing_download(url, dest_stem, **_):
        dest_stem.with_suffix(".mp4.part").write_bytes(b"partial")
        raise videos.InvalidVideo("Live streams aren't supported yet. Use a recorded video.")

    monkeypatch.setattr(videos, "download_remote", failing_download)
    h = signup(client)
    assert client.post("/api/videos/import", headers=h, json={"url": "ftp://x"}).status_code == 400

    video_id = client.post("/api/videos/import", headers=h, json={"url": "https://example.com/live"}).json()["id"]
    video = wait_for_import(client, h, video_id)
    assert video["status"] == "error" and "Live streams" in video["error"]
    assert client.get(f"/api/videos/{video_id}/playback", headers=h).status_code == 409
    assert not any(client.videos_dir.rglob("*.*"))


def test_old_stream_settings_table_is_migrated(tmp_path):
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, created_at TEXT);
        CREATE TABLE stream_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            transport TEXT NOT NULL CHECK (transport IN ('demo', 'webrtc', 'mjpeg')),
            url TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        INSERT INTO users VALUES (1, 'pilot', 'x', 'now');
        INSERT INTO stream_settings VALUES (1, 'mjpeg', 'http://drone/stream', 'now');
        """
    )
    conn.close()

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT transport, url FROM stream_settings").fetchall() == [("mjpeg", "http://drone/stream")]
    conn.execute("UPDATE stream_settings SET transport = 'video'")
    conn.close()


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("ERROR: [generic] not-a-video: Unable to download webpage: HTTP Error 404: Not Found "
         "(caused by <HTTPError 404: Not Found>)", "Unable to download webpage: HTTP Error 404: Not Found"),
        ("ERROR: [youtube] dQw4w9WgXcQ: Video unavailable", "Video unavailable"),
        ("ERROR: Unsupported URL: https://example.com", "No video found at that link"),
    ],
)
def test_import_errors_are_readable(raw, shown):
    assert videos._describe_error(RuntimeError(raw)) == shown
