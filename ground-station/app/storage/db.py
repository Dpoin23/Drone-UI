import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL CHECK (category IN ('security', 'maintenance')),
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    severity    TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status      TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'acknowledged', 'resolved', 'false_positive')),
    location    TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_issues_user_category ON issues (user_id, category, created_at);

CREATE TABLE IF NOT EXISTS issue_images (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id     INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    path         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_issue_images_issue ON issue_images (issue_id, id);

CREATE TABLE IF NOT EXISTS stream_settings (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    transport  TEXT NOT NULL CHECK (transport IN ('demo', 'webrtc', 'mjpeg', 'video')),
    url        TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    source       TEXT NOT NULL CHECK (source IN ('upload', 'url')),
    source_url   TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL CHECK (status IN ('downloading', 'ready', 'error')),
    progress     REAL,
    error        TEXT,
    content_type TEXT NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    duration_s   REAL,
    fps          REAL,
    path         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_videos_user ON videos (user_id, created_at);

CREATE TABLE IF NOT EXISTS vision_settings (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings_json TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS server_secrets (
    name  TEXT PRIMARY KEY,
    value BLOB NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    # FastAPI may open and close a request's connection on different threadpool
    # threads; each connection is still only used by one request at a time.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_stream_settings(conn: sqlite3.Connection) -> None:
    """Widen the transport CHECK on databases created before the 'video' transport existed."""
    (sql,) = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'stream_settings'"
    ).fetchone()
    if "'video'" in sql:
        return
    conn.executescript(
        """
        BEGIN;
        ALTER TABLE stream_settings RENAME TO stream_settings_old;
        CREATE TABLE stream_settings (
            user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            transport  TEXT NOT NULL CHECK (transport IN ('demo', 'webrtc', 'mjpeg', 'video')),
            url        TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        INSERT INTO stream_settings SELECT user_id, transport, url, updated_at FROM stream_settings_old;
        DROP TABLE stream_settings_old;
        COMMIT;
        """
    )


def server_secret(conn: sqlite3.Connection, name: str) -> bytes:
    """Return a random per-install secret, creating it on first use."""
    conn.execute(
        "INSERT OR IGNORE INTO server_secrets (name, value) VALUES (?, ?)", (name, secrets.token_bytes(32))
    )
    conn.commit()
    (value,) = conn.execute("SELECT value FROM server_secrets WHERE name = ?", (name,)).fetchone()
    return value


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate_stream_settings(conn)
        conn.commit()
    finally:
        conn.close()
