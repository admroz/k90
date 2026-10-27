"""Synthetic acceptance for the shipped logging boundary."""
import logging


def test_profiling_is_durable_and_never_operational(tmp_path, monkeypatch, caplog):
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    with caplog.at_level(logging.INFO), profiling.request_scope('web'):
        with profiling.span('provider_request'):
            pass
    target = tmp_path / 'logs' / 'profiling.jsonl'
    assert target.exists(), 'profiling must have its own durable sink'
    assert 'agent.phase' not in caplog.text


def test_operational_sinks_are_safe_and_errors_are_copied(tmp_path, monkeypatch):
    import io
    import json
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    capture = io.StringIO()
    handler = logging.StreamHandler(capture)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with profiling.request_scope('web'):
            logger = logging.getLogger('web_runtime')
            logger.warning('conversation.claim seq=%d channel=%s', 1, 'SECRET_HEALTH')
            try:
                raise ValueError('SECRET_HEALTH https://private.invalid TOKEN base64')
            except ValueError:
                logger.exception('conversation.worker_error')
            logging.getLogger('httpx').warning('SECRET_HEALTH https://private.invalid TOKEN base64')
        app = tmp_path / 'logs' / 'app.log'
        assert app.exists(), 'operational logs must be durable with profiling disabled'
        rows = [json.loads(line) for line in app.read_text().splitlines()]
        errors = [json.loads(line) for line in (tmp_path/'logs'/'errors.log').read_text().splitlines()]
        assert len(errors) == 1 and errors[0] in rows
        assert len({r['request_id'] for r in rows}) == 1
        assert len(rows[0]['request_id']) == 32
        assert all(r['utc'].endswith('+00:00') and r['component'] for r in rows)
        assert errors[0]['exception_category'] == 'validation'
        for content in (app.read_text(), (tmp_path/'logs'/'errors.log').read_text(), capture.getvalue()):
            assert not any(secret in content for secret in ('SECRET_HEALTH', 'private.invalid', 'TOKEN', 'base64', 'Traceback'))
        assert not (tmp_path/'logs'/'profiling.jsonl').exists()
    finally:
        root.removeHandler(handler)


def test_provider_error_metadata_survives_wrapping_without_profiling(tmp_path, monkeypatch):
    import json
    import httpx
    import openai
    import outbound_policy
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    error = openai.RateLimitError('SECRET_BODY', response=httpx.Response(429,
        request=httpx.Request('POST', 'https://SECRET_URL.invalid'),
        headers={'x-request-id':'req_0123456789abcdef'}), body={'code':'SECRET_CODE'})
    def fail(**kwargs):
        raise error
    import pytest
    with profiling.request_scope('cli'), pytest.raises(outbound_policy.ModelCallError):
        outbound_policy.chat_completion(fail, model='synthetic', messages=[])
    app = tmp_path/'logs'/'app.log'
    assert app.exists(), 'provider failure must be visible even with timing disabled'
    rows = [json.loads(s) for s in app.read_text().splitlines()]
    row = next(r for r in rows if r['event'] == 'provider.failed')
    assert row['http_status'] == 429
    assert row['provider_request_id'] == 'req_0123456789abcdef'
    assert row['exception_category'] == 'http'
    assert row['error_code'] == 'provider_request_failed'
    assert 'SECRET' not in app.read_text()


def test_scope_instances_separate_delivery_attempts(tmp_path, monkeypatch):
    import json
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    for _ in range(2):
        with profiling.request_scope('telegram', 'a'*32, 7, scope='delivery'):
            with profiling.span('transport_delivery'):
                pass
    rows = [json.loads(s) for s in (tmp_path/'logs'/'profiling.jsonl').read_text().splitlines()]
    assert len({r['scope_id'] for r in rows}) == 2
    assert len({r['request_id'] for r in rows}) == 1


