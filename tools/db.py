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
    """Tworzy tabele jeśli nie istnieją."""
    conn = get_conn()
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
    """)
    conn.commit()
    conn.close()
