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
    monkeypatch.setattr("tools.commands.sync_has_changes", lambda result: False)
    monkeypatch.setattr("tools.commands.refresh_patient_summary", lambda trigger="": (_ for _ in ()).throw(AssertionError("should not refresh")))
    monkeypatch.setattr("tools.commands.mark_summary_refreshed", lambda: (_ for _ in ()).throw(AssertionError("should not mark")))

    result = _update()

    assert "Brak nowych zmian z Garmin, summary bez zmian." in result


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
    monkeypatch.setattr("tools.commands.sync_has_changes", lambda result: True)
    monkeypatch.setattr("tools.commands.refresh_patient_summary", lambda trigger="": calls.append(("refresh", trigger)))
    monkeypatch.setattr("tools.commands.mark_summary_refreshed", lambda: calls.append(("mark", None)))

    result = _update()

    assert ("refresh", "slash_update") in calls
    assert ("mark", None) in calls
    assert "Summary odświeżone po zmianach w danych Garmin." in result
