"""Tiny SQLite store: topic proposals, reels and settings."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY, created TEXT, title TEXT, summary TEXT, angle TEXT, why TEXT,
  status TEXT DEFAULT 'proposed');            -- proposed | approved | rejected
CREATE TABLE IF NOT EXISTS reels (
  id INTEGER PRIMARY KEY, topic_id INTEGER, folder TEXT, status TEXT,
  caption TEXT, ig_id TEXT, permalink TEXT, error TEXT, updated TEXT);
                                              -- producing | review | editing | posting | posted | dropped | failed
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


def db() -> sqlite3.Connection:
    config.DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def add_topic(t: dict) -> int:
    with db() as c:
        return c.execute("INSERT INTO topics(created,title,summary,angle,why) VALUES(?,?,?,?,?)",
                         (now(), t["title_ar"], t.get("summary_ar", ""), t.get("angle", ""), t.get("why", ""))).lastrowid


def topic(tid: int) -> dict | None:
    with db() as c:
        r = c.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
    return dict(r) if r else None


def set_topic_status(tid: int, status: str) -> None:
    with db() as c:
        c.execute("UPDATE topics SET status=? WHERE id=?", (status, tid))


def past_titles(limit: int = 120) -> list[str]:
    """Approved and proposed topics, so Claude does not suggest them again."""
    with db() as c:
        rows = c.execute("SELECT title FROM topics WHERE status!='rejected' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [r["title"] for r in rows][::-1]


def add_reel(topic_id: int, folder: str) -> int:
    with db() as c:
        return c.execute("INSERT INTO reels(topic_id,folder,status,updated) VALUES(?,?,?,?)",
                         (topic_id, folder, "producing", now())).lastrowid


def reel(rid: int) -> dict | None:
    with db() as c:
        r = c.execute("SELECT * FROM reels WHERE id=?", (rid,)).fetchone()
    return dict(r) if r else None


def update_reel(rid: int, **fields) -> None:
    fields["updated"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db() as c:
        c.execute(f"UPDATE reels SET {cols} WHERE id=?", (*fields.values(), rid))


def reels_by_status(*statuses: str) -> list[dict]:
    with db() as c:
        q = f"SELECT * FROM reels WHERE status IN ({','.join('?' * len(statuses))}) ORDER BY id"
        return [dict(r) for r in c.execute(q, statuses).fetchall()]


def get(key: str, default: str | None = None) -> str | None:
    with db() as c:
        r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def put(key: str, value: str) -> None:
    with db() as c:
        c.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
