"""auth_store.py — lightweight SQLite user accounts with hashed passwords."""

import sqlite3
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")
_lock = threading.Lock()

RESET_TOKEN_TTL_MINUTES = 60


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT,
                expires_at TEXT,
                used INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def create_user(email, name, password):
    email = email.strip().lower()
    password_hash = generate_password_hash(password)
    with _lock, _connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return None, "An account with that email already exists."
        cur = conn.execute(
            "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, datetime('now'))",
            (email, name, password_hash),
        )
        conn.commit()
        return cur.lastrowid, None


def verify_user(email, password):
    email = email.strip().lower()
    with _lock, _connect() as conn:
        row = conn.execute("SELECT id, name, password_hash FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            return None, "No account found with that email."
        if not check_password_hash(row["password_hash"], password):
            return None, "Incorrect password."
        return {"id": row["id"], "email": email, "name": row["name"]}, None


def get_user(user_id):
    with _lock, _connect() as conn:
        row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email):
    email = email.strip().lower()
    with _lock, _connect() as conn:
        row = conn.execute("SELECT id, email, name FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def create_reset_token(email):
    """Returns a fresh reset token for the account with this email, or
    None if no such account exists. Callers should still show a generic
    'check your email' message either way, to avoid leaking which
    emails have accounts."""
    user = get_user_by_email(email)
    if user is None:
        return None
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO password_resets (token, user_id, created_at, expires_at, used) VALUES (?, ?, ?, ?, 0)",
            (token, user["id"], now.isoformat(), expires.isoformat()),
        )
        conn.commit()
    return token


def verify_reset_token(token):
    """Returns the user_id for a valid, unused, unexpired token, else None."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT user_id, expires_at, used FROM password_resets WHERE token = ?", (token,)
        ).fetchone()
        if row is None or row["used"]:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
        return row["user_id"]


def reset_password(token, new_password):
    user_id = verify_reset_token(token)
    if user_id is None:
        return False, "This reset link is invalid or has expired."
    password_hash = generate_password_hash(new_password)
    with _lock, _connect() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        conn.execute("UPDATE password_resets SET used = 1 WHERE token = ?", (token,))
        conn.commit()
    return True, None
