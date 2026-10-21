import sqlite3
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user, get_db
from ..storage.db import utcnow
from ..storage.issues import (
    InvalidImage,
    delete_image_file,
    delete_issue_files,
    insert_issue,
    save_image,
)

router = APIRouter(prefix="/api/issues", tags=["issues"])

Category = Literal["security", "maintenance"]
Severity = Literal["low", "medium", "high", "critical"]
Status = Literal["open", "acknowledged", "resolved", "false_positive"]
CLOSED_STATUSES = ("resolved", "false_positive")


class IssueCreate(BaseModel):
    category: Category
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    severity: Severity = "medium"
    location: str = Field(default="", max_length=200)


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity | None = None
    status: Status | None = None
    location: str | None = Field(default=None, max_length=200)


class IssueImage(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    created_at: str


class Issue(BaseModel):
    id: int
    category: Category
    title: str
    description: str
    severity: Severity
    status: Status
    location: str
    source: str
    created_at: str
    updated_at: str
    resolved_at: str | None
    images: list[IssueImage]


def _get_owned(conn: sqlite3.Connection, user_id: int, issue_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM issues WHERE id = ? AND user_id = ?", (issue_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")
    return row


def _image(row: sqlite3.Row) -> IssueImage:
    return IssueImage(**{k: row[k] for k in IssueImage.model_fields})


def _to_issue(row: sqlite3.Row, images: list[IssueImage]) -> Issue:
    fields = {k: row[k] for k in Issue.model_fields if k != "images"}
    return Issue(**fields, images=images)


def _load_issue(conn: sqlite3.Connection, user_id: int, issue_id: int) -> Issue:
    row = _get_owned(conn, user_id, issue_id)
    images = conn.execute(
        "SELECT * FROM issue_images WHERE issue_id = ? ORDER BY id", (issue_id,)
    ).fetchall()
    return _to_issue(row, [_image(r) for r in images])


@router.get("", response_model=list[Issue])
def list_issues(
    category: Category | None = None,
    status_filter: Status | None = Query(default=None, alias="status"),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    where = "i.user_id = ?"
    params: list = [user.id]
    if category:
        where += " AND i.category = ?"
        params.append(category)
    if status_filter:
        where += " AND i.status = ?"
        params.append(status_filter)

    rows = conn.execute(
        f"SELECT i.* FROM issues i WHERE {where} ORDER BY i.created_at DESC, i.id DESC", params
    ).fetchall()
    images: dict[int, list[IssueImage]] = defaultdict(list)
    for r in conn.execute(
        f"SELECT im.* FROM issue_images im JOIN issues i ON i.id = im.issue_id WHERE {where} ORDER BY im.id",
        params,
    ):
        images[r["issue_id"]].append(_image(r))
    return [_to_issue(r, images[r["id"]]) for r in rows]


@router.post("", response_model=Issue, status_code=status.HTTP_201_CREATED)
def create_issue(
    body: IssueCreate,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    issue_id = insert_issue(conn, user_id=user.id, **body.model_dump())
    return _load_issue(conn, user.id, issue_id)


@router.patch("/{issue_id}", response_model=Issue)
def update_issue(
    issue_id: int,
    body: IssueUpdate,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    existing = _get_owned(conn, user.id, issue_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return _load_issue(conn, user.id, issue_id)

    now = utcnow()
    if "status" in changes:
        closing = changes["status"] in CLOSED_STATUSES
        was_closed = existing["status"] in CLOSED_STATUSES
        if closing and not was_closed:
            changes["resolved_at"] = now
        elif not closing:
            changes["resolved_at"] = None
    changes["updated_at"] = now

    assignments = ", ".join(f"{col} = ?" for col in changes)
    conn.execute(
        f"UPDATE issues SET {assignments} WHERE id = ? AND user_id = ?",
        (*changes.values(), issue_id, user.id),
    )
    conn.commit()
    return _load_issue(conn, user.id, issue_id)


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: int,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    _get_owned(conn, user.id, issue_id)
    conn.execute("DELETE FROM issues WHERE id = ? AND user_id = ?", (issue_id, user.id))
    conn.commit()
    delete_issue_files(request.app.state.settings.uploads_dir, user.id, issue_id)


@router.post("/{issue_id}/images", response_model=Issue, status_code=status.HTTP_201_CREATED)
def upload_images(
    issue_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    settings = request.app.state.settings
    _get_owned(conn, user.id, issue_id)

    (existing,) = conn.execute(
        "SELECT COUNT(*) FROM issue_images WHERE issue_id = ?", (issue_id,)
    ).fetchone()
    if existing + len(files) > settings.max_images_per_issue:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"An issue can have at most {settings.max_images_per_issue} images",
        )

    payloads: list[tuple[str, bytes]] = []
    for f in files:
        data = f.file.read(settings.max_image_bytes + 1)
        if len(data) > settings.max_image_bytes:
            limit_mb = settings.max_image_bytes // (1024 * 1024)
            raise HTTPException(
                413, f"{f.filename} is larger than {limit_mb} MB"
            )
        payloads.append((f.filename or "", data))

    for filename, data in payloads:
        try:
            save_image(
                conn, settings.uploads_dir,
                user_id=user.id, issue_id=issue_id, data=data, filename=filename,
            )
        except InvalidImage as exc:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{filename or 'File'}: {exc}"
            )
    return _load_issue(conn, user.id, issue_id)


def _get_owned_image(conn: sqlite3.Connection, user_id: int, issue_id: int, image_id: int) -> sqlite3.Row:
    _get_owned(conn, user_id, issue_id)
    row = conn.execute(
        "SELECT * FROM issue_images WHERE id = ? AND issue_id = ?", (image_id, issue_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return row


@router.get("/{issue_id}/images/{image_id}")
def get_image(
    issue_id: int,
    image_id: int,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned_image(conn, user.id, issue_id, image_id)
    path = request.app.state.settings.uploads_dir / row["path"]
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file missing")
    return FileResponse(
        path,
        media_type=row["content_type"],
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"},
    )


@router.delete("/{issue_id}/images/{image_id}", response_model=Issue)
def delete_image(
    issue_id: int,
    image_id: int,
    request: Request,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    row = _get_owned_image(conn, user.id, issue_id, image_id)
    conn.execute("DELETE FROM issue_images WHERE id = ?", (image_id,))
    conn.execute("UPDATE issues SET updated_at = ? WHERE id = ?", (utcnow(), issue_id))
    conn.commit()
    delete_image_file(request.app.state.settings.uploads_dir, row["path"])
    return _load_issue(conn, user.id, issue_id)
