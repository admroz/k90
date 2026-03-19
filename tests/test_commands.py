from __future__ import annotations

from tools.commands import _update


def test_update_skips_summary_refresh_when_sync_has_no_changes(monkeypatch):
    monkeypatch.setattr(
        "tools.commands.sync_garmin_data",
        lambda trigger="slash_update": {
            "ok": True,
            "changed": False,
            "datasets": {"waga": {"fetched": 1, "inserted": 0, "updated": 0, "unchanged": 1}},
        },
    )
    monkeypatch.setattr(
        "tools.commands.sync_libre_data",
        lambda trigger="slash_update": {
            "ok": True,
            "changed": False,
            "datasets": {"glukoza_libre": {"fetched": 2, "inserted": 0, "updated": 0, "unchanged": 2}},
        },
    )
    monkeypatch.setattr("tools.commands.garmin_sync_has_changes", lambda result: False)
    monkeypatch.setattr("tools.commands.libre_sync_has_changes", lambda result: False)
    monkeypatch.setattr("tools.commands.refresh_patient_summary", lambda trigger="": (_ for _ in ()).throw(AssertionError("should not refresh")))
    monkeypatch.setattr("tools.commands.mark_garmin_summary_refreshed", lambda: (_ for _ in ()).throw(AssertionError("should not mark garmin")))

    result = _update()

    assert "Summary bez zmian." in result


def test_update_refreshes_summary_when_sync_has_changes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "tools.commands.sync_garmin_data",
        lambda trigger="slash_update": {
            "ok": True,
            "changed": True,
            "datasets": {"waga": {"fetched": 1, "inserted": 1, "updated": 0, "unchanged": 0}},
        },
    )
    monkeypatch.setattr(
        "tools.commands.sync_libre_data",
        lambda trigger="slash_update": {
            "ok": True,
            "changed": True,
            "datasets": {"glukoza_libre": {"fetched": 2, "inserted": 1, "updated": 0, "unchanged": 1}},
        },
    )
    monkeypatch.setattr("tools.commands.garmin_sync_has_changes", lambda result: True)
    monkeypatch.setattr("tools.commands.libre_sync_has_changes", lambda result: True)
    monkeypatch.setattr("tools.commands.refresh_patient_summary", lambda trigger="": calls.append(("refresh", trigger)))
    monkeypatch.setattr("tools.commands.mark_garmin_summary_refreshed", lambda: calls.append(("mark_garmin", None)))

    result = _update()

    assert ("refresh", "slash_update") in calls
    assert ("mark_garmin", None) in calls
    assert "Summary odświeżone po zmianach w danych: Garmin." in result
