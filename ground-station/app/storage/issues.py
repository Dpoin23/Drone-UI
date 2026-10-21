"""Issue persistence shared by the REST API and (later) the automated detection pipeline.

Manual entries come from operators through the API with ``source="manual"``. Automated
entries from the drone link or ground-side inference should call the same functions with
their own ``source`` (for example ``"onboard"`` or ``"ground"``) and attach snapshots
with :func:`save_image`.
"""

import shutil
import sqlite3
import uuid
from pathlib import Path

from .db import utcnow

_IMAGE_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"\xff\xd8\xff", 0, "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "png"),
    (b"GIF87a", 0, "image/gif", "gif"),
    (b"GIF89a", 0, "image/gif", "gif"),
    (b"WEBP", 8, "image/webp", "webp"),
]


class InvalidImage(ValueError):
    pass


def sniff_image(data: bytes) -> tuple[str, str]:
    """Return (content_type, extension) from the file's magic bytes, not its claimed type."""
    for signature, offset, content_type, ext in _IMAGE_SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            if content_type == "image/webp" and not data.startswith(b"RIFF"):
                continue
            return content_type, ext
    raise InvalidImage("Only JPEG, PNG, GIF, and WebP images are supported")


def insert_issue(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    category: str,
    title: str,
    description: str = "",
    severity: str = "medium",
    location: str = "",
    source: str = "manual",
) -> int:
    now = utcnow()
    cur = conn.execute(
        """
        INSERT INTO issues (user_id, category, title, description, severity, location,
                            source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, category, title.strip(), description, severity, location.strip(), source, now, now),
    )
    conn.commit()
    return cur.lastrowid


def _issue_dir(uploads_dir: Path, user_id: int, issue_id: int) -> Path:
    return uploads_dir / str(user_id) / str(issue_id)


def save_image(
    conn: sqlite3.Connection,
    uploads_dir: Path,
    *,
    user_id: int,
    issue_id: int,
    data: bytes,
    filename: str,
) -> int:
    content_type, ext = sniff_image(data)
    rel_path = Path(str(user_id)) / str(issue_id) / f"{uuid.uuid4().hex}.{ext}"
    dest = uploads_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        cur = conn.execute(
            """
            INSERT INTO issue_images (issue_id, filename, content_type, size_bytes, path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (issue_id, Path(filename or f"image.{ext}").name[:200], content_type, len(data),
             rel_path.as_posix(), utcnow()),
        )
        conn.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (utcnow(), issue_id))
        conn.commit()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return cur.lastrowid


def delete_image_file(uploads_dir: Path, rel_path: str) -> None:
    (uploads_dir / rel_path).unlink(missing_ok=True)


def delete_issue_files(uploads_dir: Path, user_id: int, issue_id: int) -> None:
    shutil.rmtree(_issue_dir(uploads_dir, user_id, issue_id), ignore_errors=True)
