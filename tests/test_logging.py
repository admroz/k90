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
