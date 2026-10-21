import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth import (
    CurrentUser,
    current_user,
    get_db,
    hash_password,
    issue_token,
    revoke_token,
    verify_password,
)
from ..storage.db import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (body.username, hash_password(body.password), utcnow()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken")
    conn.commit()
    user_id = cur.lastrowid
    token = issue_token(conn, user_id, request.app.state.settings.token_ttl_hours)
    return AuthResponse(token=token, user=UserOut(id=user_id, username=body.username))


@router.post("/login", response_model=AuthResponse)
def login(body: Credentials, request: Request, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?", (body.username,)
    ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    token = issue_token(conn, row["id"], request.app.state.settings.token_ttl_hours)
    return AuthResponse(token=token, user=UserOut(id=row["id"], username=row["username"]))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser = Depends(current_user), conn: sqlite3.Connection = Depends(get_db)):
    revoke_token(conn, user.token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(current_user)):
    return UserOut(id=user.id, username=user.username)
