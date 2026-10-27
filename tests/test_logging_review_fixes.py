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
    # Configure this TestClient independently of the shell or other web fixtures.
    monkeypatch.setenv('WEB_PASSWORD', 'synthetic-password-only')
    monkeypatch.setenv('WEB_COOKIE_SECURE', 'false')
    monkeypatch.setenv('K90_INTERNAL_TOKEN', 'synthetic-internal-only')
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


def test_active_scope_late_handlers_factories_and_foreign_records(tmp_path):
    from test_logging import _child
    code = '''
import io, json, logging, os
from pathlib import Path
import profiling, logging_setup as logs
stream = io.StringIO()
with profiling.request_scope('web'):
    library = logging.getLogger('synthetic.late')
    library.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter('%(message)s %(body)s'))
    library.addHandler(handler)
    logging.setLogRecordFactory(logging.LogRecord)
    try:
        raise TimeoutError('PRIVATE_EXCEPTION')
    except TimeoutError:
        library.exception('PRIVATE_MESSAGE', extra={'body':'PRIVATE_TOKEN https://private.invalid data:image/png;base64,UFJJVkFURQ==', 'k90_context':{'request_id':'PRIVATE_ID'}})
    # A foreign record sent directly through the standard logger API is safe too.
    foreign = logging.LogRecord('synthetic.foreign',40,'PRIVATE_PATH',99,'PRIVATE_BODY',(),None)
    foreign.body = 'PRIVATE_EXTRA'
    foreign.k90_meta = {'http_status':503}
    foreign.k90_fields = {'http_status':429, 42:'PRIVATE_NON_STRING_KEY'}
    library.handle(foreign)
rows = [json.loads(line) for line in (Path(os.environ['DATA_DIR'])/'logs/errors.log').read_text().splitlines()]
assert len(rows) == 2 and rows[0]['exception_category'] == 'timeout'
assert all(len(row['request_id']) == 32 and 'PRIVATE' not in json.dumps(row) for row in rows)
assert not stream.getvalue()
'''
    child = _child(code, tmp_path)
    assert child.wait(timeout=90) == 0
    assert 'PRIVATE' not in child.output_log.read_text()


def test_first_setup_partial_failure_keeps_safe_emission_and_workload(tmp_path):
    from test_logging import _child
    code = """
import io, json, logging, os
from pathlib import Path
import logging_setup, profiling
stream = io.StringIO()
root = logging.getLogger()
root.handlers[:] = [logging.StreamHandler(stream)]
def fail(*args): raise OSError('PRIVATE_SETUP')
root.setLevel = fail
with profiling.request_scope('web'):
    logging.error('PRIVATE_MESSAGE', extra={'body':'PRIVATE_TOKEN'})
    result = 'completed'
assert result == 'completed' and not stream.getvalue()
path = Path(os.environ['DATA_DIR'])/'logs/errors.log'
rows = [json.loads(line) for line in path.read_text().splitlines()]
assert rows and all('PRIVATE' not in json.dumps(row) for row in rows)
"""
    child = _child(code, tmp_path)
    assert child.wait(timeout=90) == 0
    assert 'PRIVATE' not in child.output_log.read_text()


def test_foreign_level_labels_are_closed_vocabulary(tmp_path):
    from test_logging import _child
    code = """
import json, logging, os
from pathlib import Path
import profiling
with profiling.request_scope('web'):
    logging.addLevelName(40, 'PRIVATE_LEVEL_LABEL')
    logging.getLogger('library').error('PRIVATE_BODY')
rows = [json.loads(line) for line in (Path(os.environ['DATA_DIR'])/'logs/errors.log').read_text().splitlines()]
assert rows and rows[0]['level'] == 'ERROR'
assert 'PRIVATE' not in json.dumps(rows)
"""
    child = _child(code, tmp_path)
    assert child.wait(timeout=90) == 0
    assert 'PRIVATE' not in child.output_log.read_text()
