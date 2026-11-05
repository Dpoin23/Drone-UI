import json
import struct
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.vision import modes
from app.vision.aggregate import DetectionAggregator
from app.vision.detectors import RawDetection
from app.vision.frames import LatestFrameBuffer
from app.vision.sources import InvalidFrame, parse_browser_frame, whep_to_rtsp
from app.vision.telemetry import Telemetry, TelemetryState
from app.vision.tracking import IouTracker, TrackRegistry

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class FakeDetector:
    """Reports one person moving right, as ByteTrack track 7, on every frame it sees."""

    device = "test"

    def __init__(self, stream: str) -> None:
        self.name = f"fake-{stream}"
        self.stream = stream
        self.frames: list[int] = []
        self.resets = 0

    def detect(self, frame):
        self.frames.append(frame.seq)
        x = 0.1 + 0.01 * len(self.frames)
        if self.stream == "intruder":
            return [RawDetection("person", 0.9, (x, 0.2, 0.1, 0.3), track_id=7)]
        return [RawDetection("corrosion", 0.8, (0.5, 0.5, 0.2, 0.2))]

    def reset(self):
        self.resets += 1


@pytest.fixture
def app_client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "test.db",
        uploads_dir=tmp_path / "uploads",
        videos_dir=tmp_path / "videos",
        web_dist=tmp_path / "no-dist",
        token_ttl_hours=1,
        models_dir=tmp_path / "models",
    )
    app = create_app(settings)
    detectors: dict[str, FakeDetector] = {}

    def factory(stream, _settings):
        detectors[stream] = FakeDetector(stream)
        return detectors[stream]

    app.state.vision.detector_factory = factory
    with TestClient(app) as c:
        c.detectors = detectors
        c.uploads_dir = settings.uploads_dir
        yield c


def signup(client: TestClient, username: str = "pilot") -> tuple[dict, str]:
    res = client.post("/api/auth/register", json={"username": username, "password": "hunter22!"})
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}, token


def frame_message(media_time: float | None = None, epoch: int = 0) -> bytes:
    header = json.dumps({"ts": time.time() * 1000, "media_time": media_time, "epoch": epoch, "w": 64, "h": 36})
    return struct.pack(">I", len(header)) + header.encode() + JPEG


def collect(ws, done, limit: int = 300) -> list[dict]:
    """Read events until ``done(events)`` holds. Stats arrive every second, so this can't hang."""
    events: list[dict] = []
    for _ in range(limit):
        events.append(ws.receive_json())
        if done(events):
            return events
    raise AssertionError(f"expected events never arrived: {[e['type'] for e in events]}")


def first(events: list[dict], **match) -> dict | None:
    return next((e for e in events if all(e.get(k) == v for k, v in match.items())), None)


# ---- Units -------------------------------------------------------------------------------------


def test_latest_frame_buffer_skips_stale_frames():
    buf = LatestFrameBuffer()
    for i in range(5):
        buf.put(ts=float(i), epoch=1, jpeg=JPEG)
    frame = buf.wait_newer(0, timeout=0.1)
    assert frame.seq == 5 and frame.ts == 4.0
    assert buf.overwritten == 4
    assert buf.wait_newer(5, timeout=0.05) is None

    got = []
    waiter = threading.Thread(target=lambda: got.append(buf.wait_newer(5, timeout=2)))
    waiter.start()
    time.sleep(0.05)
    buf.put(ts=9.0, epoch=1, jpeg=JPEG)
    waiter.join()
    assert got[0].seq == 6


def test_mode_rates_and_telemetry_aliases():
    rates = modes.merged_rates({"patrol": {"intruder": 99, "bogus": 3}, "nope": {}})
    assert rates["patrol"]["intruder"] == modes.MAX_RATE
    assert rates["takeoff_landing"] == {"intruder": 0, "maintenance": 0}
    assert rates["inspection"]["maintenance"] > 0 and rates["transit"]["maintenance"] == 0
    assert modes.mode_from_telemetry("RTL") == "return_to_base"
    assert modes.mode_from_telemetry("Perimeter Patrol") == "patrol"
    assert modes.mode_from_telemetry("stabilize") is None


