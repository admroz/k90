import sqlite3
import pytest


def db():
    from k90_memory import initialize
    conn = sqlite3.connect(':memory:')
    initialize(conn)
    conn.commit()
    return conn


def test_source_outbox_rollback_and_owner_history():
    from k90_memory import upsert_source, delete_source, hydrate, SourceRef
    c = db()
    first = upsert_source(c, 's1', 'alice', 'user', 'spacer', '2026-01-01T12:00:00Z')
    assert first.revision == 1
    assert c.in_transaction
    c.rollback()
    assert c.execute('SELECT count(*) FROM memory_sources').fetchone()[0] == 0
    assert c.execute('SELECT count(*) FROM memory_outbox').fetchone()[0] == 0
    first = upsert_source(c, 's1', 'alice', 'user', 'spacer', '2026-01-01T12:00:00Z')
    c.commit()
    second = upsert_source(c, 's1', 'alice', 'assistant', 'proponuję spacer', '2026-01-02T12:00:00Z')
    assert second.revision == 2 and second.role == 'assistant'
    assert hydrate(c, 'alice', [SourceRef('s1', 1)]) == []
    assert hydrate(c, 'bob', [SourceRef('s1', 2)]) == []
    assert hydrate(c, 'alice', [SourceRef('s1', 2)])[0].content == 'proponuję spacer'
    delete_source(c, 's1', 'alice')
    assert hydrate(c, 'alice', [SourceRef('s1', 3)]) == []
    assert c.execute('SELECT count(*) FROM memory_versions').fetchone()[0] == 3
    assert c.execute('SELECT content FROM memory_versions WHERE revision=1').fetchone()[0] == 'spacer'


def test_search_safe_match_owner_fallback_and_atomic_failure():
    from k90_memory import search_local, upsert_source
    c = db()
    for owner in ('alice', 'bob'):
        upsert_source(c, owner, owner, 'user', 'spacer codziennie', '2026-01-01')
    c.commit()
    assert [s.owner for s in search_local(c, 'alice', 'spacer', 5)] == ['alice']
    for query in ('\" OR * NOT ()', 'spacer\" OR owner:bob', '*', '', '"'):
        assert all(s.owner == 'alice' for s in search_local(c, 'alice', query, 5))
    c.execute('DROP TABLE memory_fts')
    assert len(search_local(c, 'alice', 'spacer', 5)) == 1
    assert search_local(c, 'alice', '%', 5) == []
    c.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON memory_outbox BEGIN SELECT RAISE(ABORT, 'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        upsert_source(c, 'broken', 'alice', 'user', 'spacer', '2026-01-01')
    assert c.execute("SELECT count(*) FROM memory_sources WHERE source_id='broken'").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM memory_versions WHERE source_id='broken'").fetchone()[0] == 0


def test_rebuild_only_active_requested_owner():
    from k90_memory import upsert_source, rebuild_queue, delete_source
    c = db()
    for sid, owner in [('1', 'alice'), ('2', 'alice'), ('3', 'bob')]:
        upsert_source(c, sid, owner, 'user', 'walking', '2026-01-01')
    delete_source(c, '2', 'alice')
    c.execute('DELETE FROM memory_outbox')
    assert rebuild_queue(c, 'alice') == 1
    assert c.execute('SELECT owner,source_id,revision FROM memory_outbox').fetchall() == [('alice', '1', 1)]
    c.rollback()
    assert c.execute('SELECT count(*) FROM memory_sources').fetchone()[0] == 0


def test_sources_have_boolean_flags_and_hydration_bounds_candidates():
    from k90_memory import upsert_source, hydrate, SourceRef
    c = db()
    upsert_source(c, 's', 'alice', 'user', 'text', '2026-01-01')
    source = hydrate(c, 'alice', [SourceRef('s', 1)])[0]
    assert source.local_only is False and source.deleted is False
    seen = []
    def refs():
        for i in range(2000):
            seen.append(i)
            yield SourceRef('missing', 1)
    assert hydrate(c, 'alice', refs(), limit=1) == []
    assert len(seen) <= 1000


def test_initialize_does_not_commit_caller_transaction():
    from k90_memory import initialize
    c = sqlite3.connect(':memory:')
    c.execute('CREATE TABLE caller(x)')
    c.execute('INSERT INTO caller VALUES (1)')
    initialize(c)
    c.rollback()
    assert c.execute('SELECT count(*) FROM caller').fetchone()[0] == 0
