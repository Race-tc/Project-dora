"""backend/db_backup.py — periodic on-volume snapshot of dora.db.

Mitigates data loss from a bad migration or a bad write reaching a live
row (restore from yesterday's snapshot). It does NOT protect against
losing the whole Railway volume, which would take the backups with it —
that needs an off-volume copy (S3/GCS/etc.), which needs storage
credentials this repo doesn't have. Wire that up separately once
available; this is the cheap, dependency-free stopgap in the meantime.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import database as db

_BACKUP_DIR = db.DB_PATH.parent / "backups"
_KEEP = 14  # daily snapshots
_INTERVAL_SECONDS = 24 * 60 * 60


def backup_once() -> Path | None:
    """Consistent snapshot via sqlite3's own backup API — safe under WAL
    mode and concurrent writers, unlike a raw file copy of dora.db alone
    (recent rows can still be sitting only in the -wal file)."""
    if not db.DB_PATH.exists():
        return None
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = _BACKUP_DIR / f"dora_{stamp}.db"
    src_con = sqlite3.connect(db.DB_PATH)
    dest_con = sqlite3.connect(dest)
    try:
        src_con.backup(dest_con)
    finally:
        dest_con.close()
        src_con.close()
    print(f"[backup] snapshot written: {dest}")
    _prune_old()
    return dest


def _prune_old() -> None:
    snapshots = sorted(_BACKUP_DIR.glob("dora_*.db"))
    for stale in snapshots[:-_KEEP]:
        stale.unlink(missing_ok=True)


async def run_forever() -> None:
    """Snapshot immediately on startup (Railway services restart often —
    don't wait a full day after a redeploy for the first safety net),
    then every _INTERVAL_SECONDS after that."""
    while True:
        try:
            backup_once()
        except Exception as exc:
            print(f"[backup] snapshot failed: {exc}")
        await asyncio.sleep(_INTERVAL_SECONDS)
