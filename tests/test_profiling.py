import json
import logging

import pytest


def events(caplog):
    return [json.loads(r.getMessage().split(' profile=', 1)[1])
            for r in caplog.records if ' profile=' in r.getMessage()]


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
def test_disabled_profiling_has_no_clock_uuid_or_log_cost(monkeypatch, caplog, setting):
    import profiling
    monkeypatch.delenv('K90_PROFILING_ENABLED', raising=False)
    if setting is not None:
        monkeypatch.setenv('K90_PROFILING_ENABLED', setting)
    def forbidden():
        pytest.fail('disabled profiling allocated an ID or read the clock')
    monkeypatch.setattr(profiling, 'perf_counter', forbidden)
    monkeypatch.setattr(profiling, 'uuid4', forbidden)
    def exercise():
        with profiling.request_scope('web'):
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
