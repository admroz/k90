#!/usr/bin/env python3
"""
FreeStyle Libre / LibreLinkUp data fetcher — projekt k90.

Synchronizuje dane glukozy bezpośrednio do SQLite.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Brak python-dotenv. Uruchom: pip install python-dotenv")

try:
    from libre_link_up import LibreLinkUpClient
except ImportError:
    sys.exit("Brak libre-linkup-py. Uruchom: pip install libre-linkup-py")

from migrate_csv_to_sqlite import create_schema

load_dotenv()

USERNAME = os.getenv("LIBRE_LINK_UP_USERNAME")
PASSWORD = os.getenv("LIBRE_LINK_UP_PASSWORD")
LIBRE_URL = os.getenv("LIBRE_LINK_UP_URL", "https://api.libreview.io")
LIBRE_VERSION = os.getenv("LIBRE_LINK_UP_VERSION", "4.16.0")
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "k90.db"))

TABLE_CONFIG = {
    "glukoza_libre": {
        "key_cols": ["timestamp", "source_kind"],
        "columns": [
            "timestamp",
            "source_kind",
            "factory_timestamp",
            "data",
            "czas",
            "glukoza_mg_dl",
            "trend_arrow",
            "trend_message",
            "measurement_color",
            "is_high",
            "is_low",
            "typ",
            "zrodlo",
        ],
    },
}


def ensure_agent_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
        """
    )


def login() -> LibreLinkUpClient:
    client = LibreLinkUpClient(
        username=USERNAME,
        password=PASSWORD,
        url=LIBRE_URL,
        version=LIBRE_VERSION,
    )
    client.login()
    return client


def _parse_timestamp(raw_value: str | None) -> tuple[str | None, str | None, str | None]:
    if not raw_value:
        return None, None, None
    dt = datetime.strptime(raw_value, "%m/%d/%Y %I:%M:%S %p")
    return dt.strftime("%Y-%m-%dT%H:%M:%S"), dt.date().isoformat(), dt.strftime("%H:%M:%S")


def _normalize_record(record: dict, columns: list[str]) -> dict:
    normalized = {}
    for column in columns:
        value = record.get(column)
        if value == "":
            value = None
        normalized[column] = value
    return normalized


def _compare_rows(existing: sqlite3.Row, incoming: dict, columns: list[str]) -> bool:
    return all(existing[column] == incoming[column] for column in columns)


def _insert_or_update_many(conn: sqlite3.Connection, table: str, records: list[dict]) -> dict:
    config = TABLE_CONFIG[table]
    key_cols = config["key_cols"]
    columns = config["columns"]
    stats = {"fetched": len(records), "inserted": 0, "updated": 0, "unchanged": 0}
    if not records:
        return stats

    select_sql = f"SELECT {', '.join(columns)} FROM {table} WHERE " + " AND ".join(f"{col} = ?" for col in key_cols)
    insert_sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
    update_cols = [col for col in columns if col not in key_cols]
    update_sql = f"UPDATE {table} SET " + ", ".join(f"{col} = ?" for col in update_cols) + " WHERE " + " AND ".join(f"{col} = ?" for col in key_cols)

    for record in records:
        normalized = _normalize_record(record, columns)
        key_values = [normalized[col] for col in key_cols]
        existing = conn.execute(select_sql, key_values).fetchone()
        if existing is None:
            conn.execute(insert_sql, [normalized[col] for col in columns])
            stats["inserted"] += 1
            continue
        if _compare_rows(existing, normalized, columns):
            stats["unchanged"] += 1
            continue
        conn.execute(update_sql, [normalized[col] for col in update_cols] + key_values)
        stats["updated"] += 1

    return stats


def _record_from_reading(reading: dict, source_kind: str) -> dict | None:
    timestamp, local_date, local_time = _parse_timestamp(reading.get("Timestamp") or reading.get("FactoryTimestamp"))
    if not timestamp or not local_date or not local_time:
        return None

    factory_timestamp, _, _ = _parse_timestamp(reading.get("FactoryTimestamp"))
    trend_message = reading.get("TrendMessage")
    if trend_message is not None:
        trend_message = str(trend_message)

    return {
        "timestamp": timestamp,
        "source_kind": source_kind,
        "factory_timestamp": factory_timestamp,
        "data": local_date,
        "czas": local_time,
        "glukoza_mg_dl": reading.get("ValueInMgPerDl") or reading.get("Value"),
        "trend_arrow": reading.get("TrendArrow"),
        "trend_message": trend_message,
        "measurement_color": reading.get("MeasurementColor"),
        "is_high": int(bool(reading.get("isHigh"))) if reading.get("isHigh") is not None else None,
        "is_low": int(bool(reading.get("isLow"))) if reading.get("isLow") is not None else None,
        "typ": reading.get("type"),
        "zrodlo": "librelinkup",
    }


def fetch_glucose_records(client: LibreLinkUpClient) -> list[dict]:
    raw_graph = client.get_raw_graph_readings()
    data = (raw_graph or {}).get("data") or {}
    records: list[dict] = []

    for reading in data.get("graphData") or []:
        if not isinstance(reading, dict):
            continue
        record = _record_from_reading(reading, "graph")
        if record is not None:
            records.append(record)

    latest = ((data.get("connection") or {}).get("glucoseMeasurement"))
    if isinstance(latest, dict):
        record = _record_from_reading(latest, "latest")
        if record is not None:
            records.append(record)

    return sorted(records, key=lambda row: (row["timestamp"], row["source_kind"]))


def sync_libre_to_db(client: LibreLinkUpClient | None = None) -> dict:
    if not USERNAME or not PASSWORD:
        return {"error": "Brak kredencjałów Libre — uzupełnij plik .env"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    create_schema(conn)
    ensure_agent_tables(conn)
    conn.commit()

    print("\n" + "=" * 55)
    print("  LibreLinkUp sync → SQLite")
    print("=" * 55 + "\n")

    own_client = client is None
    if own_client:
        client = login()

    try:
        records = fetch_glucose_records(client)
        stats = _insert_or_update_many(conn, "glukoza_libre", records)
        conn.commit()
        return {"ok": True, "datasets": {"glukoza_libre": stats}}
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError:
            pass
        conn.close()


def main() -> None:
    result = sync_libre_to_db()
    if "error" in result:
        sys.exit(result["error"])

    print("\n" + "=" * 55)
    print("  Gotowe!")
    for name, stats in result.get("datasets", {}).items():
        print(
            f"  {name}: pobrane {stats['fetched']}, nowe {stats['inserted']}, "
            f"zaktualizowane {stats['updated']}, bez zmian {stats['unchanged']}"
        )
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
