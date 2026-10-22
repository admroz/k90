"""Local imports must never alter the backup downloaded by the user."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from dev import clone_snapshot


def test_working_copy_preserves_source_and_drops_pending_transport_jobs(tmp_path):
    source = tmp_path / "import"
    source.mkdir()
    with closing(sqlite3.connect(source / "k90.db")) as conn, conn:
        conn.execute("CREATE TABLE chat_jobs (id INTEGER)")
        conn.execute("INSERT INTO chat_jobs VALUES (1)")
        conn.execute("CREATE TABLE transport_state (name TEXT)")
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('original')")
    (source / "pacjent.md").write_text("Original document")
    (source / ".env").write_text("DO_NOT_COPY=secret")
    before = (source / "k90.db").read_bytes()
    working = tmp_path / "working"
    clone_snapshot(source, working)
    with closing(sqlite3.connect(working / "k90.db")) as conn, conn:
        conn.execute("UPDATE sample SET value = 'local edit'")
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name IN ('chat_jobs', 'transport_state')"
        ).fetchall()
    (working / "pacjent.md").write_text("Local edit")
    assert (source / "k90.db").read_bytes() == before
    assert (source / "pacjent.md").read_text() == "Original document"
    assert not (working / ".env").exists()
    with pytest.raises(FileExistsError):
        clone_snapshot(source, working)
    assert (working / "pacjent.md").read_text() == "Local edit"


def test_clone_reads_wal_and_keeps_original_bytes(tmp_path):
    source = tmp_path / "import"
    source.mkdir()
    db = source / "k90.db"
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('committed in WAL')")
        conn.commit()
        before_db, before_wal = db.read_bytes(), Path(str(db) + "-wal").read_bytes()
        working = tmp_path / "working"
        clone_snapshot(source, working)
        assert db.read_bytes() == before_db
        assert Path(str(db) + "-wal").read_bytes() == before_wal
        with closing(sqlite3.connect(working / "k90.db")) as copied:
            assert copied.execute("SELECT * FROM sample").fetchall() == [
                ("committed in WAL",)
            ]


def test_missing_database_cannot_create_source_or_working_copy(tmp_path):
    source, working = tmp_path / "missing", tmp_path / "working"
    with pytest.raises(ValueError):
        clone_snapshot(source, working)
    assert not source.exists()
    assert not working.exists()


def test_document_symlinks_are_not_imported(tmp_path):
    source = tmp_path / "import"
    source.mkdir()
    with closing(sqlite3.connect(source / "k90.db")) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
    outside = tmp_path / "private.md"
    outside.write_text("Do not follow symlinks")
    (source / "pacjent.md").symlink_to(outside)
    working = tmp_path / "working"
    clone_snapshot(source, working)
    assert not (working / "pacjent.md").exists()
