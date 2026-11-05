import asyncio
import contextlib
import json
import sqlite3
import time
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field, field_validator

from ..auth import CurrentUser, current_user, get_db, user_for_token
from ..config import Settings
from ..storage.db import connect, utcnow
from ..storage.videos import video_path
from ..vision.detectors import capabilities
from ..vision.modes import DEFAULT_RATES, MAX_RATE, MODE_LABELS, FlightMode, Stream, merged_rates
from ..vision.session import SessionConfig, TooManySessions, VisionManager
from ..vision.sources import (
    CaptureTarget,
    InvalidFrame,
    capture_backends,
    derive_capture_url,
    parse_browser_frame,
    target_label,
    valid_capture_url,
)
from ..vision.telemetry import Telemetry

router = APIRouter(prefix="/api/vision", tags=["vision"])

Rate = Annotated[float, Field(ge=0, le=MAX_RATE)]
TOKEN_RECHECK_S = 60


class VisionSettings(BaseModel):
    mode: FlightMode = "patrol"
    frame_source: Literal["auto", "server", "browser"] = "auto"
    # Overrides where the ground station reads the stream (e.g. an RTSP URL); empty derives it.
    capture_url: str = Field(default="", max_length=500)
    rates: dict[FlightMode, dict[Stream, Rate]] = Field(default_factory=lambda: merged_rates(None))
    auto_issues: bool = True
    follow_telemetry: bool = True

    @field_validator("capture_url")
    @classmethod
    def _check_capture_url(cls, v: str) -> str:
        v = v.strip()
        if v and not valid_capture_url(v):
            raise ValueError("Use an rtsp://, http(s)://, udp://, srt://, or rtmp:// stream URL")
        return v

    @field_validator("rates", mode="after")
    @classmethod
    def _fill_rates(cls, v: dict) -> dict:
        return merged_rates(v)


