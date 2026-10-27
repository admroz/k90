"""The application owns its sinks without replacing Python logging dispatch."""
import json
import logging

STANDARD_CALL_HANDLERS = logging.Logger.callHandlers


def test_configuration_keeps_standard_dispatch(tmp_path, monkeypatch):
    import logging_setup as logs
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    logs.configure_logging()
    assert logging.Logger.callHandlers is STANDARD_CALL_HANDLERS
    assert logging.Logger.callHandlers.__module__ == 'logging'


def test_explicit_event_level_metadata_and_privacy(tmp_path, monkeypatch):
    import logging_setup as logs
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    with profiling.request_scope('web', 'a'*32, 4):
        logs.event('summary.fallback', component='summary', level=logging.WARNING,
                   error=TimeoutError('PRIVATE_BODY URL token base64'), attempts=2,
                   http_status=503, provider_request_id='req_synthetic123', body='PRIVATE_BODY')
    row = json.loads((tmp_path/'logs/app.log').read_text().splitlines()[-1])
    assert row['level'] == 'WARNING' and row['attempts'] == 2
    assert row['http_status'] == 503 and row['exception_category'] == 'timeout'
    assert row['request_id'] == 'a'*32 and row['job_id'] == 4
    assert 'PRIVATE' not in json.dumps(row)


def test_actual_summary_and_sync_failures_keep_safe_diagnostics(temp_db, tmp_path, monkeypatch):
    import pytest
    import summary
    import tools.garmin as garmin
    import tools.libre as libre
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_SYNC_ENABLED', 'true')
    monkeypatch.setenv('LIBRE_ENABLED', 'true')
    monkeypatch.setattr(libre, 'is_enabled', lambda: True)
    def fail(*args, **kwargs):
        raise TimeoutError('PRIVATE_SYNC_HEALTH_TOKEN')
    monkeypatch.setattr(garmin, 'sync_garmin_to_db', fail)
    monkeypatch.setattr(libre, 'sync_libre_to_db', fail)
    monkeypatch.setattr(summary, '_load_patient_parts', lambda: (['PRIVATE_DOCUMENT'], {}))
    monkeypatch.setattr(summary, '_generate_summary', fail)
    for enabled in ('false', 'true'):
        monkeypatch.setenv('K90_PROFILING_ENABLED', enabled)
        with profiling.request_scope('background'):
            assert 'PRIVATE_SYNC' in garmin.sync_garmin_data()['error']
            assert 'PRIVATE_SYNC' in libre.sync_libre_data()['error']
            with pytest.raises(TimeoutError):
                summary.refresh_patient_summary()
    rows = [json.loads(line) for line in (tmp_path/'logs/errors.log').read_text().splitlines()]
    assert {'tools.garmin','tools.libre','agent'} <= {r['component'] for r in rows}
    assert all(r['exception_category'] == 'timeout' for r in rows)
    assert 'PRIVATE' not in ''.join(p.read_text() for p in (tmp_path/'logs').iterdir())


def test_actual_asgi_and_thread_boundary_and_known_libraries(tmp_path):
    from test_logging import _child
    code = '''
import asyncio, http.client, logging, socket, threading
import uvicorn
import agent
from logging_setup import configure_logging, KNOWN_LIBRARIES
configure_logging()
for name in KNOWN_LIBRARIES:
    logging.getLogger(name).error('PRIVATE_LIBRARY_BODY URL token')
async def app(scope, receive, send):
    if scope['type'] == 'http':
        raise ValueError('PRIVATE_ASGI_BODY URL token')
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False, lifespan='off'))
async def exercise():
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        await asyncio.sleep(.01)
    def request():
        conn = http.client.HTTPConnection('127.0.0.1', sock.getsockname()[1])
        conn.request('GET', '/PRIVATE_URL')
        response = conn.getresponse()
        assert response.status == 500
        response.read()
        conn.close()
    try:
        await asyncio.to_thread(request)
    finally:
        server.should_exit = True
        await task
asyncio.run(exercise())
def fail(): raise TimeoutError('PRIVATE_THREAD_BODY')
thread = threading.Thread(target=fail)
thread.start()
thread.join()
'''
    child = _child(code, tmp_path)
    assert child.wait(timeout=90) == 0
    rows = [json.loads(line) for line in (tmp_path/'logs/errors.log').read_text().splitlines()]
    assert {r['exception_category'] for r in rows} == {'validation', 'timeout'}
    assert all(r['event'] == 'runtime.unhandled' for r in rows)
    content = child.output_log.read_text() + ''.join(p.read_text() for p in (tmp_path/'logs').iterdir())
    assert 'PRIVATE' not in content and 'Traceback' not in content


def test_failed_app_sink_still_attempts_error_copy(tmp_path, monkeypatch, capfd):
    import logging_setup as logs
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setattr(logs, '_alarmed', False)
    (tmp_path/'logs/app.log').mkdir(parents=True)
    logs.event('response.failed', error=TimeoutError('PRIVATE_SINK'))
    row = json.loads((tmp_path/'logs/errors.log').read_text())
    assert row['exception_category'] == 'timeout'
    output = capfd.readouterr().err
    assert output.count('k90 logging sink unavailable') == 1
    assert 'PRIVATE' not in output
