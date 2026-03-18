"""Shared database connection for tools."""

import sqlite3
import os
from pathlib import Path

_DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent.parent / "data" / "k90.db"))


def get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
