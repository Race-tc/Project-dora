"""
backend/database.py — SQLite licence store.
"""
from __future__ import annotations

import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import os as _os
DB_PATH = Path(_os.getenv("DB_PATH", str(Path(__file__).parent / "dora.db")))


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def get_db():
    con = _conn()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS licences (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                licence_key             TEXT    NOT NULL UNIQUE,
                email                   TEXT    NOT NULL,
                stripe_customer_id      TEXT,
                stripe_subscription_id  TEXT,
                status                  TEXT    NOT NULL DEFAULT 'active',
                created_at              TEXT    NOT NULL,
                note                    TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ai_requests (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                licence_key TEXT    NOT NULL,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT    NOT NULL
            )
        """)


# ── Licence helpers ───────────────────────────────────────────────────────────

def generate_key() -> str:
    return "DORA-" + secrets.token_urlsafe(24).upper()[:28]


def create_licence(
    email: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    note: str | None = None,
) -> str:
    key = generate_key()
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        con.execute(
            """INSERT INTO licences
               (licence_key, email, stripe_customer_id,
                stripe_subscription_id, status, created_at, note)
               VALUES (?, ?, ?, ?, 'active', ?, ?)""",
            (key, email, stripe_customer_id, stripe_subscription_id, now, note),
        )
    return key


def get_licence(key: str) -> sqlite3.Row | None:
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences WHERE licence_key = ?", (key,)
        ).fetchone()


def set_status(stripe_subscription_id: str, status: str) -> None:
    with get_db() as con:
        con.execute(
            "UPDATE licences SET status = ? WHERE stripe_subscription_id = ?",
            (status, stripe_subscription_id),
        )


def log_request(key: str, tokens: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        con.execute(
            "INSERT INTO ai_requests (licence_key, tokens_used, created_at) VALUES (?,?,?)",
            (key, tokens, now),
        )


def list_licences() -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences ORDER BY created_at DESC"
        ).fetchall()
