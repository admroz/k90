import sqlite3
import pytest

from k90_memory import initialize, upsert_source, delete_source, rebuild_queue

KEY = b'fictional-test-key-not-a-secret!!'


class FakeBackend:
    def __init__(self):
        self.docs = {}
        self.retained = []
        self.deleted = []
        self.fail = False
        self.hook = None
    def retain(self, document):
        self.retained.append(document)
        if self.hook:
            self.hook()
        if self.fail:
            raise TimeoutError('patient body must not be saved')
        self.docs[document.document_id] = document
    def delete(self, document_id):
        self.deleted.append(document_id)
        self.docs.pop(document_id, None)
    def recall(self, owner_tag, query, limit):
        from k90_memory import SourceRef
        if self.fail:
            raise TimeoutError('private')
        return [SourceRef(d.source_id, d.revision) for d in self.docs.values() if d.owner_tag == owner_tag][:limit]


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / 'memory.sqlite'
    def get_conn():
        c = sqlite3.connect(path, timeout=0.05)
        return c
    c = get_conn()
    initialize(c)
    c.commit()
    c.close()
    return get_conn, FakeBackend()


def add(factory, content='spacer test@example.invalid', source_id='s1', owner='alice', **kw):
    c = factory()
    s = upsert_source(c, source_id, owner, 'user', content, '2026-01-01T12:00:00Z', **kw)
    c.commit()
    c.close()
    return s


def test_worker_retry_restart_ack_lease_and_no_lock_during_network(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    now = [100.0]
    worker = Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0], lease_seconds=10, retry_seconds=2)
    backend.fail = True
    def write_during_network():
        c = factory()
        c.execute('BEGIN IMMEDIATE')
        c.rollback()
        c.close()
    backend.hook = write_during_network
    assert worker.run_once(limit=1) == 1
    c = factory()
    row = c.execute('SELECT status,attempts,error FROM memory_outbox').fetchone()
    assert row == ('retry', 1, 'backend_unavailable')
    c.close()
    assert worker.run_once() == 0
    backend.fail = False
    now[0] += 3
    restarted = Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0])
    assert restarted.run_once(limit=1) == 1
    assert len(backend.docs) == 1
    assert backend.retained[0].document_id == backend.retained[1].document_id
    assert backend.retained[0].content == 'spacer [REDACTED]'
    c = factory()
    assert c.execute('SELECT status FROM memory_outbox').fetchone()[0] == 'done'
    assert c.execute('SELECT content FROM memory_sources').fetchone()[0] == 'spacer test@example.invalid'
    c.close()


def test_crash_after_retain_reclaimed_after_lease(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    now = [100.0]
    w = Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0], lease_seconds=10)
    def crash():
        raise KeyboardInterrupt()
    backend.hook = crash
    with pytest.raises(KeyboardInterrupt):
        w.run_once(limit=1)
    backend.hook = None
    assert w.run_once() == 0
    now[0] += 11
    assert w.run_once() == 1
    assert backend.retained[0].document_id == backend.retained[1].document_id


def test_stale_inflight_job_cannot_overwrite_correction_or_tombstone(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory, 'old text')
    worker = Worker(factory, backend, pseudonym_key=KEY)
    def correct_during_retain():
        backend.hook = None
        add(factory, 'new text')
        # Another worker processes a newer version while old request is in flight.
        Worker(factory, backend, pseudonym_key=KEY).run_once(limit=10)
    backend.hook = correct_during_retain
    worker.run_once(limit=10)
    worker.run_once(limit=10)
    assert [d.content for d in backend.docs.values()] == ['new text']
    c = factory()
    delete_source(c, 's1', 'alice')
    c.commit()
    c.close()
    worker.run_once(limit=10)
    assert backend.docs == {}


