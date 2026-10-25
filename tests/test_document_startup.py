"""Startup must migrate every Markdown document before a database-only backup."""
import sqlite3

from patient_documents import DOCUMENT_NAMES
from tools.db import create_db_backup, get_conn, get_data_dir, init_db


def test_startup_imports_all_legacy_documents_before_first_document_read(temp_db):
    data = get_data_dir()
    for name in DOCUMENT_NAMES:
        (data/name).write_text('synthetic legacy: '+name, encoding='utf-8')
    init_db()
    backup = create_db_backup()
    with sqlite3.connect(str(backup['path'])) as conn:
        rows = dict(conn.execute('SELECT filename,content FROM patient_documents'))
        revisions = conn.execute('SELECT count(*) FROM patient_document_revisions').fetchone()[0]
    assert rows == {name:'synthetic legacy: '+name for name in DOCUMENT_NAMES}
    assert revisions == 5
    # Subsequent startup must not restore obsolete Markdown over current SQLite.
    with get_conn() as conn:
        conn.execute("UPDATE patient_documents SET content='synthetic canonical' WHERE filename='pacjent.md'")
    init_db()
    with get_conn() as conn:
        assert conn.execute("SELECT content FROM patient_documents WHERE filename='pacjent.md'").fetchone()[0] == 'synthetic canonical'
