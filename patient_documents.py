"""Canonical patient documents in the application SQLite database.

Markdown files are legacy import inputs, never live mirrors. Schema helpers do
not commit: callers can include document changes in their own transactions.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import stat

DOCUMENT_NAMES = ("pacjent.md", "wywiad.md", "analiza.md", "dieta.md", "tydzien.md")


def validate_filename(filename: str) -> None:
    if filename not in DOCUMENT_NAMES:
        raise ValueError("Nieznany dokument pacjenta")


def ensure_schema(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS patient_documents (
        filename TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS patient_document_revisions (
        filename TEXT NOT NULL,
        revision INTEGER NOT NULL CHECK (revision >= 1),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        origin TEXT NOT NULL,
        PRIMARY KEY (filename, revision),
        FOREIGN KEY (filename) REFERENCES patient_documents(filename)
    )""")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _import_one(conn, filename: str, data_dir: Path) -> None:
    if conn.execute("SELECT 1 FROM patient_documents WHERE filename = ?", (filename,)).fetchone():
        return
    path = Path(data_dir) / filename
    # O_NOFOLLOW plus fstat prevents following links or reading nonregular files.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError("Niedozwolona ścieżka dokumentu") from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ValueError("Niedozwolona ścieżka dokumentu")
    with os.fdopen(fd, "r", encoding="utf-8", newline="") as source:
        content = source.read()
    timestamp = datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(timespec="microseconds")
    conn.execute("INSERT INTO patient_documents VALUES (?, ?, 1, ?, ?)", (filename, content, timestamp, timestamp))
    conn.execute("INSERT INTO patient_document_revisions VALUES (?, 1, ?, ?, 'markdown-import')", (filename, content, timestamp))
    from memory_runtime import document_changed
    document_changed(conn, filename, content, 1, timestamp)


def import_markdown(conn, data_dir: Path) -> None:
    """Import only absent documents; preserve originals, including empty files."""
    ensure_schema(conn)
    for filename in DOCUMENT_NAMES:
        _import_one(conn, filename, data_dir)


def get_document(filename: str, *, data_dir: Path | None = None) -> dict | None:
    from tools.db import get_conn, get_data_dir

    validate_filename(filename)
    with closing(get_conn()) as conn, conn:
        ensure_schema(conn)
        # Serialize check/import with writers; old files never replace DB rows.
        conn.execute("BEGIN IMMEDIATE")
        _import_one(conn, filename, get_data_dir() if data_dir is None else data_dir)
        row = conn.execute("SELECT * FROM patient_documents WHERE filename = ?", (filename,)).fetchone()
        return dict(row) if row else None


def write_document(filename: str, content: str, *, data_dir: Path | None = None) -> dict:
    from tools.db import get_conn, get_data_dir

    validate_filename(filename)
    if not isinstance(content, str):
        raise ValueError("Treść dokumentu musi być tekstem")
    with closing(get_conn()) as conn, conn:
        ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        _import_one(conn, filename, get_data_dir() if data_dir is None else data_dir)
        previous = conn.execute("SELECT * FROM patient_documents WHERE filename = ?", (filename,)).fetchone()
        if previous and previous["content"] == content:
            return dict(previous)
        timestamp = _now()
        revision = previous["revision"] + 1 if previous else 1
        created = previous["created_at"] if previous else timestamp
        conn.execute("""INSERT INTO patient_documents VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET content=excluded.content,
            revision=excluded.revision, updated_at=excluded.updated_at""",
            (filename, content, revision, created, timestamp))
        conn.execute("INSERT INTO patient_document_revisions VALUES (?, ?, ?, ?, 'update')", (filename, revision, content, timestamp))
        from memory_runtime import document_changed
        document_changed(conn, filename, content, revision, timestamp)
        return dict(conn.execute("SELECT * FROM patient_documents WHERE filename = ?", (filename,)).fetchone())


def get_revisions(filename: str) -> list[dict]:
    from tools.db import get_conn

    validate_filename(filename)
    with closing(get_conn()) as conn:
        ensure_schema(conn)
        return [dict(row) for row in conn.execute("SELECT * FROM patient_document_revisions WHERE filename = ? ORDER BY revision", (filename,))]


def export_documents(destination: Path, *, data_dir: Path | None = None) -> list[str]:
    """Export five current Markdown documents into a NEW private directory.

    Missing documents become empty export files. Revisions remain in SQLite;
    this is an explicit content export, not a complete application backup.
    Existing paths and symlinked ancestors are rejected, never overwritten.
    """
    from tools.db import get_conn, get_data_dir

    destination = Path(os.path.abspath(destination))
    if destination.resolve() != destination:
        raise ValueError("Eksport nie może używać dowiązań symbolicznych")
    if destination.exists():
        raise FileExistsError(destination)
    with closing(get_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        import_markdown(conn, get_data_dir() if data_dir is None else data_dir)
        contents = {row["filename"]: row["content"] for row in conn.execute("SELECT filename, content FROM patient_documents")}
    # Pin every ancestor from the filesystem root: leaf-only O_NOFOLLOW does
    # not protect an absolute path whose writable parent is replaced by a link.
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(destination.anchor, directory_flags)
    try:
        for component in destination.parts[1:-1]:
            child = os.open(component, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = child
        os.mkdir(destination.name, mode=0o700, dir_fd=parent)
        directory = os.open(destination.name, directory_flags, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        for filename in DOCUMENT_NAMES:
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
                target.write(contents.get(filename, ""))
                target.flush()
                os.fsync(target.fileno())
    finally:
        os.close(directory)
    return list(DOCUMENT_NAMES)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Eksport pięciu dokumentów pacjenta z SQLite do nowego prywatnego katalogu")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export_documents(args.destination)
