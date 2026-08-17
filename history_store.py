"""history_store.py — lightweight SQLite persistence for past scans."""

import sqlite3
import json
import os
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")
_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                job_id TEXT PRIMARY KEY,
                user_id INTEGER,
                filename TEXT,
                created_at TEXT,
                verdict TEXT,
                confidence REAL,
                thumbnail TEXT,
                result_json TEXT
            )
        """)
        conn.commit()
        # add user_id to older DBs that predate accounts
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(history)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE history ADD COLUMN user_id INTEGER")
            conn.commit()


def add_record(job_id, filename, created_at, verdict, confidence, thumbnail, payload, user_id=None):
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO history (job_id, user_id, filename, created_at, verdict, confidence, thumbnail, result_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, user_id, filename, created_at, verdict, confidence, thumbnail, json.dumps(payload)),
        )
        conn.commit()


def list_records(limit=50, user_id=None):
    with _lock, _connect() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT job_id, filename, created_at, verdict, confidence, thumbnail FROM history "
                "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT job_id, filename, created_at, verdict, confidence, thumbnail FROM history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_record(job_id):
    with _lock, _connect() as conn:
        row = conn.execute("SELECT result_json FROM history WHERE job_id = ?", (job_id,)).fetchone()
        return json.loads(row["result_json"]) if row else None


def delete_record(job_id):
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM history WHERE job_id = ?", (job_id,))
        conn.commit()
