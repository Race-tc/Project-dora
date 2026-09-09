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
        con.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT    NOT NULL UNIQUE,
                created_at  TEXT    NOT NULL,
                notified    INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Lightweight migrations for DBs created before these columns existed.
        try:
            con.execute("ALTER TABLE ai_requests ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
        except sqlite3.OperationalError:
            pass   # column already exists
        try:
            # 'paid' (Stripe subscription) or 'beta' (free, expires on BETA_END_DATE).
            con.execute("ALTER TABLE licences ADD COLUMN licence_type TEXT NOT NULL DEFAULT 'paid'")
        except sqlite3.OperationalError:
            pass   # column already exists
        try:
            # 'shop' (per-workshop) or 'solo' (single-seat) pricing tier.
            con.execute("ALTER TABLE licences ADD COLUMN tier TEXT NOT NULL DEFAULT 'shop'")
        except sqlite3.OperationalError:
            pass   # column already exists
        try:
            # Solo tier only: the device currently bound to this licence.
            # NULL until first use. Shop licences never set this — they
            # cover a whole site, not a single machine.
            con.execute("ALTER TABLE licences ADD COLUMN device_id TEXT")
        except sqlite3.OperationalError:
            pass   # column already exists
        try:
            con.execute("ALTER TABLE licences ADD COLUMN device_bound_at TEXT")
        except sqlite3.OperationalError:
            pass   # column already exists

        con.execute("""
            CREATE TABLE IF NOT EXISTS tunes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                author_name     TEXT    NOT NULL,
                uploader_email  TEXT    NOT NULL,
                licence_key     TEXT    NOT NULL,
                vehicle_make    TEXT    NOT NULL DEFAULT '',
                vehicle_model   TEXT    NOT NULL DEFAULT '',
                vehicle_year    TEXT    NOT NULL DEFAULT '',
                ecu_type        TEXT    NOT NULL DEFAULT '',
                engine          TEXT    NOT NULL DEFAULT '',
                mods            TEXT    NOT NULL DEFAULT '',
                power_gain      TEXT    NOT NULL DEFAULT '',
                hp_before       REAL,
                hp_after        REAL,
                description     TEXT    NOT NULL DEFAULT '',
                tags            TEXT    NOT NULL DEFAULT '',
                filename        TEXT    NOT NULL,
                file_size       INTEGER NOT NULL,
                file_blob       BLOB    NOT NULL,
                downloads       INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL
            )
        """)
        # Lightweight migrations for a `tunes` table created before these
        # columns existed — CREATE TABLE IF NOT EXISTS above is a no-op
        # against an already-existing table, so a column added to the
        # schema after the table's first deploy never actually lands on
        # production without this (the exact bug that broke every
        # marketplace route with "no such column" once power_gain/
        # hp_before/hp_after/tags/etc. were added here after the table
        # already existed live).
        for _col_def in (
            "vehicle_make TEXT NOT NULL DEFAULT ''",
            "vehicle_model TEXT NOT NULL DEFAULT ''",
            "vehicle_year TEXT NOT NULL DEFAULT ''",
            "ecu_type TEXT NOT NULL DEFAULT ''",
            "engine TEXT NOT NULL DEFAULT ''",
            "mods TEXT NOT NULL DEFAULT ''",
            "power_gain TEXT NOT NULL DEFAULT ''",
            "hp_before REAL",
            "hp_after REAL",
            "description TEXT NOT NULL DEFAULT ''",
            "tags TEXT NOT NULL DEFAULT ''",
            "downloads INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                con.execute(f"ALTER TABLE tunes ADD COLUMN {_col_def}")
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
    licence_type: str = "paid",
    tier: str = "shop",
) -> str:
    key = generate_key()
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        con.execute(
            """INSERT INTO licences
               (licence_key, email, stripe_customer_id,
                stripe_subscription_id, status, created_at, note, licence_type, tier)
               VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (key, email, stripe_customer_id, stripe_subscription_id, now, note, licence_type, tier),
        )
    return key


def get_licence(key: str) -> sqlite3.Row | None:
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences WHERE licence_key = ?", (key,)
        ).fetchone()


def get_beta_licence_by_email(email: str) -> sqlite3.Row | None:
    """Used by /admin/launch-beta so a retry after a failed send reuses the
    already-minted key for that email instead of stacking up a fresh one
    on every re-run."""
    with get_db() as con:
        return con.execute(
            "SELECT * FROM licences WHERE email = ? AND licence_type = 'beta' "
            "ORDER BY created_at DESC LIMIT 1",
            (email,),
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


def bind_device(key: str, device_id: str) -> None:
    """(Re)bind a Solo licence to a device. Called on first use (device_id
    was NULL) and on an allowed rebind (existing device_id, but the rebind
    cooldown in main.py's _enforce_solo_device has already elapsed)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        con.execute(
            "UPDATE licences SET device_id = ?, device_bound_at = ? WHERE licence_key = ?",
            (device_id, now, key),
        )


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


# ── Waitlist ──────────────────────────────────────────────────────────────────

def add_to_waitlist(email: str) -> bool:
    """Returns True if this email was newly added, False if it was already
    on the list (INSERT OR IGNORE swallows the UNIQUE conflict silently, so
    the caller needs the row count to tell the two cases apart)."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        cur = con.execute(
            "INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?, ?)",
            (email, now),
        )
        return cur.rowcount > 0


def list_pending_waitlist() -> list[sqlite3.Row]:
    with get_db() as con:
        return con.execute(
            "SELECT * FROM waitlist WHERE notified = 0 ORDER BY created_at ASC"
        ).fetchall()


def mark_waitlist_notified(email: str) -> None:
    with get_db() as con:
        con.execute("UPDATE waitlist SET notified = 1 WHERE email = ?", (email,))


# ── Marketplace tunes ─────────────────────────────────────────────────────────
# file_blob is intentionally excluded from _TUNE_LIST_COLUMNS so listing and
# detail queries never pull tune file bytes into memory — only get_tune_file
# (used by the download route) selects it.
_TUNE_LIST_COLUMNS = (
    "id, title, author_name, licence_key, vehicle_make, vehicle_model, vehicle_year, "
    "ecu_type, engine, mods, power_gain, hp_before, hp_after, description, tags, "
    "filename, file_size, downloads, created_at"
)


def create_tune(
    title: str,
    author_name: str,
    uploader_email: str,
    licence_key: str,
    filename: str,
    file_blob: bytes,
    vehicle_make: str = "",
    vehicle_model: str = "",
    vehicle_year: str = "",
    ecu_type: str = "",
    engine: str = "",
    mods: str = "",
    power_gain: str = "",
    hp_before: float | None = None,
    hp_after: float | None = None,
    description: str = "",
    tags: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as con:
        cur = con.execute(
            """INSERT INTO tunes
               (title, author_name, uploader_email, licence_key, vehicle_make,
                vehicle_model, vehicle_year, ecu_type, engine, mods, power_gain,
                hp_before, hp_after, description, tags, filename, file_size,
                file_blob, downloads, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)""",
            (title, author_name, uploader_email, licence_key, vehicle_make,
             vehicle_model, vehicle_year, ecu_type, engine, mods, power_gain,
             hp_before, hp_after, description, tags, filename, len(file_blob),
             file_blob, now),
        )
        return cur.lastrowid


def _like_escape(s: str) -> str:
    """Escape SQLite LIKE wildcards so a literal '%' or '_' in a search term
    (e.g. an engine code like "2.0T" typo'd as "2_0T", or "B58%") is matched
    literally instead of acting as a wildcard. Paired with ESCAPE '\\' below."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_tunes(search: str = "") -> list[sqlite3.Row]:
    with get_db() as con:
        if search:
            like = f"%{_like_escape(search)}%"
            return con.execute(
                f"""SELECT {_TUNE_LIST_COLUMNS} FROM tunes
                    WHERE title LIKE ? ESCAPE '\\' OR vehicle_make LIKE ? ESCAPE '\\'
                       OR vehicle_model LIKE ? ESCAPE '\\' OR engine LIKE ? ESCAPE '\\'
                       OR ecu_type LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\'
                    ORDER BY created_at DESC""",
                (like, like, like, like, like, like),
            ).fetchall()
        return con.execute(
            f"SELECT {_TUNE_LIST_COLUMNS} FROM tunes ORDER BY created_at DESC"
        ).fetchall()


def get_tune(tune_id: int) -> sqlite3.Row | None:
    with get_db() as con:
        return con.execute(
            f"SELECT {_TUNE_LIST_COLUMNS} FROM tunes WHERE id = ?", (tune_id,)
        ).fetchone()


def get_tune_file(tune_id: int) -> sqlite3.Row | None:
    with get_db() as con:
        return con.execute(
            "SELECT filename, file_blob FROM tunes WHERE id = ?", (tune_id,)
        ).fetchone()


def increment_downloads(tune_id: int) -> None:
    with get_db() as con:
        con.execute("UPDATE tunes SET downloads = downloads + 1 WHERE id = ?", (tune_id,))


def delete_tune(tune_id: int) -> bool:
    with get_db() as con:
        cur = con.execute("DELETE FROM tunes WHERE id = ?", (tune_id,))
        return cur.rowcount > 0