def test_actual_agent_tool_and_response_outcomes_are_distinct(temp_db, tmp_path, monkeypatch):
    import json
    import agent
    import tools
    import web_runtime
    from litellm import ModelResponse
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    monkeypatch.setattr(agent, 'MODEL', 'synthetic')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(agent.memory_runtime, 'start_worker', lambda: None)
    monkeypatch.setitem(tools._REGISTRY, 'get_weight_trend', lambda: {'ok':True})
    calls = []
    def complete(**kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise TimeoutError('SECRET_PROVIDER')
        return ModelResponse(choices=[{'message':{'role':'assistant', 'content':None,
            'tool_calls':[{'id':'synthetic','type':'function','function':{'name':'get_weight_trend','arguments':'{}'}}]}, 'finish_reason':'stop'}])
    monkeypatch.setattr(agent.litellm, 'completion', complete)
    web_runtime.init_runtime()
    job = web_runtime.enqueue('web:synthetic-outcome', 'SECRET_CHAT')
    assert web_runtime.ConversationWorker(lambda content: agent.run_agent(content, 'synthetic')[0]).run_once()
    rows = [json.loads(s) for s in (tmp_path/'logs'/'app.log').read_text().splitlines()]
    tool = next((r for r in rows if r['event'] == 'tool.completed'), None)
    assert tool is not None, 'actual tool completion needs a separate safe event'
    assert tool['round_index'] == 1 and tool['tool_index'] == 1
    assert tool['mutation_outcome'] == 'unknown', 'tool ok must never imply commit'
    assert tool['operation_id'] == job['profile_id'] + ':1:1'
    failed = next(r for r in rows if r['event'] == 'response.failed')
    assert failed['response_outcome'] == 'failed'
    assert failed['delivery_outcome'] == 'pending'
    assert failed['mutation_outcome'] == 'unknown'
    provider = next(r for r in rows if r['event'] == 'provider.failed')
    assert provider['round_index'] == 2 and 'tool_index' not in provider
    assert 'SECRET' not in (tmp_path/'logs'/'app.log').read_text()


def test_runtime_module_is_explicitly_packaged():
    from pathlib import Path
    dockerfile = (Path(__file__).resolve().parents[1]/'Dockerfile').read_text()
    assert any(line.startswith('COPY ') and 'logging_setup.py' in line for line in dockerfile.splitlines())


def test_sync_login_does_not_print_identity_or_exception(tmp_path, monkeypatch, capsys):
    import fetch_garmin
    from types import SimpleNamespace
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    (tmp_path/'.garmin_tokens').mkdir()
    class Client:
        display_name = 'SECRET_PATIENT'
        garth = SimpleNamespace(dump=lambda _: None)
        def __init__(self, **kwargs): self.calls = 0
        def login(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError('SECRET_TOKEN https://SECRET_URL.invalid')
    monkeypatch.setattr(fetch_garmin.garminconnect, 'Garmin', Client)
    fetch_garmin.login()
    output = capsys.readouterr()
    assert 'SECRET' not in output.out + output.err


def test_protocol_http_metadata_is_typed_and_content_free(tmp_path, monkeypatch):
    import http.client
    import json
    import profiling
    import subscription_protocol
    import pytest
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    class Response:
        status = 503
        def getheader(self, key):
            assert key == 'x-request-id'
            return 'req_0123456789abcdef'
        def read(self, *args):
            pytest.fail('error response body must never be read for logging')
    class Connection:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): pass
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(http.client, 'HTTPSConnection', Connection)
    with profiling.request_scope(), pytest.raises(subscription_protocol.ProbeError):
        with profiling.span('provider_request'):
            subscription_protocol.request_json(subscription_protocol.API_ORIGIN+'/v1/responses', token='SECRET_TOKEN')
    rows = [json.loads(s) for s in (tmp_path/'logs'/'app.log').read_text().splitlines()]
    row = next(r for r in rows if r['event'] == 'provider.failed')
    assert row.get('http_status') == 503, 'HTTP metadata must survive the protocol wrapper'
    assert row['provider_request_id'] == 'req_0123456789abcdef'
    assert 'SECRET' not in (tmp_path/'logs'/'app.log').read_text()


def _child(code, directory, *args):
    """Optional task watchdog wraps EACH child; normal offline CI needs no harness."""
    import os
    from pathlib import Path
    import subprocess
    import sys
    from uuid import uuid4
    child_env = dict(os.environ, DATA_DIR=str(directory))
    command = [sys.executable, '-c', code, *map(str, args)]
    template = os.getenv('K90_TEST_GUARD_TEMPLATE')
    if template:
        guard_dir = Path(os.environ['K90_TEST_GUARD_ROOT']) / ('tests-child-' + uuid4().hex)
        guard_dir.mkdir()
        guard = guard_dir/'guard.py'
        guard.write_text(Path(template).read_text())
        command = [sys.executable, str(guard), 'env', '-i',
                   *[key+'='+value for key,value in child_env.items()], *command]
        child_env = {'PATH':'/usr/bin:/bin', 'HOME':os.environ['K90_TEST_SUPERVISOR_HOME'],
                     'PYTHON_DOTENV_DISABLED':'1', 'HERMES_HOME':os.environ['K90_TEST_SUPERVISOR_HERMES_HOME']}
    directory.mkdir(parents=True, exist_ok=True)
    output = guard_dir/'writer.jsonl' if template else directory/('child-'+uuid4().hex+'.log')
    with (directory/('supervisor-'+uuid4().hex+'.log')).open('wb') if template else output.open('wb') as stream:
        child = subprocess.Popen(command, env=child_env, stdout=stream, stderr=subprocess.STDOUT)
    child.output_log = output
    return child


def test_two_process_rotation_permissions_and_restart(tmp_path):
    import json
    import stat
    code = '''
import logging, sys
import logging_setup as logs
import profiling
logs.LIMITS['app.log'] = 4096
logs.LIMITS['errors.log'] = 4096
with profiling.request_scope('cli', 'b'*32):
    for i in range(1, 11):
        logs.event('tool.completed', round_index=i, tool_index=int(sys.argv[1]), mutation_outcome='unknown')
'''
    children = [_child(code, tmp_path, index) for index in (1,2)]
    assert [child.wait(timeout=90) for child in children] == [0,0]
    directory = tmp_path/'logs'
    files = list(directory.glob('app.log*'))
    logs = [p for p in files if not p.name.endswith('.lock')]
    rows = [json.loads(line) for p in logs for line in p.read_text().splitlines()]
    assert {(r['round_index'], r['tool_index']) for r in rows} == {(i,j) for i in range(1,11) for j in (1,2)}
    assert len(rows) == 20 and len(logs) > 1
    assert all(p.stat().st_size <= 4096 for p in logs)
    assert len(logs) <= 4
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in files)
    # A fresh process reopens the same files, including after rotation.
    child = _child(code, tmp_path, 3)
    assert child.wait(timeout=90) == 0
    rows = [json.loads(line) for p in directory.glob('app.log*') if not p.name.endswith('.lock')
            for line in p.read_text().splitlines()]
    assert {(r['round_index'], r['tool_index']) for r in rows} == {(i,j) for i in range(1,11) for j in (1,2,3)}


