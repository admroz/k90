"""Synthetic regressions for ingress correlation and safe bootstrap boundaries."""
import json
import logging
import pytest


def test_bootstrap_failure_does_not_prevent_request_entry(monkeypatch):
    import profiling
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    def broken(*args): raise RuntimeError('synthetic setup failure')
    monkeypatch.setattr(logging, 'setLogRecordFactory', broken)
    with profiling.request_scope('web'):
        result = 'workload completed'
    assert result == 'workload completed'


def test_ingress_links_generated_identity_to_actual_backend_job(temp_db, tmp_path, monkeypatch):
    import telegram_adapter as adapter
    from fastapi.testclient import TestClient
    from webapp import create_app
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_ID', '345')
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    class API:
        def download_file(self, _): return b'invalid synthetic image', 'application/octet-stream'
    with TestClient(create_app(start_worker=False)) as client:
        class Backend:
            def call(self, method, path, **kwargs):
                response = client.post(path, headers={'Authorization':'Bearer synthetic-internal-only'}, **kwargs)
                assert response.status_code == 202
                return response.json()
        update = {'update_id':1, 'message':{'chat':{'id':345,'type':'private'},
            'from':{'id':345}, 'photo':[{'file_id':'synthetic'}], 'caption':'synthetic ingress'}}
        adapter.accept_update(API(), Backend(), update)
        adapter.accept_update(API(), Backend(), update)
    from tools.db import get_conn
    with get_conn() as conn:
        jobs = conn.execute('SELECT seq, profile_id FROM chat_jobs').fetchall()
    assert len(jobs) == 1
    rows = [json.loads(line) for line in (__import__('pathlib').Path(__import__('os').environ['DATA_DIR'])/'logs/app.log').read_text().splitlines()]
    links = [r for r in rows if r['event'] == 'telegram.submitted']
    assert len(links) == 2
    assert all(r['backend_request_id'] == jobs[0]['profile_id'] and r['backend_job_id'] == jobs[0]['seq'] for r in links)
    assert len({r['request_id'] for r in links}) == 2


def test_ingress_failure_keeps_exception_inside_scope(tmp_path, monkeypatch):
    import telegram_adapter as adapter
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('TELEGRAM_ALLOWED_USER_ID', '345')
    class API:
        def download_file(self, _): raise TimeoutError('PRIVATE_DOWNLOAD')
    with pytest.raises(TimeoutError):
        adapter.accept_update(API(), object(), {'update_id':1,'message':{'chat':{'type':'private','id':345},
            'from':{'id':345}, 'photo':[{'file_id':'synthetic'}]}})
    path = tmp_path/'logs/errors.log'
    assert path.exists()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    row = next(r for r in rows if r['event'] == 'telegram.ingress_failed')
    assert len(row['request_id']) == 32 and row['exception_category'] == 'timeout'
    assert 'PRIVATE_DOWNLOAD' not in path.read_text()
