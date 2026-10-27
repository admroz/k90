import json
import logging

import pytest


@pytest.fixture(autouse=True)
def isolated_logs(tmp_path, monkeypatch):
    monkeypatch.setenv('DATA_DIR', str(tmp_path))


def events(caplog):
    import os
    from pathlib import Path
    path = Path(os.environ['DATA_DIR']) / 'logs' / 'profiling.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize('transport', ['chat', 'responses'])
def test_sdk_timeout_reaches_profile_before_safe_wrapping(monkeypatch, caplog, transport):
    import httpx
    import openai
    import outbound_policy
    import profiling
    import responses_api
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    timeout = openai.APITimeoutError(request=httpx.Request('POST', 'https://synthetic.invalid/private'))
    def broken(**kwargs):
        raise timeout
    class Client:
        def __init__(self, **kwargs): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *args): return False
        create = staticmethod(broken)
    monkeypatch.setattr(responses_api, 'OpenAI', Client)
    with caplog.at_level(logging.INFO), profiling.request_scope('web'):
        with pytest.raises(outbound_policy.ModelCallError):
            if transport == 'chat':
                outbound_policy.chat_completion(broken, model='synthetic', messages=[])
            else:
                responses_api.ResponsesConversation('gpt-6.1-sol', []).complete()
    assert any(r['stage'] == 'provider_request' and r['event'] == 'timeout' for r in events(caplog))
    assert 'synthetic.invalid' not in json.dumps(events(caplog))


def test_timeout_classification_uses_hierarchy_not_exception_name():
    import httpx
    import openai
    import profiling
    import requests
    class DerivedTimeout(openai.APITimeoutError): pass
    class ReadTimeout(Exception): pass
    assert profiling._outcome(DerivedTimeout(request=httpx.Request('POST', 'https://synthetic.invalid'))) == 'timeout'
    for exc in (TimeoutError(), httpx.ReadTimeout('synthetic'), requests.exceptions.ConnectTimeout()):
        assert profiling._outcome(exc) == 'timeout'
    for exc in (ReadTimeout(), ValueError('timeout'), openai.APIConnectionError(request=httpx.Request('POST', 'https://synthetic.invalid'))):
        assert profiling._outcome(exc) == 'error'


@pytest.mark.parametrize('setting,tool_error', [('true', True), ('true', False), ('false', True)])
def test_actual_dispatcher_result_marks_tool_span_only(temp_db, monkeypatch, caplog, setting, tool_error):
    import agent
    import tools
    from litellm import ModelResponse
    monkeypatch.setenv('K90_PROFILING_ENABLED', setting)
    monkeypatch.setenv('K90_AGENT_AUTH', 'api')
    monkeypatch.setattr(agent, 'MODEL', 'synthetic')
    monkeypatch.setattr(agent, '_build_system_message', lambda: ('Synthetic system', {}))
    monkeypatch.setattr(agent.memory_runtime, 'start_worker', lambda: None)
    calls, executions = [], []
    def tool():
        executions.append(True)
        if tool_error:
            raise ValueError('synthetic-private-error')
        return {'value': 1}
    def complete(**kwargs):
        calls.append(kwargs)
        message = {'role': 'assistant', 'content': 'Synthetic answer'}
        if len(calls) == 1:
            message = {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'synthetic-call', 'type': 'function', 'function':
                 {'name': 'get_weight_trend', 'arguments': '{}'}}]}
        return ModelResponse(choices=[{'message': message, 'finish_reason': 'stop'}])
    monkeypatch.setitem(tools._REGISTRY, 'get_weight_trend', tool)
    monkeypatch.setattr(agent.litellm, 'completion', complete)
    with caplog.at_level(logging.INFO):
        assert agent.run_agent('Synthetic input', 'synthetic-owner') == ('Synthetic answer', False)
    assert executions == [True] and len(calls) == 2
    rows = events(caplog)
    assert len(agent.load_history('synthetic-owner')) == 2
    if setting == 'true':
        assert any(r['stage'] == 'tool' and r['event'] == ('error' if tool_error else 'finish') for r in rows)
        assert rows[-1]['stage_errors'] == int(tool_error)
        assert rows[-1]['outcome'] == 'finish'
        assert 'synthetic-private-error' not in json.dumps(rows)
    else:
        assert rows == []


def test_profile_error_has_start_finish_summary_and_no_exception_contents(monkeypatch, caplog):
    import profiling
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    with caplog.at_level(logging.INFO), pytest.raises(TimeoutError):
        with profiling.request_scope('telegram'):
            with profiling.span('provider'):
                raise TimeoutError('private meal token https://private.invalid')
    rows = events(caplog)
    assert [r['event'] for r in rows] == ['start', 'start', 'timeout', 'timeout', 'summary']
    assert len({r['request_id'] for r in rows}) == 1
    assert all(r['channel'] == 'telegram' for r in rows)
    assert all(r['utc'].endswith('+00:00') for r in rows)
    assert rows[2]['elapsed_ms'] >= 0
    assert rows[-1]['outcome'] == 'timeout'
    assert 'private' not in caplog.text


