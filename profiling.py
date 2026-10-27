"""Optional content-free spans in a separate durable JSONL sink.

Durations are monotonic; UTC fields provide chronology. Nested durations overlap
and must never be summed. No caller can attach payloads or arbitrary attributes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import os
import re
from time import perf_counter
from uuid import uuid4

CURRENT = ContextVar('k90_profile', default=None)
CLOCK_ID = uuid4().hex
STAGES = frozenset(('begin', 'capture', 'history', 'projection', 'filtering',
    'context', 'db', 'sync_garmin', 'sync_libre', 'summary', 'recall',
    'token_access', 'token_refresh', 'catalog', 'provider', 'provider_request',
    'tool', 'persistence', 'transport_delivery', 'queue_wait', 'processing', 'memory_index', 'hs_request'))


def enabled():
    value = os.getenv('K90_PROFILING_ENABLED', 'false')
    if value not in ('true', 'false'):
        raise ValueError('invalid_profiling_configuration')
    return value == 'true'


def _emit(state, stage, event, **numbers):
    if not state['timing']:
        return
    from logging_setup import safe_fields
    numbers.update(safe_fields({key:state.get(key) for key in ('round_index','tool_index','operation_id')}))
    record = dict(component='profiling', scope_id=state['scope_id'], clock_id=CLOCK_ID, request_id=state['request_id'], channel=state['channel'],
        job_id=state['job_id'], background=state['background'], scope=state['scope'],
        utc=datetime.now(timezone.utc).isoformat(), stage=stage, event=event, **numbers)
    from logging_setup import write_record
    write_record('profiling.jsonl', record)


def _outcome(exc):
    from logging_setup import exception_metadata
    return 'timeout' if exception_metadata(exc)['exception_category'] == 'timeout' else 'error'


def failure(exc):
    state = CURRENT.get()
    if state is not None:
        state['outcome'] = _outcome(exc)


@contextmanager
def request_scope(channel='cli', request_id=None, job_id=None, *, background=False, scope='processing'):
    from logging_setup import configure_logging
    configure_logging()
    timing = enabled()
    if CURRENT.get() is not None:
        yield
        return
    state = dict(request_id=request_id if type(request_id) is str and re.fullmatch(r'[0-9a-f]{32}', request_id) else uuid4().hex,
        channel=channel if channel in ('web', 'telegram', 'cli', 'background') else 'background',
        job_id=job_id if type(job_id) is int and job_id > 0 else None,
        background=bool(background), scope=scope if scope in ('processing', 'submission', 'delivery', 'background') else 'processing',
        scope_id=uuid4().hex, timing=timing, stack=[], count=0, marks=set(), errors=0)
    token = CURRENT.set(state)
    started = perf_counter() if timing else None
    outcome = 'finish'
    _emit(state, 'begin', 'start')
    try:
        yield
    except BaseException as exc:
        outcome = _outcome(exc)
        raise
    finally:
        outcome = state.get('outcome', outcome)
        elapsed = max(0, (perf_counter() - started) * 1000) if timing else None
        _emit(state, 'begin', outcome, elapsed_ms=elapsed)
        _emit(state, 'begin', 'summary', elapsed_ms=elapsed, outcome=outcome, spans=state['count'], stage_errors=state['errors'])
        CURRENT.reset(token)


@contextmanager
def span(stage):
    state = CURRENT.get()
    if state is None:
        with request_scope('background', background=True, scope='background'):
            with span(stage) as result:
                yield result
        return
    if not state['timing']:
        try:
            yield
        except BaseException as exc:
            _stage_failure(stage, exc)
            raise
        return
    if stage not in STAGES:
        raise ValueError('invalid_profile_stage')
    state['count'] += 1
    number = state['count']
    parent = state['stack'][-1][0] if state['stack'] else None
    started = perf_counter()
    state['stack'].append((number, stage, started))
    _emit(state, stage, 'start', span_id=number, parent_span_id=parent)
    outcome = 'finish'
    returned_error = [False]
    try:
        yield returned_error
    except BaseException as exc:
        outcome = _outcome(exc)
        _stage_failure(stage, exc)
        raise
    finally:
        if outcome == 'finish' and returned_error[0] is True:
            outcome = 'error'
        if outcome != 'finish':
            state['errors'] += 1
        _emit(state, stage, outcome, span_id=number, parent_span_id=parent,
              elapsed_ms=max(0, (perf_counter() - started) * 1000))
        state['stack'].pop()


def first_provider_event(*, text=False):
    state = CURRENT.get()
    if state is None or not state['timing']:
        return
    provider = next((s for s in reversed(state['stack']) if s[1] == 'provider_request'), None)
    if provider is None:
        return
    event = 'first_text' if text else 'first_event'
    key = (provider[0], event)
    if key not in state['marks']:
        state['marks'].add(key)
        _emit(state, 'provider_request', event, span_id=provider[0],
              elapsed_ms=max(0, (perf_counter() - provider[2]) * 1000))


def queue_event(event, started=None, clock_id=None):
    state = CURRENT.get()
    if state is None or not state['timing']:
        return
    elapsed = max(0, (perf_counter() - started) * 1000) if started is not None and clock_id == CLOCK_ID else None
    _emit(state, 'queue_wait', event, elapsed_ms=elapsed, clock_reset=event != 'start' and elapsed is None)


def profiled(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with span(stage) as failed:
                result = function(*args, **kwargs)
                if failed is not None and type(result) is dict and 'error' in result:
                    failed[0] = True
                return result
        return wrapped
    return decorate


def profiled_request(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with request_scope():
            return function(*args, **kwargs)
    return wrapped


def _stage_failure(stage, exc):
    from logging_setup import event
    if stage == 'provider_request':
        event('provider.failed', error=exc, error_code='provider_request_failed')
    else:
        event('stage.failed', error=exc, error_code='stage_failed')


def indices(round_index, tool_index=None):
    state = CURRENT.get()
    if state is not None:
        state['round_index'] = round_index
        state['tool_index'] = tool_index
        state['operation_id'] = (state['request_id'] + ':' + str(round_index) + ':' + str(tool_index)) if tool_index else None
