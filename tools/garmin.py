"""Narzędzie do synchronizacji danych z Garmin Connect bezpośrednio do SQLite."""

from __future__ import annotations

from logging_setup import event
from profiling import profiled

import sys
import logging
import os

from fetch_garmin import sync_garmin_to_db
from .db import get_conn
from .time_utils import now_local, today_local

SYNC_SOURCE = "garmin"


def _aggregate_stats(result: dict) -> dict:
    totals = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0}
    for stats in result.get("datasets", {}).values():
        for key in totals:
            totals[key] += int(stats.get(key, 0) or 0)
    return totals


def _set_sync_status(**fields) -> None:
    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM sync_status WHERE source = ?",
        (SYNC_SOURCE,),
    ).fetchone()
    data = dict(existing) if existing else {"source": SYNC_SOURCE}
    data.update(fields)
    conn.execute(
        """
        INSERT INTO sync_status (
            source, last_started_at, last_success_at, last_success_date,
            last_status, last_error, last_fetched, last_inserted,
            last_updated, last_unchanged, last_summary_refresh_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_started_at = excluded.last_started_at,
            last_success_at = excluded.last_success_at,
            last_success_date = excluded.last_success_date,
            last_status = excluded.last_status,
            last_error = excluded.last_error,
            last_fetched = excluded.last_fetched,
            last_inserted = excluded.last_inserted,
            last_updated = excluded.last_updated,
            last_unchanged = excluded.last_unchanged,
            last_summary_refresh_at = excluded.last_summary_refresh_at
        """,
        (
            data.get("source", SYNC_SOURCE),
            data.get("last_started_at"),
            data.get("last_success_at"),
            data.get("last_success_date"),
            data.get("last_status"),
            data.get("last_error"),
            data.get("last_fetched", 0),
            data.get("last_inserted", 0),
            data.get("last_updated", 0),
            data.get("last_unchanged", 0),
            data.get("last_summary_refresh_at"),
        ),
    )
    conn.commit()
    conn.close()


def get_sync_status() -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM sync_status WHERE source = ?", (SYNC_SOURCE,)).fetchone()
    conn.close()
    return dict(row) if row else None


def should_auto_sync_today() -> bool:
    status = get_sync_status()
    return not status or status.get("last_success_date") != today_local()


def sync_has_changes(result: dict) -> bool:
    totals = _aggregate_stats(result)
    return (totals["inserted"] + totals["updated"]) > 0


def mark_summary_refreshed() -> None:
    _set_sync_status(last_summary_refresh_at=now_local().isoformat())


@profiled('sync_garmin')
def sync_garmin_data(trigger: str = "manual") -> dict:
    """Pobiera nowe dane z Garmin Connect i aktualizuje SQLite bez pośrednictwa CSV."""
    if os.getenv("K90_SYNC_ENABLED", "true").lower() == "false":
        return {"error": "Synchronizacja jest wyłączona w lokalnej kopii danych."}
    started_at = now_local().isoformat()
    _set_sync_status(last_started_at=started_at, last_status=f"running:{trigger}", last_error=None)
    event('garmin.sync', component='tools.garmin')
    try:
        result = sync_garmin_to_db()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _set_sync_status(last_status=f"error:{trigger}", last_error=error)
        event('garmin.sync', component='tools.garmin', level=logging.ERROR, error=sys.exception())
        return {"error": error}
    if "error" in result:
        _set_sync_status(last_status=f"error:{trigger}", last_error=result["error"])
        event('garmin.sync', component='tools.garmin', level=logging.ERROR)
        return result

    totals = _aggregate_stats(result)
    result["totals"] = totals
    result["changed"] = (totals["inserted"] + totals["updated"]) > 0
    _set_sync_status(
        last_success_at=now_local().isoformat(),
        last_success_date=today_local(),
        last_status=f"success:{trigger}",
        last_error=None,
        last_fetched=totals["fetched"],
        last_inserted=totals["inserted"],
        last_updated=totals["updated"],
        last_unchanged=totals["unchanged"],
    )

    for name, stats in result.get("datasets", {}).items():
        event('garmin.sync', component='tools.garmin', fetched=stats["fetched"], inserted=stats["inserted"], updated=stats["updated"], unchanged=stats["unchanged"])
    event('garmin.sync', component='tools.garmin', fetched=totals["fetched"], inserted=totals["inserted"], updated=totals["updated"], unchanged=totals["unchanged"])
    return result