@pytest.mark.parametrize('channel', ['web', 'telegram'])
def test_queue_processing_and_persistence_share_generated_identity(temp_db, monkeypatch, caplog, channel):
    import web_runtime
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    web_runtime.init_runtime()
    with caplog.at_level(logging.INFO):
        job = web_runtime.enqueue(channel + ':987654321', 'private meal', channel, 123 if channel == 'telegram' else None)
        web_runtime.ConversationWorker(lambda _: 'safe').run_once()
    rows = events(caplog)
    assert {'queue_wait', 'processing', 'persistence'} <= {r['stage'] for r in rows}
    assert len({r['request_id'] for r in rows}) == 1
    assert all(r['channel'] == channel and r['job_id'] == job['seq'] for r in rows)
    assert all(len(r['request_id']) == 32 for r in rows)
    assert '987654321' not in json.dumps(rows) and 'private meal' not in json.dumps(rows)


@pytest.mark.parametrize('setting', [None, 'false', 'invalid', '1', 'TRUE'])
def test_disabled_profiling_has_correlation_without_clock_or_profile_sink(monkeypatch, caplog, setting):
    import profiling
    monkeypatch.delenv('K90_PROFILING_ENABLED', raising=False)
    if setting is not None:
        monkeypatch.setenv('K90_PROFILING_ENABLED', setting)
    def forbidden():
        pytest.fail('disabled profiling read the clock')
    monkeypatch.setattr(profiling, 'perf_counter', forbidden)
    def exercise():
        with profiling.request_scope('web'):
            assert len(profiling.CURRENT.get()['request_id']) == 32
            with profiling.span('tool'):
                pass
    if setting not in (None, 'false'):
        with pytest.raises(ValueError, match='invalid_profiling_configuration'):
            exercise()
    else:
        exercise()
    assert events(caplog) == []


def test_stream_reports_first_actual_event_and_text_once(monkeypatch, caplog):
    import profiling
    from subscription_protocol import read_stream
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    payloads = [{'type':'response.created'},
        {'type':'response.output_text.delta','delta':'private meal'},
        {'type':'response.output_text.delta','delta':'private credential'},
        {'type':'response.completed','response':{'status':'completed','output':[]}}]
    stream = [line for item in payloads for line in
        [('data: ' + json.dumps(item)).encode(), b'']]
    with caplog.at_level(logging.INFO), profiling.request_scope('web'):
        with profiling.span('provider_request'):
            result = read_stream(stream)
    assert result['status'] == 'completed'
    rows = events(caplog)
    assert sum(r['event'] == 'first_event' for r in rows) == 1
    assert sum(r['event'] == 'first_text' for r in rows) == 1
    assert 'private' not in json.dumps(rows)
    assert all('ttft' not in str(r).lower() for r in rows)


def test_background_is_separate_and_nested_spans_are_not_summed(monkeypatch, caplog):
    import profiling
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    with caplog.at_level(logging.INFO):
        with profiling.request_scope('background', background=True, scope='background'):
            with profiling.span('summary'):
                with profiling.span('provider'):
                    pass
    rows = events(caplog)
    assert all(r['background'] for r in rows)
    starts = [r for r in rows if r['event'] == 'start' and 'span_id' in r]
    assert starts[1]['parent_span_id'] == starts[0]['span_id']
    assert rows[-1]['spans'] == 2 and 'sum_ms' not in rows[-1]


def test_hs_timeout_is_visible_before_safe_backend_fallback(monkeypatch, caplog):
    import memory_runtime
    import profiling
    from k90_memory import BackendError
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    class Connection:
        def __init__(self, *a, **kw): pass
        def request(self, *a, **kw): raise TimeoutError('private HS URL and token')
        def close(self): pass
    monkeypatch.setattr(memory_runtime.http.client, 'HTTPSConnection', Connection)
    with caplog.at_level(logging.INFO), profiling.request_scope('web'):
        with pytest.raises(BackendError):
            memory_runtime._transport('private-token')('POST', 'https://private.invalid/recall', b'private meal', 1, 100)
    assert any(r['stage'] == 'hs_request' and r['event'] == 'timeout' for r in events(caplog))
    assert 'private' not in caplog.text


def test_returned_sync_error_is_visible_without_changing_result(monkeypatch, caplog):
    import profiling
    monkeypatch.setenv('K90_PROFILING_ENABLED', 'true')
    @profiling.profiled('sync_garmin')
    def sync():
        return {'error':'private provider contents'}
    with caplog.at_level(logging.INFO):
        assert sync() == {'error':'private provider contents'}
    assert any(r['stage'] == 'sync_garmin' and r['event'] == 'error' for r in events(caplog))
    assert 'private' not in caplog.text