class TelemetryIn(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    alt_m: float | None = None
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    flight_mode: str | None = Field(default=None, max_length=50)
    ts: float | None = Field(default=None, description="Fix time, Unix epoch seconds. Defaults to now.")


def _manager(request: Request) -> VisionManager:
    return request.app.state.vision


def load_vision_settings(conn: sqlite3.Connection, user_id: int) -> VisionSettings:
    row = conn.execute("SELECT settings_json FROM vision_settings WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return VisionSettings()
    try:
        return VisionSettings.model_validate_json(row["settings_json"])
    except ValueError:
        return VisionSettings()


def build_session_config(conn: sqlite3.Connection, settings: Settings, user_id: int,
                         vs: VisionSettings) -> SessionConfig:
    """Work out where frames come from, given the account's feed and vision settings."""
    row = conn.execute("SELECT transport, url FROM stream_settings WHERE user_id = ?", (user_id,)).fetchone()
    transport, url = (row["transport"], row["url"]) if row else ("demo", "")
    source = vs.frame_source
    if source == "auto":
        source = "server" if transport in ("webrtc", "mjpeg") or vs.capture_url else "browser"

    video = None
    if transport == "video" and url.isdigit():
        video = conn.execute(
            "SELECT * FROM videos WHERE id = ? AND user_id = ? AND status = 'ready'", (int(url), user_id)
        ).fetchone()
    video_title = video["title"] if video else None

    capture = None
    if source == "server":
        if settings.capture_pipeline:
            capture = CaptureTarget("pipeline", settings.capture_pipeline, "GStreamer pipeline")
        elif vs.capture_url:
            capture = CaptureTarget("stream", vs.capture_url, target_label(vs.capture_url))
        elif transport == "video":
            if video is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick a ready test video in stream settings first")
            path = video_path(settings.videos_dir, video["path"])
            capture = CaptureTarget("file", str(path), f'Test video "{video_title}"')
        else:
            derived = derive_capture_url(transport, url)
            if derived is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "The ground station can't capture this feed itself. Use browser frames, or set a capture URL.",
                )
            capture = CaptureTarget("stream", derived, target_label(derived))
        source_label = capture.label
    else:
        source_label = {
            "demo": "Demo feed",
            "video": f'Test video "{video_title}"' if video_title else "Test video",
            "webrtc": "WebRTC feed",
            "mjpeg": "MJPEG feed",
        }.get(transport, transport) + " (browser frames)"

    return SessionConfig(
        mode=vs.mode,
        rates=vs.rates,
        auto_issues=vs.auto_issues,
        follow_telemetry=vs.follow_telemetry,
        frame_source=source,
        transport=transport,
        source_label=source_label,
        capture=capture,
        video_title=video_title,
    )


def reapply_session(manager: VisionManager, conn: sqlite3.Connection, settings: Settings, user_id: int) -> None:
    """Called after the account's feed or vision settings change, so a running session follows them."""
    if manager.get(user_id) is None:
        return
    try:
        config = build_session_config(conn, settings, user_id, load_vision_settings(conn, user_id))
    except HTTPException:
        manager.stop(user_id)
        return
    manager.apply(user_id, config)


@router.get("/capabilities")
def get_capabilities(request: Request, user: CurrentUser = Depends(current_user)):
    settings = request.app.state.settings
    return {
        **capabilities(settings),
        "capture": capture_backends(),
        "modes": [{"id": m, "label": label} for m, label in MODE_LABELS.items()],
        "default_rates": DEFAULT_RATES,
        "max_rate": MAX_RATE,
        "imgsz": settings.vision_imgsz,
    }


@router.get("/settings", response_model=VisionSettings)
def get_settings(user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    return load_vision_settings(conn, user.id)


@router.put("/settings", response_model=VisionSettings)
def put_settings(
    body: VisionSettings,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    conn.execute(
        """
        INSERT INTO vision_settings (user_id, settings_json, updated_at) VALUES (?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            settings_json = excluded.settings_json, updated_at = excluded.updated_at
        """,
        (user.id, body.model_dump_json(), utcnow()),
    )
    conn.commit()
    reapply_session(_manager(request), conn, request.app.state.settings, user.id)
    return body


@router.get("/session")
def get_session(request: Request, user: CurrentUser = Depends(current_user)):
    session = _manager(request).get(user.id)
    return session.status() if session else {"running": False}


@router.post("/session", status_code=status.HTTP_201_CREATED)
def start_session(
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    settings = request.app.state.settings
    config = build_session_config(conn, settings, user.id, load_vision_settings(conn, user.id))
    try:
        session = _manager(request).start(user.id, config)
    except TooManySessions as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return session.status()


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def stop_session(request: Request, user: CurrentUser = Depends(current_user)):
    _manager(request).stop(user.id)


@router.post("/telemetry", status_code=status.HTTP_204_NO_CONTENT)
def post_telemetry(body: TelemetryIn, request: Request, user: CurrentUser = Depends(current_user)):
    """Latest drone position and flight mode, from the drone link or a simulator."""
    now = time.time()
    ts = body.ts if body.ts is not None and abs(body.ts - now) < 3600 else now
    _manager(request).update_telemetry(user.id, Telemetry(
        ts=ts, lat=body.lat, lon=body.lon, alt_m=body.alt_m, heading_deg=body.heading_deg,
        flight_mode=body.flight_mode,
    ))


def _token_user(settings: Settings, token: object) -> CurrentUser | None:
    if not isinstance(token, str) or not token:
        return None
    conn = connect(settings.db_path)
    try:
        return user_for_token(conn, token)
    finally:
        conn.close()


@router.websocket("/live")
async def live(ws: WebSocket):
    """Detections, alerts, status, and stats to the UI; JPEG frames from the UI in browser mode.

    The first message must be ``{"type": "auth", "token": "..."}``, since browsers can't set an
    Authorization header on a WebSocket.
    """
    await ws.accept()
    settings: Settings = ws.app.state.settings
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
    except (TimeoutError, ValueError, WebSocketDisconnect, KeyError):
        await ws.close(code=4401)
        return
    token = hello.get("token") if isinstance(hello, dict) else None
    user = _token_user(settings, token)
    if user is None:
        await ws.send_json({"type": "error", "message": "Session expired, please sign in again"})
        await ws.close(code=4401)
        return

    manager: VisionManager = ws.app.state.vision
    hub = manager.hub(user.id)
    sub = hub.subscribe(asyncio.get_running_loop())
    producer = uuid.uuid4().hex
    session = manager.get(user.id)
    await ws.send_json({"type": "status", "session": session.status() if session else {"running": False}})

    async def pump() -> None:
        while True:
            event = await sub.queue.get()
            await ws.send_text(json.dumps(event))

    async def heartbeat() -> None:
        ticks = 0
        while True:
            await asyncio.sleep(1)
            ticks += 1
            if ticks % TOKEN_RECHECK_S == 0 and _token_user(settings, token) is None:
                await ws.close(code=4401)
                return
            current = manager.get(user.id)
            if current:
                sub.offer(current.stats())

    tasks = [asyncio.create_task(pump()), asyncio.create_task(heartbeat())]
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is None:
                continue
            current = manager.get(user.id)
            if current is None:
                continue
            try:
                current.push_browser_frame(producer, parse_browser_frame(data))
            except InvalidFrame:
                continue
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        hub.unsubscribe(sub)
        current = manager.get(user.id)
        if current:
            current.release_producer(producer)
