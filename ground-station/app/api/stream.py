import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user, get_db
from ..storage.db import utcnow
from .vision import reapply_session

router = APIRouter(prefix="/api/stream-settings", tags=["stream"])


class StreamSettings(BaseModel):
    transport: Literal["demo", "webrtc", "mjpeg", "video"] = "demo"
    # For the "video" transport this is the id of a video in the account's test-video library.
    url: str = Field(default="", max_length=500)


@router.get("", response_model=StreamSettings)
def get_stream_settings(
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = conn.execute(
        "SELECT transport, url FROM stream_settings WHERE user_id = ?", (user.id,)
    ).fetchone()
    return StreamSettings(**dict(row)) if row else StreamSettings()


@router.put("", response_model=StreamSettings)
def put_stream_settings(
    body: StreamSettings,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    body.url = body.url.strip()
    if body.transport == "video":
        owned = body.url.isdigit() and conn.execute(
            "SELECT 1 FROM videos WHERE id = ? AND user_id = ?", (int(body.url), user.id)
        ).fetchone()
        if not owned:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick a video from your library")
    conn.execute(
        """
        INSERT INTO stream_settings (user_id, transport, url, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            transport = excluded.transport, url = excluded.url, updated_at = excluded.updated_at
        """,
        (user.id, body.transport, body.url, utcnow()),
    )
    conn.commit()
    reapply_session(request.app.state.vision, conn, request.app.state.settings, user.id)
    return body
