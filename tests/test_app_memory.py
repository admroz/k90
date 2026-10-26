"""Application wiring for the source ledger, with only synthetic local data."""
import importlib
import json

import pytest

from tools.db import get_conn


def test_incoming_original_and_outbox_commit_before_any_model_request(temp_db):
    runtime=importlib.import_module('memory_runtime')
    raw=[{'type':'text','text':'Synthetic grain preference'},
         {'type':'image_url','image_url':{'url':'data:image/png;base64,iVBORw0KGgpzeW50aGV0aWM='}}]
    turn=runtime.begin_turn('synthetic-owner',raw)
    with get_conn() as conn:
        event=conn.execute('SELECT payload FROM agent_events WHERE id=?',(turn['user_event_id'],)).fetchone()
        source=conn.execute('SELECT content FROM memory_sources WHERE source_id=?',(turn['source_id'],)).fetchone()
        assert json.loads(event[0])==raw
        assert source[0]=='Synthetic grain preference'
        assert conn.execute('SELECT count(*) FROM memory_outbox').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM conversations').fetchone()[0]==0


def test_recall_grounds_in_old_local_source_and_redacts_identifiers(temp_db,monkeypatch):
    runtime=importlib.import_module('memory_runtime')
    runtime.begin_turn('synthetic-owner','I choose millet for breakfast; synthetic@example.invalid')
    runtime.begin_turn('other-owner','I choose secret-other grain')
    context,stats=runtime.recall_context('synthetic-owner','millet breakfast')
    assert 'millet' in context and 'synthetic@example.invalid' not in context
    assert 'secret-other' not in context
    assert 'source_id' in context and 'occurred_at' in context and 'role' in context
    assert stats['memory_sources']==1


def test_memory_fallback_and_local_only_do_not_leak_to_model_context(temp_db,monkeypatch):
    runtime=importlib.import_module('memory_runtime')
    runtime.begin_turn('synthetic-owner','[local-only] Synthetic private allergy notes')
    context,stats=runtime.recall_context('synthetic-owner','private allergy')
    assert 'Synthetic private' not in context
    assert stats['memory_blocked']>=1


def test_pair_and_outbox_rollback_with_callers_transaction(temp_db):
    runtime=importlib.import_module('memory_runtime')
    with get_conn() as conn:
        runtime.initialize(conn)
    with get_conn() as conn:
        with pytest.raises(RuntimeError):
            with conn:
                runtime.record_pair(conn,'synthetic-owner','Synthetic user','Synthetic assistant')
                raise RuntimeError('synthetic rollback')
    with get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM agent_events').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM memory_outbox').fetchone()[0]==0


def test_document_write_and_memory_outbox_are_one_transaction(temp_db,monkeypatch):
    runtime=importlib.import_module('memory_runtime')
    import patient_documents as documents
    with get_conn() as conn:
        runtime.initialize(conn)
    documents.write_document('pacjent.md','Synthetic first')
    with get_conn() as conn:
        row=conn.execute("SELECT content,revision FROM memory_sources WHERE source_id='document:pacjent.md'").fetchone()
    assert row is not None and tuple(row)==('Synthetic first',1)
    monkeypatch.setattr(runtime,'document_changed',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('synthetic outbox failure')))
    with pytest.raises(RuntimeError,match='synthetic outbox failure'):
        documents.write_document('pacjent.md','Synthetic should roll back')
    assert documents.get_document('pacjent.md')['content']=='Synthetic first'
    assert len(documents.get_revisions('pacjent.md'))==1


def test_web_lifespan_starts_and_stops_outbox_with_its_worker(temp_db,monkeypatch):
    import memory_runtime
    from fastapi.testclient import TestClient
    from webapp import create_app
    monkeypatch.setenv('WEB_PASSWORD','synthetic-strong-password')
    calls=[]
    monkeypatch.setattr(memory_runtime,'start_worker',lambda:calls.append('start'))
    monkeypatch.setattr(memory_runtime,'stop_worker',lambda:calls.append('stop'))
    with TestClient(create_app(start_worker=True,processor=lambda *a,**k:'synthetic')):
        assert calls==['start']
    assert calls==['start','stop']


def test_document_snapshot_only_indexes_changed_revision(temp_db):
    runtime=importlib.import_module('memory_runtime')
    with get_conn() as conn:
        runtime.initialize(conn)
        runtime.document_changed(conn,'pacjent.md','Synthetic profile',1,'2026-10-24T18:00:00Z')
        runtime.document_changed(conn,'pacjent.md','Synthetic profile',1,'2026-10-24T18:00:00Z')
    with get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM memory_sources WHERE kind='document'").fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM memory_outbox').fetchone()[0]==1
