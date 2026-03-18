from __future__ import annotations

from datetime import datetime

from tools.db import get_conn
from tools.garmin import get_sync_status, mark_summary_refreshed, should_auto_sync_today, sync_garmin_data, sync_has_changes


def test_should_auto_sync_today_depends_on_last_success_date(monkeypatch, temp_db):
    monkeypatch.setattr("tools.garmin.today_local", lambda: "2026-03-18")

    assert should_auto_sync_today() is True

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sync_status (source, last_success_date, last_status) VALUES (?, ?, ?)",
            ("garmin", "2026-03-18", "success:auto_daily"),
        )
        conn.commit()

    assert should_auto_sync_today() is False


def test_sync_garmin_data_updates_status_and_totals(monkeypatch, temp_db):
    fixed_now = datetime(2026, 3, 18, 15, 30, 0)
    monkeypatch.setattr("tools.garmin.now_local", lambda: fixed_now)
    monkeypatch.setattr("tools.garmin.today_local", lambda: "2026-03-18")
    monkeypatch.setattr(
        "tools.garmin.sync_garmin_to_db",
        lambda: {
            "ok": True,
            "datasets": {
                "waga": {"fetched": 2, "inserted": 1, "updated": 0, "unchanged": 1},
                "sen": {"fetched": 1, "inserted": 0, "updated": 1, "unchanged": 0},
            },
        },
    )

    result = sync_garmin_data(trigger="test")

    assert result["changed"] is True
    assert result["totals"] == {"fetched": 3, "inserted": 1, "updated": 1, "unchanged": 1}
    assert sync_has_changes(result) is True

    status = get_sync_status()
    assert status["last_status"] == "success:test"
    assert status["last_success_date"] == "2026-03-18"
    assert status["last_inserted"] == 1
    assert status["last_updated"] == 1

    mark_summary_refreshed()
    status = get_sync_status()
    assert status["last_summary_refresh_at"] == fixed_now.isoformat()
