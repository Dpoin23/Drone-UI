import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user, get_db
from ..storage.db import utcnow

router = APIRouter(prefix="/api/stream-settings", tags=["stream"])


class StreamSettings(BaseModel):
    transport: Literal["demo", "webrtc", "mjpeg"] = "demo"
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
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    conn.execute(
        """
        INSERT INTO stream_settings (user_id, transport, url, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id) DO UPDATE SET
            transport = excluded.transport, url = excluded.url, updated_at = excluded.updated_at
        """,
        (user.id, body.transport, body.url.strip(), utcnow()),
    )
    conn.commit()
    return body
