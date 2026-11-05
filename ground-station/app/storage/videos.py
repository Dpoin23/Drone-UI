"""Test-video library: operator uploads and videos imported from links (YouTube and other sites).

Files live under ``videos_dir/<user_id>/`` so a ground-side detector can read them straight
from disk; the browser plays them through ``/api/videos/{id}/file``.
"""

import re
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .db import connect, utcnow
from .issues import safe_path

_CHUNK = 1024 * 1024


class InvalidVideo(ValueError):
    pass


class VideoTooLarge(ValueError):
    pass


def sniff_video(head: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's magic bytes, not its claimed type."""
    if head[4:8] == b"ftyp":
        return ("video/quicktime", "mov") if head[8:12] == b"qt  " else ("video/mp4", "mp4")
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return ("video/webm", "webm") if b"webm" in head[:64] else ("video/x-matroska", "mkv")
    if head.startswith(b"OggS"):
        return "video/ogg", "ogv"
    raise InvalidVideo("Only MP4, MOV, WebM, MKV, and Ogg videos can be played in the browser")


def video_path(videos_dir: Path, rel_path: str) -> Path:
    return safe_path(videos_dir, rel_path)


def delete_video_files(videos_dir: Path, rel_path: str) -> None:
    """Delete a video and any partial download that shares its stem."""
    target = video_path(videos_dir, rel_path)
    stem = target.name.split(".", 1)[0]
    for leftover in target.parent.glob(f"{stem}.*"):
        leftover.unlink(missing_ok=True)


def save_upload(
    conn: sqlite3.Connection,
    videos_dir: Path,
    *,
    user_id: int,
    src: BinaryIO,
    filename: str,
    max_bytes: int,
) -> int:
    head = src.read(64)
    content_type, ext = sniff_video(head)
    rel_path = f"{user_id}/{uuid.uuid4().hex}.{ext}"
    dest = video_path(videos_dir, rel_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    size = len(head)
    try:
        with dest.open("wb") as out:
            out.write(head)
            while chunk := src.read(_CHUNK):
                size += len(chunk)
                if size > max_bytes:
                    raise VideoTooLarge(f"Videos can be at most {max_bytes // (1024 * 1024)} MB")
                out.write(chunk)
        title = Path(filename or f"video.{ext}").stem[:200] or "Uploaded video"
        cur = conn.execute(
            """
            INSERT INTO videos (user_id, title, source, status, content_type, size_bytes, path, created_at)
            VALUES (?, ?, 'upload', 'ready', ?, ?, ?, ?)
            """,
            (user_id, title, content_type, size, rel_path, utcnow()),
        )
        conn.commit()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return cur.lastrowid


# ---- Importing from a link -------------------------------------------------------------------


@dataclass
class RemoteInfo:
    title: str
    duration_s: float | None
    fps: float | None


ProgressFn = Callable[[float], None]


def _download_with_ytdlp(
    url: str,
    dest_stem: Path,
    *,
    max_bytes: int,
    on_info: Callable[[RemoteInfo], None],
    on_progress: ProgressFn,
    cancelled: threading.Event,
) -> Path:
    import yt_dlp

    if shutil.which("ffmpeg"):
        fmt = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b"
    else:
        # Without ffmpeg, separate video and audio streams can't be merged. Detection only needs
        # pixels, so prefer an HD video-only H.264 stream over a low-res file that has audio.
        fmt = "bv[height<=1080][ext=mp4][vcodec^=avc1]/b[height<=1080][ext=mp4]/b[ext=mp4]/b"

    def hook(d: dict) -> None:
        if cancelled.is_set():
            raise yt_dlp.utils.DownloadCancelled("Cancelled")
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if d.get("status") == "downloading" and total:
            on_progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "format": fmt,
        "merge_output_format": "mp4",
        "max_filesize": max_bytes,
        "outtmpl": {"default": f"{dest_stem}.%(ext)s"},
        "progress_hooks": [hook],
        "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            raise InvalidVideo("That link is a playlist. Paste a link to a single video.")
        if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            raise InvalidVideo("Live streams aren't supported yet. Use a recorded video.")
        size = info.get("filesize") or info.get("filesize_approx")
        if size and size > max_bytes:
            raise VideoTooLarge(f"Videos can be at most {max_bytes // (1024 * 1024)} MB")
        on_info(RemoteInfo(
            title=str(info.get("title") or url)[:200],
            duration_s=info.get("duration"),
            fps=info.get("fps"),
        ))
        result = ydl.process_ie_result(info, download=True)

    downloads = result.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads and downloads[0].get("filepath") else None
    if path is None or not path.is_file():
        raise InvalidVideo("The video could not be downloaded")
    return path


# Tests replace this to avoid the network.
download_remote = _download_with_ytdlp

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-import")
_cancel_events: dict[int, threading.Event] = {}
_cancel_lock = threading.Lock()


def start_import(conn: sqlite3.Connection, db_path: Path, videos_dir: Path, *, user_id: int, url: str,
                 max_bytes: int) -> int:
    stem = f"{user_id}/{uuid.uuid4().hex}"
    video_path(videos_dir, stem).parent.mkdir(parents=True, exist_ok=True)
    cur = conn.execute(
        """
        INSERT INTO videos (user_id, title, source, source_url, status, progress, path, created_at)
        VALUES (?, ?, 'url', ?, 'downloading', 0, ?, ?)
        """,
        (user_id, url[:200], url, stem, utcnow()),
    )
    conn.commit()
    video_id = cur.lastrowid
    cancelled = threading.Event()
    with _cancel_lock:
        _cancel_events[video_id] = cancelled
    _executor.submit(_run_import, db_path, videos_dir, video_id, url, stem, max_bytes, cancelled)
    return video_id


def cancel_import(video_id: int) -> None:
    with _cancel_lock:
        event = _cancel_events.get(video_id)
    if event:
        event.set()


def _run_import(db_path: Path, videos_dir: Path, video_id: int, url: str, stem: str, max_bytes: int,
                cancelled: threading.Event) -> None:
    conn = connect(db_path)
    last_write = 0.0

    def update(**fields) -> None:
        if cancelled.is_set():
            return
        assignments = ", ".join(f"{col} = ?" for col in fields)
        conn.execute(f"UPDATE videos SET {assignments} WHERE id = ?", (*fields.values(), video_id))
        conn.commit()

    def on_info(info: RemoteInfo) -> None:
        update(title=info.title, duration_s=info.duration_s, fps=info.fps)

    def on_progress(fraction: float) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write >= 0.5:
            last_write = now
            update(progress=round(fraction, 3))

    try:
        path = download_remote(
            url, video_path(videos_dir, stem),
            max_bytes=max_bytes, on_info=on_info, on_progress=on_progress, cancelled=cancelled,
        )
        with path.open("rb") as f:
            content_type, _ = sniff_video(f.read(64))
        rel_path = f"{stem.rsplit('/', 1)[0]}/{path.name}"
        update(status="ready", progress=1.0, content_type=content_type,
               size_bytes=path.stat().st_size, path=rel_path)
    except Exception as exc:
        update(status="error", progress=None, error=_describe_error(exc))
        delete_video_files(videos_dir, stem)
    finally:
        if cancelled.is_set():
            delete_video_files(videos_dir, stem)
        with _cancel_lock:
            _cancel_events.pop(video_id, None)
        conn.close()


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, InvalidVideo | VideoTooLarge):
        return str(exc)
    message = str(exc).removeprefix("ERROR: ").strip()
    message = re.sub(r"^\[[^\]]+\] [^:\s]+: ", "", message)
    message = re.sub(r" \(caused by .*\)$", "", message)
    if not message:
        return "The video could not be downloaded"
    if "Unsupported URL" in message:
        return "No video found at that link"
    if "is not a valid URL" in message:
        return "That doesn't look like a video link"
    return message[:300]


def fail_interrupted_imports(conn: sqlite3.Connection, videos_dir: Path) -> None:
    """Downloads don't survive a server restart; mark them failed and clear partial files."""
    for row in conn.execute("SELECT path FROM videos WHERE status = 'downloading'").fetchall():
        delete_video_files(videos_dir, row["path"])
    conn.execute(
        "UPDATE videos SET status = 'error', progress = NULL, error = ? WHERE status = 'downloading'",
        ("Interrupted by a ground-station restart. Delete it and import again.",),
    )
    conn.commit()
