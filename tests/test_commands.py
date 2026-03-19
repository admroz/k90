from __future__ import annotations

import os
import time
from pathlib import Path

from tools.commands import _backup, _update, handle_command
from tools.db import create_db_backup


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


def test_backup_command_routes_to_backup_handler(monkeypatch):
    monkeypatch.setattr("tools.commands._backup", lambda: "ok")

    assert handle_command("/backup") == "ok"


def test_backup_formats_snapshot_response(monkeypatch):
    monkeypatch.setattr(
        "tools.commands.create_db_backup",
        lambda: {
            "filename": "k90-2026-03-19_22-15-00.db",
            "backup_dir": "/tmp/backups",
            "created_at": "2026-03-19T22:15:00+01:00",
            "timezone": "Europe/Warsaw",
            "size_bytes": 4096,
            "retention_days": 30,
            "deleted_old": 2,
        },
    )

    result = _backup()

    assert "/backup: snapshot zapisany" in result
    assert "Plik: k90-2026-03-19_22-15-00.db" in result
    assert "Retencja: 30 dni" in result
    assert "Usuniete stare backupy: 2" in result


def test_create_db_backup_creates_snapshot_and_prunes_old_files(temp_db, monkeypatch):
    backup_dir = Path(os.environ["DATA_DIR"]) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    old_backup = backup_dir / "test-older.db"
    old_backup.write_text("stary backup")
    old_timestamp = time.time() - 3 * 24 * 60 * 60
    os.utime(old_backup, (old_timestamp, old_timestamp))

    result = create_db_backup(retention_days=1)

    backup_path = Path(result["path"])
    assert backup_path.exists()
    assert backup_path.parent == backup_dir
    assert result["timezone"] == "Europe/Warsaw"
    assert result["retention_days"] == 1
    assert result["deleted_old"] == 1
    assert not old_backup.exists()
