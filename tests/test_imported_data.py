"""Optional verification of a user-downloaded backup, always on a temporary copy.

K90_TEST_IMPORT=data/local-import.20260920 pytest -q tests/test_imported_data.py
"""

import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dev import clone_snapshot
from webapp import create_app


@pytest.mark.skipif(not os.getenv("K90_TEST_IMPORT"), reason="No local import selected")
def test_downloaded_backup_serves_every_view_without_modifying_source(
    tmp_path, monkeypatch
):
    source = Path(os.environ["K90_TEST_IMPORT"]).resolve()
    original_files = [source / "k90.db", *source.glob("*.md")]
    before = {
        path: hashlib.sha256(path.read_bytes()).digest() for path in original_files
    }
    working = tmp_path / "working"
    clone_snapshot(source, working)
    monkeypatch.setenv("DB_PATH", str(working / "k90.db"))
    monkeypatch.setenv("DATA_DIR", str(working))
    monkeypatch.setenv("WEB_PASSWORD", "local-import-test-password")
    monkeypatch.setenv("WEB_COOKIE_SECURE", "false")
    monkeypatch.setenv("K90_PREVIEW", "true")
    monkeypatch.setenv("K90_SYNC_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ENABLED", "false")
    with TestClient(create_app(start_worker=False)) as client:
        assert (
            client.post(
                "/api/login",
                json={"password": "local-import-test-password"},
                headers={"X-K90-Request": "1"},
            ).status_code
            == 200
        )
        for days in (7, 30, 90, 365):
            assert client.get(f"/api/dashboard?days={days}").status_code == 200
        for table in client.get("/api/tables").json():
            assert client.get(f"/api/tables/{table}").status_code == 200
        for document in client.get("/api/documents").json():
            assert client.get(f"/api/documents/{document}").status_code == 200
        assert client.get("/api/messages").status_code == 200
        assert client.get("/api/meals").status_code == 200
        assert client.get("/api/jobs").json() == []
    assert {
        path: hashlib.sha256(path.read_bytes()).digest() for path in original_files
    } == before