def test_retention_is_bounded_and_sink_failure_preserves_result(temp_db, tmp_path, monkeypatch, capfd):
    import json
    import logging_setup as logs
    import profiling
    import web_runtime
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    for name in logs.LIMITS:
        monkeypatch.setitem(logs.LIMITS, name, 1024)
    for _ in range(40):
        with profiling.request_scope('cli'):
            logs.event('response.failed', error=ValueError('SECRET_SINK'), response_outcome='failed')
    for name in logs.LIMITS:
        files = [p for p in (tmp_path/'logs').glob(name+'*') if not p.name.endswith('.lock')]
        assert len(files) == 4 and all(p.stat().st_size <= 1024 for p in files)
        for path in files:
            assert all(isinstance(json.loads(line), dict) for line in path.read_text().splitlines())
            assert 'SECRET' not in path.read_text()
    # Existing regular file where a directory is needed: every sink fails.
    blocked = tmp_path/'blocked'
    blocked.mkdir()
    (blocked/'logs').write_text('synthetic')
    monkeypatch.setenv('DATA_DIR', str(blocked))
    monkeypatch.setattr(logs, '_alarmed', False)
    web_runtime.init_runtime()
    web_runtime.enqueue('web:synthetic-sink-error', 'synthetic')
    assert web_runtime.ConversationWorker(lambda _: 'unchanged answer').run_once()
    from tools.db import get_conn
    with get_conn() as conn:
        row = conn.execute('SELECT state, response FROM chat_jobs').fetchone()
    assert tuple(row) == ('done', 'unchanged answer')
    output = capfd.readouterr()
    assert output.err.count('k90 logging sink unavailable') == 1
    assert 'blocked' not in output.err and 'SECRET' not in output.err


