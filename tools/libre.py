"""Narzędzie do synchronizacji danych z LibreLinkUp bezpośrednio do SQLite."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from fetch_libre import sync_libre_to_db
from .db import get_conn
from .time_utils import now_local

log = logging.getLogger(__name__)
SYNC_SOURCE = "libre"


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


def _max_age_minutes() -> int:
    return int(os.getenv("LIBRE_SYNC_MAX_AGE_MINUTES", "15"))


def should_auto_sync(max_age_minutes: int | None = None) -> bool:
    status = get_sync_status()
    if not status or not status.get("last_success_at"):
        return True
    last_success = datetime.fromisoformat(status["last_success_at"])
    age_limit = max_age_minutes if max_age_minutes is not None else _max_age_minutes()
    return now_local() - last_success >= timedelta(minutes=age_limit)


def sync_has_changes(result: dict) -> bool:
    totals = _aggregate_stats(result)
    return (totals["inserted"] + totals["updated"]) > 0


def mark_summary_refreshed() -> None:
    _set_sync_status(last_summary_refresh_at=now_local().isoformat())


def sync_libre_data(trigger: str = "manual") -> dict:
    started_at = now_local().isoformat()
    _set_sync_status(last_started_at=started_at, last_status=f"running:{trigger}", last_error=None)
    log.info("libre.sync start trigger=%s", trigger)
    result = sync_libre_to_db()
    if "error" in result:
        _set_sync_status(last_status=f"error:{trigger}", last_error=result["error"])
        log.error("libre.sync trigger=%s error=%s", trigger, result["error"])
        return result

    totals = _aggregate_stats(result)
    result["totals"] = totals
    result["changed"] = (totals["inserted"] + totals["updated"]) > 0
    _set_sync_status(
        last_success_at=now_local().isoformat(),
        last_success_date=now_local().date().isoformat(),
        last_status=f"success:{trigger}",
        last_error=None,
        last_fetched=totals["fetched"],
        last_inserted=totals["inserted"],
        last_updated=totals["updated"],
        last_unchanged=totals["unchanged"],
    )

    for name, stats in result.get("datasets", {}).items():
        log.info(
            "libre.sync trigger=%s dataset=%s fetched=%d inserted=%d updated=%d unchanged=%d",
            trigger,
            name,
            stats["fetched"],
            stats["inserted"],
            stats["updated"],
            stats["unchanged"],
        )
    log.info(
        "libre.sync finish trigger=%s fetched=%d inserted=%d updated=%d unchanged=%d changed=%s",
        trigger,
        totals["fetched"],
        totals["inserted"],
        totals["updated"],
        totals["unchanged"],
        result["changed"],
    )
    return result
