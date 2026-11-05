import hashlib
import hmac
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user, get_db
from ..storage.videos import (
    InvalidVideo,
    VideoTooLarge,
    cancel_import,
    delete_video_files,
    save_upload,
    start_import,
    video_path,
)
from .vision import reapply_session

router = APIRouter(prefix="/api/videos", tags=["videos"])

PLAYBACK_TTL_SECONDS = 24 * 3600


class Video(BaseModel):
    id: int
    title: str
    source: Literal["upload", "url"]
    source_url: str
    status: Literal["downloading", "ready", "error"]
    progress: float | None
    error: str | None
    content_type: str
    size_bytes: int
    duration_s: float | None
    fps: float | None
    created_at: str


class VideoImport(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class Playback(BaseModel):
    url: str
    expires_at: int


def _to_video(row: sqlite3.Row) -> Video:
    return Video(**{k: row[k] for k in Video.model_fields})


def _get_owned(conn: sqlite3.Connection, user_id: int, video_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM videos WHERE id = ? AND user_id = ?", (video_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return row


def _signature(secret: bytes, video_id: int, expires_at: int) -> str:
    return hmac.new(secret, f"video:{video_id}:{expires_at}".encode(), hashlib.sha256).hexdigest()


@router.get("", response_model=list[Video])
def list_videos(user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM videos WHERE user_id = ? ORDER BY created_at DESC, id DESC", (user.id,)
    ).fetchall()
    return [_to_video(r) for r in rows]


@router.get("/{video_id}", response_model=Video)
def get_video(
    video_id: int, user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)
):
    return _to_video(_get_owned(conn, user.id, video_id))


@router.post("/upload", response_model=Video, status_code=status.HTTP_201_CREATED)
def upload_video(
    request: Request,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    settings = request.app.state.settings
    try:
        video_id = save_upload(
            conn, settings.videos_dir,
            user_id=user.id, src=file.file, filename=file.filename or "", max_bytes=settings.max_video_bytes,
        )
    except InvalidVideo as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    except VideoTooLarge as exc:
        raise HTTPException(413, str(exc))
    return _to_video(_get_owned(conn, user.id, video_id))


@router.post("/import", response_model=Video, status_code=status.HTTP_202_ACCEPTED)
def import_video(
    body: VideoImport,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a full http:// or https:// link")
    settings = request.app.state.settings
    video_id = start_import(
        conn, settings.db_path, settings.videos_dir, user_id=user.id, url=url, max_bytes=settings.max_video_bytes
    )
    return _to_video(_get_owned(conn, user.id, video_id))


@router.get("/{video_id}/playback", response_model=Playback)
def playback_url(
    video_id: int,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    """A signed, expiring file URL, since a <video> element can't send the Authorization header."""
    row = _get_owned(conn, user.id, video_id)
    if row["status"] != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Video isn't ready yet")
    expires_at = int(time.time()) + PLAYBACK_TTL_SECONDS
    sig = _signature(request.app.state.media_secret, video_id, expires_at)
    return Playback(url=f"/api/videos/{video_id}/file?exp={expires_at}&sig={sig}", expires_at=expires_at)


@router.get("/{video_id}/file")
def video_file(
    video_id: int,
    request: Request,
    exp: int = Query(...),
    sig: str = Query(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    expected = _signature(request.app.state.media_secret, video_id, exp)
    if not hmac.compare_digest(expected, sig) or exp < time.time():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Playback link expired, reload the page")
    row = conn.execute("SELECT * FROM videos WHERE id = ? AND status = 'ready'", (video_id,)).fetchone()
    path = video_path(request.app.state.settings.videos_dir, row["path"]) if row else None
    if path is None or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return FileResponse(
        path,
        media_type=row["content_type"],
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned(conn, user.id, video_id)
    cancel_import(video_id)
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.execute(
        "UPDATE stream_settings SET url = '' WHERE user_id = ? AND transport = 'video' AND url = ?",
        (user.id, str(video_id)),
    )
    conn.commit()
    reapply_session(request.app.state.vision, conn, request.app.state.settings, user.id)
    delete_video_files(request.app.state.settings.videos_dir, row["path"])
