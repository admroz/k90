"""Synthetic-only document migration and shared-store regression tests."""
from contextlib import closing
from pathlib import Path
import sqlite3
import pytest

import patient_documents as documents

from tools import patient
from tools.db import get_conn, get_data_dir


def test_tools_import_once_and_write_only_sqlite(temp_db, monkeypatch):
    monkeypatch.setattr(patient, "DATA_DIR", get_data_dir())
    source = get_data_dir() / "pacjent.md"
    source.write_text("legacy profile", encoding="utf-8")
    assert patient.read_patient_file("pacjent.md")["content"] == "legacy profile"
    assert patient.update_patient_file("pacjent.md", "canonical profile")["ok"]
    assert source.read_text() == "legacy profile"
    source.write_text("stale legacy", encoding="utf-8")
    assert patient.read_patient_file("pacjent.md")["content"] == "canonical profile"
    with closing(get_conn()) as conn:
        assert conn.execute("SELECT content FROM patient_documents WHERE filename = 'pacjent.md'").fetchone()[0] == "canonical profile"


def test_panel_summary_and_tools_share_canonical_documents(temp_db, monkeypatch):
    import summary
    import web_data
    monkeypatch.setattr(patient, "DATA_DIR", get_data_dir())
    monkeypatch.setattr(summary, "DATA_DIR", get_data_dir())
    (get_data_dir() / "pacjent.md").write_text("obsolete")
    assert patient.update_patient_file("pacjent.md", "shared canonical")["ok"]
    assert web_data.document("pacjent.md")["content"] == "shared canonical"
    parts, contents = summary._load_patient_parts()
    assert contents == {"pacjent.md": "shared canonical"}
    assert parts == ["=== pacjent.md ===\nshared canonical"]
    assert web_data.document("wywiad.md") == {"name": "wywiad.md", "content": "", "updated_at": None}


def test_explicit_export_is_private_five_files_and_never_overwrites(temp_db, tmp_path):
    export = getattr(documents, "export_documents", None)
    assert callable(export), "an explicit safe Markdown export is required"
    documents.write_document("pacjent.md", "Canonical Polish: żółć")
    documents.write_document("dieta.md", "")
    destination = tmp_path / "export"
    result = export(destination)
    assert set(result) == set(documents.DOCUMENT_NAMES)
    assert {item.name for item in destination.iterdir()} == set(documents.DOCUMENT_NAMES)
    assert (destination / "pacjent.md").read_text() == "Canonical Polish: żółć"
    assert (destination / "wywiad.md").read_text() == ""
    assert destination.stat().st_mode & 0o777 == 0o700
    assert all((destination / name).stat().st_mode & 0o777 == 0o600 for name in result)
    with pytest.raises(FileExistsError):
        export(destination)
    with pytest.raises(FileExistsError):
        export(get_data_dir())
    link = tmp_path / "link"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError):
        export(link / "nested")
    assert not (destination / "nested").exists()


def test_export_does_not_follow_parent_swapped_after_validation(temp_db, tmp_path, monkeypatch):
    parent = tmp_path / "writable-parent"
    parent.mkdir()
    original = tmp_path / "original-parent"
    outside = tmp_path / "outside"
    outside.mkdir()
    documents.write_document("pacjent.md", "synthetic private content")
    import_markdown = documents.import_markdown
    swapped = False

    def swap_parent_after_validation(conn, data_dir):
        nonlocal swapped
        import_markdown(conn, data_dir)
        parent.rename(original)
        parent.symlink_to(outside, target_is_directory=True)
        swapped = True

    monkeypatch.setattr(documents, "import_markdown", swap_parent_after_validation)
    try:
        documents.export_documents(parent / "export")
    except (OSError, ValueError):
        pass  # Rejecting a substituted ancestor is safe too.
    assert swapped, "the race must occur after initial path validation"
    assert list(outside.iterdir()) == [], "export followed the substituted ancestor"
    if (original / "export").exists():
        assert {p.name for p in (original / "export").iterdir()} == set(documents.DOCUMENT_NAMES)
        assert (original / "export" / "pacjent.md").read_text() == "synthetic private content"


def test_import_preserves_exact_markdown_and_original_dates(temp_db):
    import os
    from datetime import datetime, timezone
    source = get_data_dir() / "wywiad.md"
    source.write_bytes("# Żółć\r\n\r\nTreść\r\n".encode())
    os.utime(source, (1600000000, 1600000000))
    document = documents.get_document("wywiad.md")
    assert document["content"] == "# Żółć\r\n\r\nTreść\r\n"
    assert datetime.fromisoformat(document["created_at"]) == datetime.fromtimestamp(1600000000, timezone.utc)
    assert document["updated_at"] == document["created_at"]
    assert documents.get_revisions("wywiad.md")[0]["origin"] == "markdown-import"


