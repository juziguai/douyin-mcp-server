"""Download history tracking with SQLite."""

import os
import sqlite3
import time
from contextlib import contextmanager

_DB_PATH = os.path.join(os.path.dirname(__file__), "videos", "history.db")


@contextmanager
def _conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    """Create the history table if it doesn't exist."""
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                video_title TEXT,
                nickname TEXT,
                share_url TEXT,
                file_path TEXT,
                file_type TEXT DEFAULT 'video',
                size_mb REAL,
                ratio TEXT,
                downloaded_at REAL NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_video_id ON downloads(video_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_downloaded_at ON downloads(downloaded_at)")


def record_download(video_id: str, video_title: str, nickname: str, share_url: str,
                    file_path: str, file_type: str = "video", size_mb: float = 0.0,
                    ratio: str = "") -> int:
    """Record a download in history. Returns the row ID."""
    init_db()
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO downloads (video_id, video_title, nickname, share_url, file_path, file_type, size_mb, ratio, downloaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (video_id, video_title, nickname, share_url, file_path, file_type, size_mb, ratio, time.time()),
        )
        return cur.lastrowid


def is_downloaded(video_id: str, file_type: str = "video") -> dict | None:
    """Check if a video has been downloaded. Returns the record or None."""
    init_db()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM downloads WHERE video_id = ? AND file_type = ? ORDER BY downloaded_at DESC LIMIT 1",
            (video_id, file_type),
        ).fetchone()
        if row:
            return dict(row)
        return None


def list_history(limit: int = 20, file_type: str | None = None) -> list[dict]:
    """List download history, newest first."""
    init_db()
    with _conn() as c:
        if file_type:
            rows = c.execute(
                "SELECT * FROM downloads WHERE file_type = ? ORDER BY downloaded_at DESC LIMIT ?",
                (file_type, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM downloads ORDER BY downloaded_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def search_history(keyword: str, limit: int = 20) -> list[dict]:
    """Search download history by title or nickname."""
    init_db()
    pattern = f"%{keyword}%"
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM downloads WHERE video_title LIKE ? OR nickname LIKE ? ORDER BY downloaded_at DESC LIMIT ?",
            (pattern, pattern, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_record(record_id: int) -> dict:
    """Delete a single download record by ID. Returns the deleted record or None."""
    init_db()
    with _conn() as c:
        row = c.execute("SELECT * FROM downloads WHERE id = ?", (record_id,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM downloads WHERE id = ?", (record_id,))
        return dict(row)


def clear_history(file_type: str | None = None) -> int:
    """Clear download history. Returns number of deleted records."""
    init_db()
    with _conn() as c:
        if file_type:
            cur = c.execute("DELETE FROM downloads WHERE file_type = ?", (file_type,))
        else:
            cur = c.execute("DELETE FROM downloads")
        return cur.rowcount
