import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth import CurrentUser, current_user, get_db
from ..storage.db import utcnow

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


def _get_owned(conn: sqlite3.Connection, user_id: int, issue_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM issues WHERE id = ? AND user_id = ?", (issue_id, user_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Issue not found")
    return row


def _to_issue(row: sqlite3.Row) -> Issue:
    return Issue(**{k: row[k] for k in Issue.model_fields})


@router.get("", response_model=list[Issue])
def list_issues(
    category: Category | None = None,
    status_filter: Status | None = Query(default=None, alias="status"),
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    sql = "SELECT * FROM issues WHERE user_id = ?"
    params: list = [user.id]
    if category:
        sql += " AND category = ?"
        params.append(category)
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY created_at DESC, id DESC"
    return [_to_issue(r) for r in conn.execute(sql, params).fetchall()]


@router.post("", response_model=Issue, status_code=status.HTTP_201_CREATED)
def create_issue(
    body: IssueCreate,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    now = utcnow()
    cur = conn.execute(
        """
        INSERT INTO issues (user_id, category, title, description, severity, location,
                            created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user.id, body.category, body.title.strip(), body.description, body.severity,
         body.location.strip(), now, now),
    )
    conn.commit()
    return _to_issue(_get_owned(conn, user.id, cur.lastrowid))


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
        return _to_issue(existing)

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
    return _to_issue(_get_owned(conn, user.id, issue_id))


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: int,
    user: CurrentUser = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_db),
):
    _get_owned(conn, user.id, issue_id)
    conn.execute("DELETE FROM issues WHERE id = ? AND user_id = ?", (issue_id, user.id))
    conn.commit()