def test_superseded_jobs_batch_limit_rebuild_and_blocked_content(setup):
    from k90_memory import Worker, PrivacyPolicy
    factory, backend = setup
    for text in ('old', 'new'):
        add(factory, text)
    add(factory, 'Bearer never-send', source_id='secret')
    add(factory, 'local document', source_id='private', local_only=True)
    add(factory, 'photo', source_id='image', kind='image')
    worker = Worker(factory, backend, pseudonym_key=KEY, policy=PrivacyPolicy())
    assert worker.run_once(limit=1) == 1
    worker.run_once(limit=20)
    assert [d.content for d in backend.docs.values()] == ['new']
    assert all(d.owner_tag != 'alice' for d in backend.retained)
    c = factory()
    assert c.execute("SELECT count(*) FROM memory_outbox WHERE status='blocked'").fetchone()[0] == 3
    backend.docs.clear()
    assert rebuild_queue(c, 'alice') == 4
    c.commit()
    c.close()
    worker.run_once(limit=20)
    assert [d.content for d in backend.docs.values()] == ['new']


def test_policy_bug_sends_nothing_and_errors_are_fixed(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    class Broken:
        def sanitize(self, value):
            raise RuntimeError('sensitive input')
    Worker(factory, backend, pseudonym_key=KEY, policy=Broken()).run_once()
    assert backend.retained == []
    c = factory()
    assert c.execute('SELECT status,error FROM memory_outbox').fetchone() == ('blocked', 'privacy_blocked')
    c.close()


def test_invalid_filter_return_never_leaks_pii(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    class IdentityFilter:
        def sanitize(self, value):
            return value
    Worker(factory, backend, pseudonym_key=KEY, policy=IdentityFilter()).run_once()
    assert backend.retained[0].content == 'spacer [REDACTED]'


def test_ack_crash_replays_exact_document_after_restart(setup, monkeypatch):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    now = [100.0]
    w = Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0], lease_seconds=1)
    monkeypatch.setattr(w, '_finish', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        w.run_once(limit=1)
    assert len(backend.docs) == 1
    now[0] += 2
    Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0]).run_once(limit=1)
    assert len(backend.docs) == 1
    assert backend.retained[0] == backend.retained[1]


def test_expired_claim_cannot_ack_or_retry_a_new_claim(setup):
    from k90_memory import Worker
    factory, backend = setup
    add(factory)
    now = [100.0]
    w = Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0], lease_seconds=1)
    def newer_claim_completes():
        backend.hook = None
        now[0] += 2
        Worker(factory, backend, pseudonym_key=KEY, clock=lambda: now[0]).run_once(limit=1)
        raise TimeoutError('old acknowledgement lost')
    backend.hook = newer_claim_completes
    assert w.run_once(limit=1) == 1
    c = factory()
    assert c.execute('SELECT status,attempts,error FROM memory_outbox').fetchone() == ('done', 2, None)
    c.close()


def test_retrieve_policy_failure_calls_no_remote(setup):
    from k90_memory import retrieve
    factory, backend = setup
    add(factory, 'spacer')
    calls = []
    backend.recall = lambda *args: calls.append(args)
    class Broken:
        def sanitize_text(self, value):
            raise ValueError('private')
    c = factory()
    assert len(retrieve(c, 'alice', 'spacer', backend=backend, pseudonym_key=KEY, policy=Broken())) == 1
    assert calls == []
    c.close()


def test_retrieve_hydrates_current_owner_with_local_fallback(setup):
    from k90_memory import retrieve, SourceRef
    factory, backend = setup
    add(factory, 'spacer dzienny')
    add(factory, 'spacer inny', source_id='s2', owner='bob')
    backend.fail = True
    c = factory()
    results = retrieve(c, 'alice', 'spacer', backend=backend, pseudonym_key=KEY)
    assert [s.source_id for s in results] == ['s1']
    backend.fail = False
    backend.recall = lambda *a: [SourceRef('s2', 1), SourceRef('s1', 99), SourceRef('s1', 1)]
    assert [s.source_id for s in retrieve(c, 'alice', 'spacer', backend=backend, pseudonym_key=KEY)] == ['s1']
    c.close()