def test_malformed_sdk_metadata_never_changes_workload_exception(tmp_path, monkeypatch):
    import httpx
    import openai
    import profiling
    import pytest
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    class Malformed(openai.APIStatusError):
        def __getattribute__(self, key):
            if key == 'request_id':
                raise RuntimeError('SECRET_METADATA')
            return super().__getattribute__(key)
    original = Malformed('SECRET_BODY', response=httpx.Response(503,
        request=httpx.Request('POST', 'https://SECRET_URL.invalid')), body=None)
    with pytest.raises(Malformed) as caught:
        with profiling.request_scope():
            with profiling.span('provider_request'):
                raise original
    assert caught.value is original


def test_telegram_delivery_outcome_is_separate_from_response(tmp_path, monkeypatch):
    import json
    import telegram_adapter
    import pytest
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    class Backend:
        def call(self, method, path, **kwargs):
            if method == 'GET':
                return [dict(profile_id='c'*32, job_id=9, response='SECRET_RESPONSE',
                             delivery_index=0, request_id='telegram:SECRET_ID', chat_id=123)]
    class API:
        def send_text(self, *args): raise TimeoutError('SECRET_TOKEN')
    with pytest.raises(TimeoutError):
        telegram_adapter.deliver_pending(API(), Backend())
    rows = [json.loads(s) for s in (tmp_path/'logs'/'app.log').read_text().splitlines()]
    row = next(r for r in rows if r['event'] == 'delivery.failed')
    assert row['delivery_outcome'] == 'failed' and 'response_outcome' not in row
    assert row['request_id'] == 'c'*32
    assert 'SECRET' not in (tmp_path/'logs'/'app.log').read_text()


def test_queue_event_rejects_untrusted_event_text(tmp_path, monkeypatch):
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    with profiling.request_scope('SECRET_CHANNEL', 'SECRET_REQUEST', True, scope='SECRET_SCOPE'):
        profiling.queue_event('SECRET_EVENT https://SECRET_URL.invalid')
    content = (tmp_path/'logs'/'profiling.jsonl').read_text()
    assert 'SECRET' not in content, 'profiling fields must have a closed vocabulary'


def test_bootstrap_paths_default_to_operational_only(tmp_path):
    import json
    code = '''
import importlib, logging, os, sys
os.environ.pop('K90_PROFILING_ENABLED', None)
importlib.import_module(sys.argv[1])
try:
    raise ValueError('SECRET_BOOTSTRAP')
except ValueError:
    logging.getLogger(sys.argv[1]).exception('conversation.worker_error')
'''
    for module in ('webapp', 'telegram_adapter', 'agent', 'server'):
        directory = tmp_path/module
        child = _child(code, directory, module)
        assert child.wait(timeout=90) == 0
        app = directory/'logs'/'app.log'
        error = directory/'logs'/'errors.log'
        assert app.exists() and error.exists()
        assert not (directory/'logs'/'profiling.jsonl').exists()
        assert 'SECRET' not in app.read_text() + error.read_text()
        assert any(json.loads(line)['exception_category'] == 'validation' for line in error.read_text().splitlines())


def test_http_library_status_is_retained_without_headers_or_urls():
    import httpx
    import requests
    import logging_setup as logs
    response = httpx.Response(403, request=httpx.Request('POST', 'https://SECRET_URL.invalid'),
                              headers={'authorization':'SECRET_TOKEN'})
    error = httpx.HTTPStatusError('SECRET_BODY', request=response.request, response=response)
    assert logs.exception_metadata(error).get('http_status') == 403
    response2 = requests.Response()
    response2.status_code = 502
    response2.url = 'https://SECRET_URL.invalid'
    assert logs.exception_metadata(requests.HTTPError('SECRET_BODY', response=response2)).get('http_status') == 502


def test_uncaught_bootstrap_exception_has_no_traceback_or_source(tmp_path):
    child = _child("import agent; raise ValueError('SECRET_UNHANDLED')", tmp_path)
    assert child.wait(timeout=90) == 1
    path = tmp_path/'logs'/'errors.log'
    assert path.exists(), 'uncaught bootstrap errors need the safe error sink'
    import json
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    assert any(row['event'] == 'runtime.unhandled' for row in rows)
    assert 'SECRET' not in path.read_text()
    assert 'SECRET' not in child.output_log.read_text()
    assert 'Traceback' not in child.output_log.read_text()