def test_demo_seed_uses_sqlite_without_markdown_mirrors(temp_db):
    from scripts.seed_demo import seed
    seed()
    assert not (get_data_dir() / "pacjent.md").exists()
    assert not (get_data_dir() / "analiza.md").exists()
    before = documents.get_document("pacjent.md")
    assert "demonstracyjny" in before["content"]
    documents.write_document("pacjent.md", "local edited demo")
    seed()
    assert documents.get_document("pacjent.md")["content"] == "local edited demo"


def test_snapshot_migrates_only_working_copy_and_keeps_db_authoritative(temp_db, tmp_path, monkeypatch):
    from dev import clone_snapshot
    source = tmp_path / "snapshot"
    source.mkdir()
    with closing(sqlite3.connect(source / "k90.db")) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
    (source / "pacjent.md").write_text("old snapshot document")
    before = (source / "k90.db").read_bytes()
    working = tmp_path / "working"
    clone_snapshot(source, working)
    assert (source / "k90.db").read_bytes() == before
    monkeypatch.setenv("DB_PATH", str(working / "k90.db"))
    monkeypatch.setenv("DATA_DIR", str(working))
    with closing(get_conn()) as conn:
        assert conn.execute("SELECT content FROM patient_documents WHERE filename='pacjent.md'").fetchone()[0] == "old snapshot document"
    documents.write_document("pacjent.md", "new snapshot document")
    second = tmp_path / "second"
    clone_snapshot(working, second)
    monkeypatch.setenv("DB_PATH", str(second / "k90.db"))
    monkeypatch.setenv("DATA_DIR", str(second))
    assert documents.get_document("pacjent.md")["content"] == "new snapshot document"
    assert [r["content"] for r in documents.get_revisions("pacjent.md")] == ["old snapshot document", "new snapshot document"]


def test_empty_missing_and_later_created_documents_are_distinct(temp_db):
    assert documents.get_document("tydzien.md") is None
    assert "error" in patient.read_patient_file("tydzien.md")
    (get_data_dir() / "tydzien.md").write_text("")
    empty = documents.get_document("tydzien.md")
    assert empty is not None and empty["content"] == "" and empty["revision"] == 1
    documents.write_document("tydzien.md", "")
    assert len(documents.get_revisions("tydzien.md")) == 1
    (get_data_dir() / "tydzien.md").write_text("late stale edit")
    assert documents.get_document("tydzien.md")["content"] == ""
    assert patient.update_patient_file("dieta.md", "new DB-only document")["ok"]
    assert not (get_data_dir() / "dieta.md").exists()


def test_revisions_are_durable_sequential_and_timestamped(temp_db):
    first = documents.write_document("analiza.md", "first")
    same = documents.write_document("analiza.md", "first")
    assert same == first
    second = documents.write_document("analiza.md", "second")
    third = documents.write_document("analiza.md", "")
    assert second["created_at"] == third["created_at"] == first["created_at"]
    assert first["updated_at"] <= second["updated_at"] <= third["updated_at"]
    revisions = documents.get_revisions("analiza.md")
    assert [r["revision"] for r in revisions] == [1, 2, 3]
    assert [r["content"] for r in revisions] == ["first", "second", ""]
    assert [r["created_at"] for r in revisions] == [first["updated_at"], second["updated_at"], third["updated_at"]]


def test_schema_and_import_never_commit_callers_transaction(temp_db):
    (get_data_dir() / "wywiad.md").write_text("rollback me")
    with closing(get_conn()) as conn:
        conn.execute("CREATE TABLE caller_changes (value TEXT)")
        conn.execute("INSERT INTO caller_changes VALUES ('uncommitted')")
        documents.ensure_schema(conn)
        documents.import_markdown(conn, get_data_dir())
        assert conn.in_transaction
        conn.rollback()
        assert conn.execute("SELECT count(*) FROM caller_changes").fetchone()[0] == 0
        # Transactional DDL may itself be rolled back, so create it again.
        documents.ensure_schema(conn)
        assert conn.execute("SELECT count(*) FROM patient_documents").fetchone()[0] == 0
        documents.import_markdown(conn, get_data_dir())
        documents.import_markdown(conn, get_data_dir())
        conn.commit()
        assert conn.execute("SELECT count(*) FROM patient_document_revisions").fetchone()[0] == 1