def test_whep_url_maps_to_mediamtx_rtsp():
    assert whep_to_rtsp("http://drone.local:8889/cam/whep") == "rtsp://drone.local:8554/cam"
    assert whep_to_rtsp("https://192.168.4.1:8889/cam/") == "rtsp://192.168.4.1:8554/cam"


def test_browser_frame_parsing():
    frame = parse_browser_frame(frame_message(media_time=1.5, epoch=2))
    assert (frame.media_time, frame.epoch, frame.width, frame.jpeg) == (1.5, 2, 64, JPEG)
    with pytest.raises(InvalidFrame):
        parse_browser_frame(struct.pack(">I", 2) + b"{}" + b"<svg>")
    with pytest.raises(InvalidFrame):
        parse_browser_frame(b"\x00\x00\xff\xff" + JPEG)


def test_track_velocity_and_defect_matching():
    reg = TrackRegistry()
    reg.update(1, (0.1, 0.1, 0.1, 0.1), "person", 0.8, t=0.0)
    track = reg.update(1, (0.2, 0.1, 0.1, 0.1), "person", 0.9, t=0.5)
    assert track.hits == 2 and track.vx == pytest.approx(0.1) and track.vy == 0

    iou = IouTracker()
    first = iou.update([("crack", (0.1, 0.1, 0.2, 0.2)), ("rust", (0.6, 0.6, 0.1, 0.1))])
    second = iou.update([("crack", (0.12, 0.1, 0.2, 0.2))])
    assert second[0].track_id == first[0].track_id and second[0].hits == 2


def test_aggregator_gps_tags_and_confirms_once():
    events = []
    telemetry = TelemetryState()
    agg = DetectionAggregator(publish=events.append, telemetry=telemetry, issue_sink=None,
                              context=lambda: {"auto_issues": False})
    buf = LatestFrameBuffer()
    for i in range(4):
        now = time.time()
        telemetry.update(Telemetry(ts=now, lat=37.0, lon=-122.0, alt_m=30))
        frame = buf.put(ts=now, epoch=1, jpeg=JPEG)
        agg.handle("intruder", frame, [RawDetection("pedestrian", 0.8, (0.1 * i, 0, 0.1, 0.1), track_id=3)],
                   detector="t", infer_ms=1)
    detections = [e for e in events if e["type"] == "detections"]
    assert detections[-1]["position"]["lat"] == 37.0
    assert detections[-1]["items"][0]["kind"] == "person"
    assert [e["type"] for e in events].count("alert") == 1


# ---- API and live pipeline ---------------------------------------------------------------------


def test_vision_settings_round_trip(app_client):
    h, _ = signup(app_client)
    defaults = app_client.get("/api/vision/settings", headers=h).json()
    assert defaults["mode"] == "patrol" and defaults["frame_source"] == "auto"
    assert defaults["rates"]["inspection"] == {"intruder": 3, "maintenance": 1.5}

    body = {**defaults, "mode": "inspection", "rates": {"inspection": {"intruder": 4}}}
    saved = app_client.put("/api/vision/settings", headers=h, json=body).json()
    assert saved["rates"]["inspection"] == {"intruder": 4, "maintenance": 1.5}
    assert app_client.get("/api/vision/settings", headers=h).json()["mode"] == "inspection"

    bad = app_client.put("/api/vision/settings", headers=h, json={**defaults, "capture_url": "file:///etc/passwd"})
    assert bad.status_code == 422
    caps = app_client.get("/api/vision/capabilities", headers=h).json()
    assert set(caps["streams"]) == {"intruder", "maintenance"} and len(caps["modes"]) == 5


