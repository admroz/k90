"""Bounded local JSON logs for the Linux container; no payload formatting.

Every write reopens under flock so backend and Telegram share rotation safely.
Logging failures are deliberately isolated from application results.
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import threading

LIMITS = {'app.log': 10 * 1024 * 1024, 'errors.log': 5 * 1024 * 1024,
          'profiling.jsonl': 10 * 1024 * 1024}
BACKUPS = 3
_alarm_lock = threading.Lock()
_alarmed = False


def _alarm():
    global _alarmed
    with _alarm_lock:
        if not _alarmed:
            _alarmed = True
            try:
                os.write(2, b'k90 logging sink unavailable\n')
            except OSError:
                pass


def _open(path):
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('invalid_log_file')
        os.fchmod(fd, 0o600)
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_record(name, record):
    """Internal sink. Callers supply validated, content-free records only."""
    try:
        limit = LIMITS[name]
        payload = (json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        if len(payload) > min(limit, 8192):
            return
        directory = Path(os.getenv('DATA_DIR', str(Path(__file__).parent / 'data'))) / 'logs'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink():
            raise OSError('invalid_log_directory')
        directory.chmod(0o700)
        lock = _open(directory / (name + '.lock'))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = directory / name
            fd = _open(path)
            try:
                if os.fstat(fd).st_size + len(payload) > limit:
                    os.close(fd)
                    fd = None
                    for index in range(BACKUPS, 0, -1):
                        source = path if index == 1 else directory / (name + '.' + str(index - 1))
                        target = directory / (name + '.' + str(index))
                        if source.exists() or source.is_symlink():
                            os.replace(source, target)
                    fd = _open(path)
                view = memoryview(payload)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError('log_write_failed')
                    view = view[count:]
            finally:
                if fd is not None:
                    os.close(fd)
        finally:
            os.close(lock)
    except Exception:
        _alarm()

# Exact repository templates: arguments are never interpolated.
TEMPLATES = {'agent.start user=%s model=%s reasoning_effort=%s input=%s history_records=%d context_sections=%d context_chars=%d summary_chars=%d': 'agent.start', 'agent.max_rounds user=%s rounds=%d': 'agent.max_rounds', 'agent.tools user=%s round=%d tool_calls=%s': 'agent.tools', 'agent.usage user=%s round=%d prompt_tokens=%s completion_tokens=%s': 'agent.usage', 'agent.finish user=%s round=%d response_chars=%d refresh=%s': 'agent.finish', 'agent.tool_result user=%s tool=%s ok=%s': 'agent.tool_result', 'agent.failure_record.unavailable': 'agent.failure_record.unavailable', 'conversation.claim seq=%d channel=%s': 'conversation.claim', 'conversation.failed job_id=%d': 'conversation.failed', 'summary.startup_refresh_failed': 'summary.startup_refresh_failed', 'conversation.worker_error': 'conversation.worker_error', 'summary.auto_sync_refresh_failed': 'summary.auto_sync_refresh_failed', 'summary.refresh_failed': 'summary.refresh_failed', 'conversation.sync_failed source=%s': 'conversation.sync_failed', 'telegram.message chat_id=%s user_id=%s text_chars=%d image=%s': 'telegram.message', 'telegram.response chat_id=%s chars=%d refresh=%s': 'telegram.response', 'telegram.connected bot=@%s': 'telegram.connected', 'telegram.reject reason=non_private chat_id=%s user_id=%s': 'telegram.reject', 'telegram.reject reason=not_allowed chat_id=%s user_id=%s': 'telegram.reject', 'summary.async_refresh trigger=tool_call sender=%s': 'summary.async_refresh', 'telegram.allowed_user_missing; messages will be rejected. Send a message to the bot, read user_id from the log, set TELEGRAM_ALLOWED_USER_ID and restart.': 'telegram.allowed_user_missing;', 'telegram.sent chat_id=%s chars=%d': 'telegram.sent', 'garmin.auto_sync_failed sender=%s error=%s': 'garmin.auto_sync_failed', 'libre.auto_sync_failed sender=%s error=%s': 'libre.auto_sync_failed', 'telegram.image mime=%s bytes=%d': 'telegram.image', 'agent.error sender=%s error=%s': 'agent.error', 'summary.startup_refresh_failed error=%s': 'summary.startup_refresh_failed', 'telegram.stopped': 'telegram.stopped', 'garmin.auto_sync_no_changes sender=%s': 'garmin.auto_sync_no_changes', 'libre.auto_sync_no_changes sender=%s': 'libre.auto_sync_no_changes', 'telegram.image_error error=%s': 'telegram.image_error', 'telegram.poll_error error=%s retry_in=%s': 'telegram.poll_error', 'telegram.update_error update_id=%s error=%s': 'telegram.update_error', 'telegram.disabled reason=missing_configuration': 'telegram.disabled', 'telegram.image_rejected reason=%s bytes=%d': 'telegram.image_rejected', 'telegram.unavailable error_type=%s retry=%s': 'telegram.unavailable', 'summary.refresh trigger=%s input_chars=%d files=%d': 'summary.refresh', 'summary.saved trigger=%s chars=%d attempts=%d': 'summary.saved', 'summary.attempt model=%s attempt=%d finish_reason=%s chars=%d': 'summary.attempt', 'summary.fallback trigger=%s finish_reason=%s': 'summary.fallback', 'memory.worker.unavailable': 'memory.worker.unavailable', 'garmin.sync start trigger=%s': 'garmin.sync', 'garmin.sync finish trigger=%s fetched=%d inserted=%d updated=%d unchanged=%d changed=%s': 'garmin.sync', 'garmin.sync trigger=%s error=%s': 'garmin.sync', 'garmin.sync trigger=%s dataset=%s fetched=%d inserted=%d updated=%d unchanged=%d': 'garmin.sync', 'libre.sync start trigger=%s': 'libre.sync', 'libre.sync finish trigger=%s fetched=%d inserted=%d updated=%d unchanged=%d changed=%s': 'libre.sync', 'libre.sync skipped trigger=%s reason=disabled': 'libre.sync', 'libre.sync trigger=%s error=%s': 'libre.sync', 'libre.sync trigger=%s dataset=%s fetched=%d inserted=%d updated=%d unchanged=%d': 'libre.sync'}

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

COMPONENTS = frozenset(('agent', 'web_runtime', 'webapp', 'telegram_adapter', 'server',
    'summary', 'memory_runtime', 'tools', 'tools.garmin', 'tools.libre',
    'outbound_policy', 'responses_api', 'subscription_api'))
_CONFIG_LOCK = threading.RLock()


def exception_metadata(exc):
    """Classify by trusted hierarchy; never format an exception or its body."""
    category = 'unknown'
    if isinstance(exc, TimeoutError):
        category = 'timeout'
    elif isinstance(exc, (ConnectionError,)):
        category = 'connection'
    elif isinstance(exc, ValueError):
        category = 'validation'
    elif isinstance(exc, PermissionError):
        category = 'permission'
    elif isinstance(exc, OSError):
        category = 'io'
    # Optional SDKs are inspected only when already imported.
    for module, names in (('httpx', {'TimeoutException':'timeout', 'HTTPStatusError':'http', 'NetworkError':'connection'}),
                          ('openai', {'APITimeoutError':'timeout', 'APIStatusError':'http', 'APIConnectionError':'connection'}),
                          ('requests.exceptions', {'Timeout':'timeout', 'HTTPError':'http', 'ConnectionError':'connection'})):
        loaded = sys.modules.get(module)
        if loaded:
            for name, value in names.items():
                cls = getattr(loaded, name, None)
                if isinstance(cls, type) and isinstance(exc, cls):
                    category = value
                    break
    result = {'exception_category':category, 'error_code':'runtime_failure'}
    # SDK status/request_id are documented fields; never scan headers or body.
    loaded = sys.modules.get('openai')
    cls = getattr(loaded, 'APIStatusError', None) if loaded else None
    if isinstance(cls, type) and isinstance(exc, cls):
        result.update(safe_fields({'http_status':exc.status_code, 'provider_request_id':exc.request_id}))
    protocol = sys.modules.get('subscription_protocol')
    cls = getattr(protocol, 'ProbeError', None) if protocol else None
    if isinstance(cls, type) and isinstance(exc, cls):
        result['exception_category'] = 'protocol'
        result.update(safe_fields({'http_status':getattr(exc, 'http_status', None),
                                  'provider_request_id':getattr(exc, 'provider_request_id', None)}))
    return result


def _context():
    module = sys.modules.get('profiling')
    return module.CURRENT.get() if module else None


def _factory(*args, **kwargs):
    record = logging.LogRecord(*args, **kwargs)
    component = record.name if record.name in COMPONENTS else 'library'
    event = (record.msg if record.msg in EVENTS else TEMPLATES.get(record.msg, 'runtime.notice')) if type(record.msg) is str else 'runtime.notice'
    state = _context() or {}
    record.name = component
    record.msg, record.args = event, ()
    record.k90_meta = exception_metadata(record.exc_info[1]) if record.exc_info and record.exc_info[1] else {}
    record.exc_info = record.exc_text = record.stack_info = None
    record.pathname = record.filename = record.funcName = ''
    record.lineno = 0
    record.k90_context = {key:state.get(key) for key in ('request_id','scope_id','job_id','channel','scope')}
    record.k90_context.update(safe_fields({key:state.get(key) for key in ('round_index','tool_index','operation_id')}))
    return record


def _operational_record(record):
    result = dict(utc=datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                  level=record.levelname if record.levelno in (10,20,30,40,50) else 'INFO',
                  component=record.name, event=record.msg, **record.k90_context, **record.k90_meta)
    result.update(safe_fields(getattr(record, 'k90_fields', {})))
    return result


class SafeHandler(logging.Handler):
    def emit(self, record):
        try:
            value = _operational_record(record)
            write_record('app.log', value)
            if record.levelno >= logging.ERROR:
                write_record('errors.log', value)
        except Exception:
            _alarm()


class SafeConsole(logging.StreamHandler):
    def emit(self, record):
        try:
            self.stream.write(json.dumps(_operational_record(record), separators=(',', ':')) + '\n')
            self.flush()
        except Exception:
            _alarm()


def configure_logging():
    """Idempotent bootstrap, including replacement of preconfigured SDK handlers."""
    with _CONFIG_LOCK:
        logging.setLogRecordFactory(_factory)
        root = logging.getLogger()
        # Keep application/test observers; the factory sanitizes before any handler.
        if not any(isinstance(h, SafeHandler) for h in root.handlers):
            for handler in list(root.handlers):
                if not handler.__class__.__module__.startswith('_pytest.'):
                    root.removeHandler(handler)
            root.addHandler(SafeHandler())
            root.addHandler(SafeConsole())
        root.setLevel(logging.INFO)
        for name, logger in logging.root.manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                logger.handlers.clear()
                logger.propagate = True

EVENTS = frozenset(('provider.failed', 'stage.failed', 'tool.completed', 'response.completed',
    'response.failed', 'delivery.completed', 'delivery.failed', 'job.completed', 'job.failed'))
CODES = frozenset(('runtime_failure', 'provider_request_failed', 'stage_failed', 'tool_returned_error'))
CATEGORIES = frozenset(('unknown','timeout','connection','validation','permission','io','http','protocol'))


def safe_fields(fields):
    result = {}
    for key, value in fields.items():
        if key in ('round_index', 'tool_index') and type(value) is int and 0 < value <= 4096:
            result[key] = value
        elif key == 'http_status' and type(value) is int and 100 <= value <= 599:
            result[key] = value
        elif key == 'provider_request_id' and type(value) is str and re.fullmatch(r'req_[A-Za-z0-9_-]{8,96}', value):
            result[key] = value
        elif key == 'operation_id' and type(value) is str and re.fullmatch(r'[0-9a-f]{32}:[1-9][0-9]{0,3}:[1-9][0-9]{0,3}', value):
            result[key] = value
        elif key == 'exception_category' and value in CATEGORIES:
            result[key] = value
        elif key == 'error_code' and value in CODES:
            result[key] = value
        elif key == 'mutation_outcome' and value in ('committed','rolled_back','none','unknown'):
            result[key] = value
        elif key in ('response_outcome','delivery_outcome') and value in ('completed','failed','pending','unknown','none'):
            result[key] = value
        elif key == 'tool_outcome' and value in ('returned','error'):
            result[key] = value
    return result


def event(name, *, component='agent', error=None, **fields):
    """Emit a fixed event and typed fields. No caller-supplied message is accepted."""
    try:
        if name not in EVENTS or component not in COMPONENTS:
            return
        configure_logging()
        if error is not None:
            fields = {**exception_metadata(error), **fields}
        logging.getLogger(component).log(logging.ERROR if error is not None or name.endswith('.failed') else logging.INFO,
            name, extra={'k90_fields':safe_fields(fields)})
    except Exception:
        _alarm()