@pytest.mark.parametrize("name", ["../pacjent.md", "/pacjent.md", "sub/pacjent.md", "sub\\pacjent.md", "pacjent.md\x00", "system_prompt.md", "unknown.md"])
def test_strict_allowlist_for_store_tools_and_panel(temp_db, name):
    import web_data
    assert "error" in patient.read_patient_file(name)
    assert "error" in patient.update_patient_file(name, "forbidden")
    for action in (documents.get_document, documents.get_revisions, web_data.document):
        with pytest.raises(ValueError):
            action(name)
    with pytest.raises(ValueError):
        documents.write_document(name, "forbidden")
    assert not (get_data_dir() / "system_prompt.md").exists()


@pytest.mark.parametrize("kind", ["symlink", "dangling", "directory", "fifo"])
def test_legacy_import_rejects_nonregular_paths_without_following(temp_db, tmp_path, kind):
    import os
    import web_data
    outside = tmp_path / "outside.md"
    outside.write_text("do not read or change")
    path = get_data_dir() / "pacjent.md"
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "dangling":
        path.symlink_to(tmp_path / "absent.md")
    elif kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    assert "error" in patient.read_patient_file("pacjent.md")
    assert "error" in patient.update_patient_file("pacjent.md", "forbidden")
    with pytest.raises(ValueError):
        web_data.document("pacjent.md")
    assert outside.read_text() == "do not read or change"
    assert documents.get_revisions("pacjent.md") == []


def test_db_document_ignores_even_symlinked_stale_source(temp_db, tmp_path):
    documents.write_document("pacjent.md", "DB authority")
    outside = tmp_path / "outside.md"
    outside.write_text("never import")
    (get_data_dir() / "pacjent.md").symlink_to(outside)
    assert documents.get_document("pacjent.md")["content"] == "DB authority"
    documents.write_document("pacjent.md", "new DB authority")
    assert outside.read_text() == "never import"


def test_sqlite_backup_restores_five_docs_all_revisions_without_markdown(temp_db, tmp_path, monkeypatch):
    from tools.db import create_db_backup
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    for name in documents.DOCUMENT_NAMES:
        (get_data_dir() / name).write_text("original " + name)
        documents.write_document(name, "canonical " + name)
        documents.write_document(name, "latest " + name)
    expected = {name: documents.get_document(name) for name in documents.DOCUMENT_NAMES}
    history = {name: documents.get_revisions(name) for name in documents.DOCUMENT_NAMES}
    backup = create_db_backup(retention_days=30)
    restored = tmp_path / "restored"
    restored.mkdir()
    with closing(sqlite3.connect(backup["path"])) as src, closing(sqlite3.connect(restored / "k90.db")) as dst:
        src.backup(dst)
    monkeypatch.setenv("DB_PATH", str(restored / "k90.db"))
    monkeypatch.setenv("DATA_DIR", str(restored))
    for name in documents.DOCUMENT_NAMES:
        assert documents.get_document(name) == expected[name]
        assert documents.get_revisions(name) == history[name]
        (restored / name).write_text("stale restored Markdown")
        assert documents.get_document(name) == expected[name]
    with closing(get_conn()) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_concurrent_writes_keep_each_revision_and_current_in_sync(temp_db):
    from concurrent.futures import ThreadPoolExecutor
    documents.write_document("analiza.md", "initial")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda i: documents.write_document("analiza.md", f"edit {i}"), range(12)))
    revisions = documents.get_revisions("analiza.md")
    assert [r["revision"] for r in revisions] == list(range(1, 14))
    assert {r["content"] for r in revisions[1:]} == {f"edit {i}" for i in range(12)}
    assert documents.get_document("analiza.md")["content"] == revisions[-1]["content"]


def test_failed_revision_insert_rolls_back_current_document(temp_db):
    original = documents.write_document("analiza.md", "original")
    with closing(get_conn()) as conn, conn:
        conn.execute("""CREATE TRIGGER reject_revision BEFORE INSERT ON patient_document_revisions
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        documents.write_document("analiza.md", "must roll back")
    assert documents.get_document("analiza.md") == original
    assert len(documents.get_revisions("analiza.md")) == 1


def test_export_cli_runs_only_on_explicit_temporary_database(temp_db, tmp_path):
    import os
    import subprocess
    import sys
    documents.write_document("pacjent.md", "explicit CLI fixture")
    target = tmp_path / "cli-export"
    result = subprocess.run(
        [sys.executable, "-m", "patient_documents", str(target)],
        cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "pacjent.md").read_text() == "explicit CLI fixture"
    assert len(list(target.iterdir())) == 5
