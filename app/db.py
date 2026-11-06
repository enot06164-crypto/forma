"""SQLite-хранилище: файлы, задания, статистика."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "forma.db")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
    return _conn


def init() -> None:
    with _lock:
        c = conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS files(
                id TEXT PRIMARY KEY, sid TEXT NOT NULL, name TEXT, ext TEXT, kind TEXT,
                size INTEGER, path TEXT, role TEXT, parent TEXT, created REAL, meta TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, sid TEXT, file_id TEXT, target TEXT, status TEXT,
                progress REAL, note TEXT, out_id TEXT, error TEXT, created REAL, finished REAL
            );
            CREATE INDEX IF NOT EXISTS idx_files_sid ON files(sid);
            CREATE INDEX IF NOT EXISTS idx_files_created ON files(created);
            """
        )
        c.commit()


def add_file(fid: str, sid: str, name: str, ext: str, kind: str, size: int,
             path: str, role: str = "source", parent: str | None = None,
             meta: dict | None = None) -> None:
    with _lock:
        c = conn()
        c.execute(
            "INSERT OR REPLACE INTO files(id,sid,name,ext,kind,size,path,role,parent,created,meta)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (fid, sid, name, ext, kind, size, path, role, parent, time.time(),
             json.dumps(meta or {}, ensure_ascii=False)),
        )
        c.commit()


def get_file(fid: str) -> dict | None:
    with _lock:
        row = conn().execute("SELECT * FROM files WHERE id=?", (fid,)).fetchone()
    return dict(row) if row else None


def list_files(sid: str, limit: int = 200) -> list[dict]:
    with _lock:
        rows = conn().execute(
            "SELECT * FROM files WHERE sid=? ORDER BY created DESC LIMIT ?", (sid, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_file(fid: str) -> None:
    with _lock:
        c = conn()
        c.execute("DELETE FROM files WHERE id=? OR parent=?", (fid, fid))
        c.commit()


def stats() -> dict:
    with _lock:
        c = conn()
        row = c.execute(
            "SELECT COALESCE(SUM(size),0) AS bytes, COUNT(*) AS n FROM files WHERE role='output'"
        ).fetchone()
        src = c.execute("SELECT COUNT(*) AS n FROM files WHERE role='source'").fetchone()
        by_kind = c.execute(
            "SELECT kind, COUNT(*) AS n, COALESCE(SUM(size),0) AS b FROM files"
            " WHERE role='output' GROUP BY kind ORDER BY b DESC"
        ).fetchall()
        by_ext = c.execute(
            "SELECT ext, COUNT(*) AS n FROM files WHERE role='output'"
            " GROUP BY ext ORDER BY n DESC LIMIT 8"
        ).fetchall()
    return {
        "bytes": row["bytes"], "outputs": row["n"], "sources": src["n"],
        "by_kind": [dict(r) for r in by_kind],
        "by_ext": [dict(r) for r in by_ext],
    }


def add_job(jid: str, sid: str, file_id: str, target: str) -> None:
    with _lock:
        c = conn()
        c.execute(
            "INSERT OR REPLACE INTO jobs(id,sid,file_id,target,status,progress,note,created)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (jid, sid, file_id, target, "queued", 0.0, "в очереди", time.time()),
        )
        c.commit()


def finish_job(jid: str, status: str, out_id: str | None, error: str | None) -> None:
    with _lock:
        c = conn()
        c.execute(
            "UPDATE jobs SET status=?, progress=?, out_id=?, error=?, finished=? WHERE id=?",
            (status, 1.0 if status == "done" else 0.0, out_id, error, time.time(), jid),
        )
        c.commit()


def purge_older_than(days: int) -> int:
    cutoff = time.time() - days * 86400
    with _lock:
        c = conn()
        rows = c.execute("SELECT id, path FROM files WHERE created < ?", (cutoff,)).fetchall()
        for r in rows:
            try:
                if r["path"] and os.path.exists(r["path"]):
                    os.unlink(r["path"])
            except OSError:
                pass
        c.execute("DELETE FROM files WHERE created < ?", (cutoff,))
        c.commit()
    return len(rows)
