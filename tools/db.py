"""Shared database connection for tools."""

from __future__ import annotations

import os
import sqlite3
from datetime import timedelta
from pathlib import Path

from .time_utils import APP_TIMEZONE, now_local

_DEFAULT_DB_PATH = str(Path(__file__).parent.parent / "data" / "k90.db")
_DB_PATH = os.getenv("DB_PATH", _DEFAULT_DB_PATH)
_DEFAULT_BACKUP_RETENTION_DAYS = 30


def get_db_path() -> str:
    return os.getenv("DB_PATH", _DB_PATH)


def get_data_dir() -> Path:
    data_dir = os.getenv("DATA_DIR")
    if data_dir:
        return Path(data_dir)
    return Path(get_db_path()).resolve().parent


def get_backup_dir() -> Path:
    backup_dir = os.getenv("BACKUP_DIR")
    if backup_dir:
        return Path(backup_dir)
    return get_data_dir() / "backups"


def get_backup_retention_days() -> int:
    raw = os.getenv("BACKUP_RETENTION_DAYS", str(_DEFAULT_BACKUP_RETENTION_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        return _DEFAULT_BACKUP_RETENTION_DAYS
    return max(days, 0)


def get_conn():
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def checkpoint_wal(conn: sqlite3.Connection, mode: str = "TRUNCATE") -> None:
    """Flush WAL pages into the main database file when WAL mode is enabled."""
    try:
        conn.execute(f"PRAGMA wal_checkpoint({mode})")
    except sqlite3.DatabaseError:
        pass


def _prune_old_backups(backup_dir: Path, stem: str, suffix: str, retention_days: int) -> list[Path]:
    if retention_days < 0:
        return []

    cutoff = now_local() - timedelta(days=retention_days)
    deleted = []
    for candidate in backup_dir.glob(f"{stem}-*{suffix}"):
        modified_at = now_local().fromtimestamp(candidate.stat().st_mtime, now_local().tzinfo)
        if modified_at < cutoff:
            candidate.unlink(missing_ok=True)
            deleted.append(candidate)
    return deleted


def create_db_backup(retention_days: int | None = None) -> dict[str, object]:
    db_path = Path(get_db_path())
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = now_local()
    suffix = db_path.suffix or ".db"
    backup_path = backup_dir / f"{db_path.stem}-{timestamp.strftime('%Y-%m-%d_%H-%M-%S')}{suffix}"

    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    dest = sqlite3.connect(str(backup_path), timeout=30)
    try:
        src.execute("PRAGMA busy_timeout = 5000")
        src.backup(dest)
        dest.commit()
    except Exception:
        dest.close()
        src.close()
        backup_path.unlink(missing_ok=True)
        raise
    finally:
        try:
            dest.close()
        except sqlite3.Error:
            pass
        try:
            src.close()
        except sqlite3.Error:
            pass

    deleted_paths = _prune_old_backups(backup_dir, db_path.stem, suffix, get_backup_retention_days() if retention_days is None else retention_days)
    return {
        "path": str(backup_path),
        "filename": backup_path.name,
        "size_bytes": backup_path.stat().st_size,
        "created_at": timestamp.isoformat(timespec="seconds"),
        "timezone": APP_TIMEZONE,
        "retention_days": get_backup_retention_days() if retention_days is None else retention_days,
        "deleted_old": len(deleted_paths),
        "backup_dir": str(backup_dir),
    }


def rows_to_list(rows):
    return [dict(r) for r in rows]


def init_db():
    """Tworzy tabele agenta oraz podstawowy schemat danych zdrowotnych jeśli nie istnieją."""
    conn = get_conn()
    try:
        from migrate_csv_to_sqlite import create_schema
        create_schema(conn)
    except Exception:
        pass
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS patient_summary (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            content TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            trigger TEXT
        );
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER
        );
        CREATE TABLE IF NOT EXISTS sync_status (
            source TEXT PRIMARY KEY,
            last_started_at DATETIME,
            last_success_at DATETIME,
            last_success_date TEXT,
            last_status TEXT,
            last_error TEXT,
            last_fetched INTEGER DEFAULT 0,
            last_inserted INTEGER DEFAULT 0,
            last_updated INTEGER DEFAULT 0,
            last_unchanged INTEGER DEFAULT 0,
            last_summary_refresh_at DATETIME
        );
    """)
    conn.commit()
    conn.close()