def test_server_capture_needs_a_capturable_feed(app_client):
    h, _ = signup(app_client)
    settings = app_client.get("/api/vision/settings", headers=h).json()
    app_client.put("/api/vision/settings", headers=h, json={**settings, "frame_source": "server"})
    res = app_client.post("/api/vision/session", headers=h)
    assert res.status_code == 400 and "can't capture" in res.json()["detail"]


def test_browser_frames_produce_detections_alerts_and_issues(app_client):
    h, token = signup(app_client)
    settings = app_client.get("/api/vision/settings", headers=h).json()
    app_client.put("/api/vision/settings", headers=h, json={**settings, "mode": "inspection"})
    app_client.post("/api/vision/telemetry", headers=h, json={"lat": 37.4, "lon": -122.1, "alt_m": 40})

    started = app_client.post("/api/vision/session", headers=h)
    assert started.status_code == 201, started.text
    status = started.json()
    assert status["frame_source"] == "browser" and status["source"]["label"] == "Demo feed (browser frames)"
    assert status["workers"]["intruder"]["target_fps"] == 3

    with app_client.websocket_connect("/api/vision/live") as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "status"
        for i in range(25):
            ws.send_bytes(frame_message(media_time=i * 0.1))
            time.sleep(0.05)
        events = collect(ws, lambda evs: bool(
            first(evs, type="alert", stream="intruder") and first(evs, type="alert", stream="maintenance")
            and first(evs, type="stats")
        ))

    det = first(events, type="detections", stream="intruder")
    assert det["items"][0]["label"] == "person" and det["items"][0]["category"] == "security"
    assert det["position"]["lat"] == 37.4 and det["media_time"] is not None
    alert = first(events, type="alert", stream="intruder")
    assert alert["issue_id"] and alert["title"] == "Person detected"
    assert first(events, type="stats")["frames_in"] >= 1

    issues = app_client.get("/api/issues", headers=h).json()
    by_category = {i["category"]: i for i in issues}
    assert by_category["security"]["source"] == "ground" and by_category["security"]["severity"] == "high"
    assert by_category["security"]["location"] == "37.400000, -122.100000"
    assert len(by_category["security"]["images"]) == 1
    assert by_category["maintenance"]["title"] == "Corrosion detected"

    # Inference runs on a subset of frames, never more than the target rate allows.
    assert len(app_client.detectors["intruder"].frames) < 25

    assert app_client.delete("/api/vision/session", headers=h).status_code == 204
    assert app_client.get("/api/vision/session", headers=h).json() == {"running": False}


def test_mode_switch_turns_detectors_off_live(app_client):
    h, _ = signup(app_client)
    app_client.post("/api/vision/session", headers=h)
    settings = app_client.get("/api/vision/settings", headers=h).json()
    app_client.put("/api/vision/settings", headers=h, json={**settings, "mode": "takeoff_landing"})
    status = app_client.get("/api/vision/session", headers=h).json()
    assert status["mode"] == "takeoff_landing" and status["push_fps"] == 0
    assert status["workers"]["intruder"]["target_fps"] == 0

    app_client.put("/api/vision/settings", headers=h, json={**settings, "follow_telemetry": True})
    app_client.post("/api/vision/telemetry", headers=h, json={"flight_mode": "inspection"})
    assert app_client.get("/api/vision/session", headers=h).json()["mode"] == "inspection"


def test_live_socket_requires_auth_and_sessions_are_per_account(app_client):
    alice, _ = signup(app_client, "alice")
    _, bob_token = signup(app_client, "bob")
    app_client.post("/api/vision/session", headers=alice)

    with app_client.websocket_connect("/api/vision/live") as ws:
        ws.send_json({"type": "auth", "token": "nope"})
        assert ws.receive_json()["type"] == "error"

    with app_client.websocket_connect("/api/vision/live") as ws:
        ws.send_json({"type": "auth", "token": bob_token})
        assert ws.receive_json() == {"type": "status", "session": {"running": False}}
