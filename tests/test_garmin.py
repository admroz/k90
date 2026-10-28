from __future__ import annotations

from datetime import datetime

import fetch_garmin
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
    monkeypatch.setenv("K90_SYNC_ENABLED", "true")  # Fetch boundary is mocked below.
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

    # Explicit opt-in only after the source function above is replaced by a fake.
    monkeypatch.setenv("K90_SYNC_ENABLED", "true")
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


def test_sync_garmin_to_db_uses_fresh_end_date_each_call(monkeypatch, temp_db):
    monkeypatch.setattr(fetch_garmin, "EMAIL", "user@example.com")
    monkeypatch.setattr(fetch_garmin, "PASSWORD", "secret")
    monkeypatch.setattr(fetch_garmin, "_default_end_date", lambda: "2026-03-19")
    monkeypatch.setattr(fetch_garmin, "login", lambda: object())
    monkeypatch.setattr(fetch_garmin, "create_schema", lambda conn: None)
    monkeypatch.setattr(fetch_garmin, "ensure_agent_tables", lambda conn: None)

    for name in (
        "fetch_weight",
        "fetch_blood_pressure",
        "fetch_activities",
        "fetch_sleep",
        "fetch_daily_metrics",
        "fetch_hrv",
        "fetch_body_battery",
        "fetch_daily_calories",
    ):
        monkeypatch.setattr(fetch_garmin, name, lambda client, start, end: [])

    result = fetch_garmin.sync_garmin_to_db(end_date=None)

    assert result["end_date"] == "2026-03-19"


def test_garmin_sync_converts_unexpected_exception_to_error(monkeypatch, temp_db):
    monkeypatch.setenv("K90_SYNC_ENABLED", "true")  # Fetch boundary is mocked below.
    monkeypatch.setattr(
        "tools.garmin.sync_garmin_to_db",
        lambda: (_ for _ in ()).throw(RuntimeError("rate limited")),
    )

    # Explicit opt-in only after the source function above is replaced by a fake.
    monkeypatch.setenv("K90_SYNC_ENABLED", "true")
    result = sync_garmin_data(trigger="test")

    assert result == {"error": "RuntimeError: rate limited"}
    assert get_sync_status()["last_status"] == "error:test"


def test_daily_calories_read_both_components_and_preserve_real_zero():
    from unittest.mock import Mock

    client = Mock()
    client.get_stats.return_value = {"calendarDate": "2026-10-24", "bmrKilocalories": 1950, "activeKilocalories": 0, "totalKilocalories": 1950}
    row = fetch_garmin.fetch_daily_calories(client, "2026-10-24", "2026-10-24")[0]
    assert row["spoczynkowe_kcal"] == 1950
    assert row["aktywne_kcal"] == 0
    assert row["calkowite_kcal"] == 1950
    assert row["pobrano_at"]
    client.get_stats.assert_called_once_with("2026-10-24")


def test_missing_or_invalid_calories_remain_unknown():
    from unittest.mock import Mock

    client = Mock()
    client.get_stats.side_effect = [{}, {"bmrKilocalories": -1, "activeKilocalories": float("nan"), "totalKilocalories": "bad"}]
    rows = fetch_garmin.fetch_daily_calories(client, "2026-10-23", "2026-10-24")
    assert [row["data"] for row in rows] == ["2026-10-23", "2026-10-24"]
    assert all(row[key] is None for row in rows for key in ("spoczynkowe_kcal", "aktywne_kcal", "calkowite_kcal"))


def test_historical_days_without_garmin_data_do_not_stop_backfill():
    from unittest.mock import Mock
    import garminconnect

    client = Mock()
    client.get_stats.side_effect = garminconnect.GarminConnectConnectionError("No data received from server")
    row = fetch_garmin.fetch_daily_calories(client, "2022-01-01", "2022-01-01")[0]
    assert row["data"] == "2022-01-01"
    assert row["spoczynkowe_kcal"] is None
    client.get_stats.side_effect = garminconnect.GarminConnectConnectionError("synthetic network outage")
    import pytest
    with pytest.raises(garminconnect.GarminConnectConnectionError):
        fetch_garmin.fetch_daily_calories(client, "2022-01-02", "2022-01-02")


def test_calorie_freshness_updates_without_marking_values_changed(temp_db):
    row = {"data": "2026-10-24", "spoczynkowe_kcal": 1900, "aktywne_kcal": 400, "calkowite_kcal": 2300, "pobrano_at": "first"}
    with get_conn() as conn:
        assert fetch_garmin._insert_or_update_many(conn, "kalorie_dzienne", [row])["inserted"] == 1
        row["pobrano_at"] = "second"
        stats = fetch_garmin._insert_or_update_many(conn, "kalorie_dzienne", [row])
        assert stats["updated"] == 0 and stats["unchanged"] == 1
        assert conn.execute("SELECT pobrano_at FROM kalorie_dzienne").fetchone()[0] == "second"


def test_calorie_backfill_commits_batches_and_resumes_after_failure(monkeypatch, temp_db):
    from unittest.mock import Mock

    monkeypatch.setattr(fetch_garmin, "EMAIL", "test@example.com")
    monkeypatch.setattr(fetch_garmin, "PASSWORD", "test")
    monkeypatch.setattr(fetch_garmin.time, "sleep", lambda _: None)
    for name in ("fetch_weight", "fetch_blood_pressure", "fetch_activities", "fetch_sleep", "fetch_daily_metrics", "fetch_hrv", "fetch_body_battery"):
        monkeypatch.setattr(fetch_garmin, name, lambda *args: [])
    client = Mock()
    requested = []

    def stats(day):
        requested.append(day)
        if day == "2022-01-31":
            raise RuntimeError("synthetic outage")
        return {"bmrKilocalories": 1900, "activeKilocalories": 100, "totalKilocalories": 2000}

    client.get_stats.side_effect = stats
    assert "error" in fetch_garmin.sync_garmin_to_db(client=client, end_date="2022-02-05")
    assert requested[0] == "2022-01-01"
    with get_conn() as conn:
        assert conn.execute("SELECT MAX(data) FROM kalorie_dzienne").fetchone()[0] == "2022-01-30"
        assert conn.execute("SELECT COUNT(*) FROM kalorie_dzienne").fetchone()[0] == 30
    requested.clear()
    client.get_stats.side_effect = lambda day: requested.append(day) or {"bmrKilocalories": 1900, "activeKilocalories": 200}
    result = fetch_garmin.sync_garmin_to_db(client=client, end_date="2022-02-05")
    assert result["ok"]
    assert requested[0] == "2022-01-23"
    with get_conn() as conn:
        assert conn.execute("SELECT MAX(data) FROM kalorie_dzienne").fetchone()[0] == "2022-02-05"
        assert conn.execute("SELECT COUNT(*) FROM kalorie_dzienne").fetchone()[0] == 36
