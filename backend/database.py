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
                created_at  TEXT    NOT NULL,
                kind        TEXT    NOT NULL DEFAULT 'text'
            )
        """)
        # Lightweight migration for DBs created before the `kind` column existed.
        try:
            con.execute("ALTER TABLE ai_requests ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
        except sqlite3.OperationalError:
            pass   # column already exists


# ── Licence helpers ───────────────────────────────────────────────────────────

def generate_key() -> str:
    # No .upper() here: folding token_urlsafe's mixed-case alphabet (64
    # symbols) down to uppercase+digits+-_ (~38 symbols) before truncating
    # cuts per-character entropy from 6 bits to ~5.25 bits. Not exploitable
    # at this length, but an easy trap if the truncation length is ever
    # shortened later — the effective keyspace would be smaller than
    # token_urlsafe(24) implies. Nothing downstream assumes uppercase:
    # lookups are an exact string match, and every client field that
    # accepts a licence key just .strip()s it, never .upper()s it.
    return "DORA-" + secrets.token_urlsafe(24)[:28]


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


def get_licence_by_subscription_id(stripe_subscription_id: str) -> sqlite3.Row | None:
    """Used by the webhook handler to detect a retried checkout.session.completed
    event (Stripe retries on any non-2xx response or timeout) before minting a
    second licence for the same subscription."""
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences WHERE stripe_subscription_id = ?",
            (stripe_subscription_id,),
        ).fetchone()


def set_status(stripe_subscription_id: str, status: str) -> bool:
    """Returns True if a licence row was actually updated. Stripe doesn't
    guarantee webhook delivery order — a subscription.updated/.deleted
    event can arrive before the checkout.session.completed that creates
    the licence, in which case this matches zero rows and the status
    change is lost with no record of it ever having been attempted unless
    the caller checks this return value."""
    with get_db() as con:
        cur = con.execute(
            "UPDATE licences SET status = ? WHERE stripe_subscription_id = ?",
            (status, stripe_subscription_id),
        )
        return cur.rowcount > 0


def log_request(key: str, tokens: int, kind: str = "text") -> None:
    """`kind` distinguishes usage in admin reporting — 'text' (Claude calls,
    metered in tokens), 'voice_stt' (audio seconds), 'voice_tts' (characters)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        con.execute(
            "INSERT INTO ai_requests (licence_key, tokens_used, created_at, kind) VALUES (?,?,?,?)",
            (key, tokens, now, kind),
        )


def list_licences() -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences ORDER BY created_at DESC"
        ).fetchall()