def test_cli_command_and_legacy_telegram_have_generated_scope(temp_db, tmp_path, monkeypatch, capsys):
    import json
    import agent
    import server
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    answers = iter(['/help','quit'])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    def command(_):
        logging.getLogger('agent').info('agent.failure_record.unavailable')
        return 'synthetic help'
    monkeypatch.setattr(agent, 'handle_command', command)
    start = len((tmp_path/'logs'/'app.log').read_text().splitlines()) if (tmp_path/'logs'/'app.log').exists() else 0
    agent.cli()
    monkeypatch.setattr(server, 'TELEGRAM_ALLOWED_USER_ID', '321')
    monkeypatch.setattr(server, 'handle_command', command)
    class API:
        def send_text(self, *args):
            logging.getLogger('server').info('telegram.stopped')
    server.handle_telegram_message(API(), {'chat':{'id':321,'type':'private'}, 'from':{'id':321}, 'text':'/help'})
    rows = [json.loads(s) for s in (tmp_path/'logs'/'app.log').read_text().splitlines()]
    rows = rows[start:]
    assert all(type(row['request_id']) is str and len(row['request_id']) == 32 for row in rows)
    assert {row['channel'] for row in rows} == {'cli','telegram'}
    telegram = [row for row in rows if row['channel'] == 'telegram']
    assert len({row['request_id'] for row in telegram}) == 1
    assert not (tmp_path/'logs'/'profiling.jsonl').exists()


def test_arbitrary_objects_and_extra_fields_never_reach_any_sink(tmp_path, monkeypatch, capsys):
    import json
    import logging_setup as logs
    import profiling
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    class Secret:
        def __str__(self): raise AssertionError('formatter touched private object')
        def __repr__(self): raise AssertionError('formatter touched private object')
    class SecretError(Exception):
        def __str__(self): raise AssertionError('formatter touched private exception')
    with profiling.request_scope('web'):
        try:
            raise SecretError()
        except SecretError:
            logging.getLogger('SECRET_COMPONENT').exception(Secret(), Secret(), stack_info=True)
        logging.getLogger('web_runtime').error('conversation.worker_error', extra={'k90_fields':{
            'http_status':True, 'provider_request_id':'https://SECRET_URL.invalid',
            'exception_category':'SECRET_CLASS', 'error_code':'SECRET_CODE',
            'mutation_outcome':'ok', 'body':'data:image/png;base64,U0VDUkVUX0lNQUdF',
            'response_outcome':{'SECRET':'BODY'}}})
    content = capsys.readouterr().err
    for name in logs.LIMITS:
        path = tmp_path/'logs'/name
        content += path.read_text() if path.exists() else ''
    assert not any(s in content for s in ('SECRET', 'U0VDUkVU', 'Traceback', 'base64', 'AssertionError'))
    rows = [json.loads(s) for s in (tmp_path/'logs'/'errors.log').read_text().splitlines()]
    assert rows[0]['exception_category'] == 'unknown'
    assert not any(key in rows[1] for key in ('http_status','provider_request_id','mutation_outcome','response_outcome'))


def test_dispatcher_caught_exception_has_safe_category_and_error_copy(tmp_path, monkeypatch):
    import json
    import profiling
    import tools
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'false')
    def fail(): raise ValueError('SECRET_TOOL_RESULT')
    monkeypatch.setitem(tools._REGISTRY, 'get_weight_trend', fail)
    with profiling.request_scope('cli'):
        profiling.indices(1, 1)
        result = tools.execute_tool('get_weight_trend', {})
    assert result == {'error':'SECRET_TOOL_RESULT'}, 'logging must preserve the dispatcher result'
    path = tmp_path/'logs'/'errors.log'
    assert path.exists(), 'caught tool exceptions still need safe diagnostics'
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    row = next(r for r in rows if r['event'] == 'tool.failed')
    assert row['exception_category'] == 'validation'
    assert row['mutation_outcome'] == 'unknown'
    assert row['round_index'] == row['tool_index'] == 1
    assert 'SECRET' not in path.read_text()
