"""Local originals are authoritative. Mutators never commit the caller's connection."""
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3
import uuid


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    revision: int


@dataclass(frozen=True)
class Source:
    source_id: str
    owner: str
    revision: int
    role: str
    content: str
    occurred_at: str
    kind: str = 'conversation'
    local_only: bool = False
    deleted: bool = False


COLUMNS = 'source_id,owner,revision,role,content,occurred_at,kind,local_only,deleted'


def _source(row):
    if row is None:
        return None
    values = list(row)
    values[7], values[8] = bool(values[7]), bool(values[8])
    return Source(*values)


@contextmanager
def atomic(conn):
    # Explicit BEGIN keeps RELEASE from committing an otherwise standalone savepoint.
    if not conn.in_transaction:
        conn.execute('BEGIN')
    name = 'memory_' + uuid.uuid4().hex
    conn.execute('SAVEPOINT ' + name)
    try:
        yield
    except BaseException:
        conn.execute('ROLLBACK TO ' + name)
        conn.execute('RELEASE ' + name)
        raise
    else:
        conn.execute('RELEASE ' + name)


def initialize(conn):
    """Idempotent schema; no executescript, implicit commits, imports or network."""
    statements = [
        '''CREATE TABLE IF NOT EXISTS memory_sources (
        source_id TEXT NOT NULL, owner TEXT NOT NULL, revision INTEGER NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, occurred_at TEXT NOT NULL,
        kind TEXT NOT NULL, local_only INTEGER NOT NULL, deleted INTEGER NOT NULL,
        PRIMARY KEY(owner,source_id))''',
        '''CREATE TABLE IF NOT EXISTS memory_versions (
        source_id TEXT NOT NULL, owner TEXT NOT NULL, revision INTEGER NOT NULL,
        role TEXT NOT NULL, content TEXT NOT NULL, occurred_at TEXT NOT NULL,
        kind TEXT NOT NULL, local_only INTEGER NOT NULL, deleted INTEGER NOT NULL,
        PRIMARY KEY(owner,source_id,revision))''',
        '''CREATE TABLE IF NOT EXISTS memory_outbox (
        id INTEGER PRIMARY KEY, owner TEXT NOT NULL, source_id TEXT NOT NULL,
        revision INTEGER NOT NULL, operation TEXT NOT NULL DEFAULT 'retain',
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL DEFAULT 0,
        lease_until REAL NOT NULL DEFAULT 0, token TEXT, error TEXT)''',
        'CREATE INDEX IF NOT EXISTS memory_outbox_ready ON memory_outbox(status,available_at,lease_until)',
    ]
    with atomic(conn):
        for statement in statements:
            conn.execute(statement)
        try:
            conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(owner UNINDEXED, source_id UNINDEXED, content)')
        except sqlite3.OperationalError as exc:
            if 'no such module' not in str(exc).lower():
                raise


def current(conn, owner, source_id):
    return _source(conn.execute(f'SELECT {COLUMNS} FROM memory_sources WHERE owner=? AND source_id=?', (owner, source_id)).fetchone())


def _enqueue(conn, source):
    conn.execute("UPDATE memory_outbox SET status='superseded',token=NULL WHERE owner=? AND source_id=? AND operation='retain' AND status IN ('pending','retry')", (source.owner, source.source_id))
    operation = 'delete' if source.deleted else 'retain'
    conn.execute('INSERT INTO memory_outbox(owner,source_id,revision,operation) VALUES (?,?,?,?)', (source.owner, source.source_id, source.revision, operation))


def _write(conn, source):
    values = tuple(getattr(source, k) for k in COLUMNS.split(','))
    conn.execute(f'INSERT OR REPLACE INTO memory_sources({COLUMNS}) VALUES ({",".join("?" for _ in values)})', values)
    conn.execute(f'INSERT INTO memory_versions({COLUMNS}) VALUES ({",".join("?" for _ in values)})', values)
    has_fts = conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_fts'").fetchone()
    if has_fts:
        conn.execute('DELETE FROM memory_fts WHERE owner=? AND source_id=?', (source.owner, source.source_id))
        if not source.deleted:
            conn.execute('INSERT INTO memory_fts(owner,source_id,content) VALUES (?,?,?)', (source.owner, source.source_id, source.content))
    if source.revision > 1:
        conn.execute("INSERT INTO memory_outbox(owner,source_id,revision,operation) VALUES (?,?,?,'delete')", (source.owner, source.source_id, source.revision - 1))
    _enqueue(conn, source)
    return source


def upsert_source(conn, source_id, owner, role, content, occurred_at, kind='conversation', local_only=False):
    if not all(isinstance(v, str) and v for v in (source_id, owner, role, occurred_at, kind)) or not isinstance(content, str):
        raise ValueError('invalid source')
    if role not in ('user', 'assistant', 'system', 'tool', 'document') or type(local_only) is not bool:
        raise ValueError('invalid source')
    with atomic(conn):
        old = current(conn, owner, source_id)
        source = Source(source_id, owner, old.revision + 1 if old else 1, role, content, occurred_at, kind, local_only)
        return _write(conn, source)


def delete_source(conn, source_id, owner):
    """Append a tombstone without erasing any historical source text."""
    with atomic(conn):
        old = current(conn, owner, source_id)
        if old is None or old.deleted:
            return old
        return _write(conn, Source(old.source_id, old.owner, old.revision + 1, old.role, old.content, old.occurred_at, old.kind, old.local_only, True))


def rebuild_queue(conn, owner):
    """Re-index current active sources; does not import history or contact a backend."""
    with atomic(conn):
        sources = conn.execute(f'SELECT {COLUMNS} FROM memory_sources WHERE owner=? AND deleted=0', (owner,)).fetchall()
        for row in sources:
            _enqueue(conn, _source(row))
        return len(sources)


def search_local(conn, owner, query, limit=20):
    import re
    limit = max(0, min(int(limit), 100))
    tokens = re.findall(r'\w+', str(query)[:4096], re.UNICODE)[:32]
    if not tokens or not limit:
        return []
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='memory_fts'").fetchone():
        match = ' AND '.join('"' + token.replace('"', '""') + '"' for token in tokens)
        rows = conn.execute('''SELECT s.source_id,s.revision FROM memory_fts f
            JOIN memory_sources s ON s.owner=f.owner AND s.source_id=f.source_id
            WHERE memory_fts MATCH ? AND s.owner=? AND s.deleted=0
            ORDER BY rank,s.source_id LIMIT ?''', (match, owner, limit)).fetchall()
    else:
        # Bound result count and parameterize literal terms, not LIKE wildcards.
        clauses = ' AND '.join('instr(lower(content),lower(?))>0' for _ in tokens)
        rows = conn.execute(f'''SELECT source_id,revision FROM memory_sources
            WHERE owner=? AND deleted=0 AND {clauses}
            ORDER BY occurred_at DESC,source_id LIMIT ?''', (owner, *tokens, limit)).fetchall()
    return hydrate(conn, owner, [SourceRef(*row) for row in rows], limit)


def hydrate(conn, owner, refs, limit=20):
    from itertools import islice
    result, seen = [], set()
    for ref in islice(refs, 1000):
        if len(result) >= max(0, min(limit, 100)):
            break
        if not isinstance(ref, SourceRef) or ref.source_id in seen:
            continue
        source = current(conn, owner, ref.source_id)
        if source and not source.deleted and source.revision == ref.revision:
            result.append(source)
            seen.add(ref.source_id)
    return result
