from __future__ import annotations

from datetime import datetime, timedelta

from tools.libre import get_sync_status, mark_summary_refreshed, should_auto_sync, sync_has_changes, sync_libre_data


def test_should_auto_sync_depends_on_last_success_age(monkeypatch, temp_db):
    fixed_now = datetime(2026, 3, 19, 18, 0, 0)
    monkeypatch.setenv("LIBRE_SYNC_MAX_AGE_MINUTES", "15")
    monkeypatch.setattr("tools.libre.now_local", lambda: fixed_now)

    assert should_auto_sync() is True

    from tools.db import get_conn

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sync_status (source, last_success_at, last_status) VALUES (?, ?, ?)",
            ("libre", (fixed_now - timedelta(minutes=10)).isoformat(), "success:auto"),
        )
        conn.commit()

    assert should_auto_sync() is False

    with get_conn() as conn:
        conn.execute(
            "UPDATE sync_status SET last_success_at = ? WHERE source = ?",
            ((fixed_now - timedelta(minutes=20)).isoformat(), "libre"),
        )
        conn.commit()

    assert should_auto_sync() is True


def test_sync_libre_data_updates_status_and_totals(monkeypatch, temp_db):
    fixed_now = datetime(2026, 3, 19, 18, 30, 0)
    monkeypatch.setattr("tools.libre.now_local", lambda: fixed_now)
    monkeypatch.setattr(
        "tools.libre.sync_libre_to_db",
        lambda: {
            "ok": True,
            "datasets": {
                "glukoza_libre": {"fetched": 10, "inserted": 3, "updated": 2, "unchanged": 5},
            },
        },
    )

    result = sync_libre_data(trigger="test")

    assert result["changed"] is True
    assert result["totals"] == {"fetched": 10, "inserted": 3, "updated": 2, "unchanged": 5}
    assert sync_has_changes(result) is True

    status = get_sync_status()
    assert status["last_status"] == "success:test"
    assert status["last_inserted"] == 3
    assert status["last_updated"] == 2

    mark_summary_refreshed()
    status = get_sync_status()
    assert status["last_summary_refresh_at"] == fixed_now.isoformat()
