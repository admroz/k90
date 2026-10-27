"""Bounded local JSON logs for the Linux container; no payload formatting.

Every write reopens under flock so backend and Telegram share rotation safely.
Logging failures are deliberately isolated from application results.
"""
import fcntl
import logging
import math
import re
from datetime import datetime, timezone
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
TEMPLATES = {'agent.error sender=%s error=%s': 'agent.error',
 'agent.failure_record.unavailable': 'agent.failure_record.unavailable',
 'agent.finish user=%s round=%d response_chars=%d refresh=%s': 'agent.finish',
 'agent.max_rounds user=%s rounds=%d': 'agent.max_rounds',
 'agent.start user=%s model=%s reasoning_effort=%s input=%s history_records=%d context_sections=%d context_chars=%d summary_chars=%d': 'agent.start',
 'agent.tool_result user=%s tool=%s ok=%s': 'agent.tool_result',
 'agent.tools user=%s round=%d tool_calls=%s': 'agent.tools',
 'agent.usage user=%s round=%d prompt_tokens=%s completion_tokens=%s': 'agent.usage',
 'conversation.claim seq=%d channel=%s': 'conversation.claim',
 'conversation.failed job_id=%d': 'conversation.failed',
 'conversation.sync_failed source=%s': 'conversation.sync_failed',
 'conversation.worker_error': 'conversation.worker_error',
 'garmin.auto_sync_failed sender=%s error=%s': 'garmin.auto_sync_failed',
 'garmin.auto_sync_no_changes sender=%s': 'garmin.auto_sync_no_changes',
 'garmin.fetch_failed': 'garmin.fetch_failed',
 'garmin.login_failed': 'garmin.login_failed',
 'garmin.sync finish trigger=%s fetched=%d inserted=%d updated=%d unchanged=%d changed=%s': 'garmin.sync',
 'garmin.sync start trigger=%s': 'garmin.sync',
 'garmin.sync trigger=%s dataset=%s fetched=%d inserted=%d updated=%d unchanged=%d': 'garmin.sync',
 'garmin.sync trigger=%s error=%s': 'garmin.sync',
 'garmin.sync.progress': 'garmin.sync.progress',
 'libre.auto_sync_failed sender=%s error=%s': 'libre.auto_sync_failed',
 'libre.auto_sync_no_changes sender=%s': 'libre.auto_sync_no_changes',
 'libre.fetch_failed': 'libre.fetch_failed',
 'libre.sync finish trigger=%s fetched=%d inserted=%d updated=%d unchanged=%d changed=%s': 'libre.sync',
 'libre.sync skipped trigger=%s reason=disabled': 'libre.sync',
 'libre.sync start trigger=%s': 'libre.sync',
 'libre.sync trigger=%s dataset=%s fetched=%d inserted=%d updated=%d unchanged=%d': 'libre.sync',
 'libre.sync trigger=%s error=%s': 'libre.sync',
 'libre.sync.progress': 'libre.sync.progress',
 'memory.worker.unavailable': 'memory.worker.unavailable',
 'summary.async_refresh trigger=tool_call sender=%s': 'summary.async_refresh',
 'summary.attempt model=%s attempt=%d finish_reason=%s chars=%d': 'summary.attempt',
 'summary.auto_sync_refresh_failed': 'summary.auto_sync_refresh_failed',
 'summary.fallback trigger=%s finish_reason=%s': 'summary.fallback',
 'summary.refresh trigger=%s input_chars=%d files=%d': 'summary.refresh',
 'summary.refresh_failed': 'summary.refresh_failed',
 'summary.saved trigger=%s chars=%d attempts=%d': 'summary.saved',
 'summary.startup_refresh_failed': 'summary.startup_refresh_failed',
 'summary.startup_refresh_failed error=%s': 'summary.startup_refresh_failed',
 'telegram.allowed_user_missing; messages will be rejected. Send a message to the bot, read user_id from the log, set TELEGRAM_ALLOWED_USER_ID and restart.': 'telegram.allowed_user_missing;',
 'telegram.connected bot=@%s': 'telegram.connected',
 'telegram.disabled reason=missing_configuration': 'telegram.disabled',
 'telegram.image mime=%s bytes=%d': 'telegram.image',
 'telegram.image_error error=%s': 'telegram.image_error',
 'telegram.image_rejected reason=%s bytes=%d': 'telegram.image_rejected',
 'telegram.message chat_id=%s user_id=%s text_chars=%d image=%s': 'telegram.message',
 'telegram.poll_error error=%s retry_in=%s': 'telegram.poll_error',
 'telegram.reject reason=non_private chat_id=%s user_id=%s': 'telegram.reject',
 'telegram.reject reason=not_allowed chat_id=%s user_id=%s': 'telegram.reject',
 'telegram.response chat_id=%s chars=%d refresh=%s': 'telegram.response',
 'telegram.sent chat_id=%s chars=%d': 'telegram.sent',
 'telegram.stopped': 'telegram.stopped',
 'telegram.unavailable error_type=%s retry=%s': 'telegram.unavailable',
 'telegram.update_error update_id=%s error=%s': 'telegram.update_error'}


COMPONENTS = frozenset(('agent', 'web_runtime', 'webapp', 'telegram_adapter', 'server',
    'summary', 'memory_runtime', 'tools', 'tools.garmin', 'tools.libre',
    'outbound_policy', 'responses_api', 'subscription_api', 'fetch_garmin', 'fetch_libre', 'runtime'))
_CONFIG_LOCK = threading.RLock()
_CONFIGURED = False


class SafeTransportError(RuntimeError):
    """A fixed wrapper carrying only validated diagnostics across transport layers."""
    def __init__(self, *, cause=None, http_status=None):
        super().__init__('transport_request_failed')
        fields = exception_metadata(cause) if cause is not None else {'exception_category':'unknown'}
        fields.update(safe_fields({'http_status':http_status}))
        if fields.get('http_status', 0) >= 400:
            fields['exception_category'] = 'http'
        fields['error_code'] = 'transport_request_failed'
        self.diagnostics = safe_fields(fields)


def exception_metadata(exc):
    try:
        return _exception_metadata(exc)
    except Exception:
        return {'exception_category':'unknown', 'error_code':'runtime_failure'}


def _exception_metadata(exc):
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
    if isinstance(exc, SafeTransportError):
        result.update(safe_fields(exc.diagnostics))
    # SDK status/request_id are documented fields; never scan headers or body.
    loaded = sys.modules.get('openai')
    cls = getattr(loaded, 'APIStatusError', None) if loaded else None
    if isinstance(cls, type) and isinstance(exc, cls):
        try:
            result.update(safe_fields({'http_status':exc.status_code, 'provider_request_id':exc.request_id}))
        except Exception:
            pass
    for module, name in (('httpx', 'HTTPStatusError'), ('requests.exceptions', 'HTTPError')):
        loaded = sys.modules.get(module)
        cls = getattr(loaded, name, None) if loaded else None
        if isinstance(cls, type) and isinstance(exc, cls):
            try:
                result.update(safe_fields({'http_status':exc.response.status_code}))
            except Exception:
                pass
    protocol = sys.modules.get('subscription_protocol')
    cls = getattr(protocol, 'ProbeError', None) if protocol else None
    if isinstance(cls, type) and isinstance(exc, cls):
        result['exception_category'] = 'protocol'
        try:
            result.update(safe_fields({'http_status':getattr(exc, 'http_status', None),
                                      'provider_request_id':getattr(exc, 'provider_request_id', None)}))
        except Exception:
            pass
    return result


def _context():
    module = sys.modules.get('profiling')
    return module.CURRENT.get() if module else None


def _fields(value):
    # Foreign factories/extra fields are untrusted even when keys look internal.
    return safe_fields({key:item for key,item in value.items() if type(key) is str}) if type(value) is dict else {}


def _normalize(record):
    """Copy only validated fields AFTER Logger.makeRecord has merged extra."""
    data = vars(record)
    name, message = data.get('name'), data.get('msg')
    component = name if type(name) is str and name in COMPONENTS else 'library'
    allowed = EVENTS | frozenset(TEMPLATES.values())
    event_name = (message if message in allowed else TEMPLATES.get(message, 'runtime.notice')) if type(message) is str else 'runtime.notice'
    level = data.get('levelno')
    level = level if type(level) is int and level in (10,20,30,40,50) else 40
    safe = logging.LogRecord(component, level, '', 0, event_name, (), None)
    created = data.get('created')
    if type(created) in (int, float) and math.isfinite(created) and 0 <= created <= 32503680000:
        safe.created = created
    safe.threadName, safe.processName = 'worker', 'process'
    state = _context() or {}
    context = {}
    for key in ('request_id', 'scope_id'):
        value = state.get(key)
        context[key] = value if type(value) is str and re.fullmatch(r'[0-9a-f]{32}', value) else None
    job = state.get('job_id')
    context['job_id'] = job if type(job) is int and job > 0 else None
    context['channel'] = state.get('channel') if state.get('channel') in ('web','telegram','cli','background') else None
    context['scope'] = state.get('scope') if state.get('scope') in ('processing','submission','delivery','background') else None
    context.update(_fields({key:state.get(key) for key in ('round_index','tool_index','operation_id')}))
    safe.k90_context = context
    exc_info = data.get('exc_info')
    if type(exc_info) is tuple and len(exc_info) == 3 and isinstance(exc_info[1], BaseException):
        safe.k90_meta = exception_metadata(exc_info[1])
    else:
        safe.k90_meta = _fields(data.get('k90_meta'))
    safe.k90_fields = _fields(data.get('k90_fields'))
    return safe


def _operational_record(record):
    safe = _normalize(record)
    value = dict(utc=datetime.fromtimestamp(safe.created, timezone.utc).isoformat(),
                 level=safe.levelname, component=safe.name, event=safe.msg)
    value.update(safe.k90_meta)
    value.update(safe.k90_fields)
    value.update(safe.k90_context)
    return value


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
            sys.stderr.write(json.dumps(_operational_record(record), separators=(',', ':')) + '\n')
            sys.stderr.flush()
        except Exception:
            _alarm()


def _dispatch(logger, record):
    """Own standard logging emission, including late non-propagating loggers.

    Arbitrary library handlers/formatters are not output sinks. This boundary is
    after extra and logger filters, and is independent of the record factory.
    """
    try:
        safe = _normalize(record)
        _DURABLE.handle(safe)
        _CONSOLE.handle(safe)
        # Preserve pytest's in-memory observers with the sanitized copy only.
        # Production output is exclusively the two controlled handlers above.
        for handler in tuple(logging.getLogger().handlers):
            if handler.__class__.__module__.startswith('_pytest.') and safe.levelno >= handler.level:
                try:
                    handler.handle(safe)
                except Exception:
                    _alarm()
    except Exception:
        _alarm()


_DURABLE = SafeHandler()
_CONSOLE = SafeConsole()


def configure_logging():
    """Establish safe output first, with no dependency on factory installation."""
    global _CONFIGURED
    # One class-level dispatch boundary covers existing and future standard
    # loggers without scanning the registry or calling arbitrary handlers.
    logging.Logger.callHandlers = _dispatch
    try:
        with _CONFIG_LOCK:
            sys.excepthook = _uncaught
            threading.excepthook = _thread_uncaught
            if not _CONFIGURED:
                logging.getLogger().setLevel(logging.INFO)
                _CONFIGURED = True
    except Exception:
        _alarm()


EVENTS = frozenset(('telegram.submitted', 'telegram.ingress_failed', 'telegram.unavailable', 'provider.failed', 'stage.failed', 'tool.failed', 'tool.completed', 'response.completed',
    'runtime.unhandled', 'response.failed', 'delivery.completed', 'delivery.failed', 'job.completed', 'job.failed'))
CODES = frozenset(('runtime_failure', 'provider_request_failed', 'stage_failed', 'tool_returned_error', 'transport_request_failed'))
CATEGORIES = frozenset(('unknown','timeout','connection','validation','permission','io','http','protocol'))


def safe_fields(fields):
    result = {}
    for key, value in fields.items():
        if key == 'backend_request_id' and type(value) is str and re.fullmatch(r'[0-9a-f]{32}', value):
            result[key] = value
        elif key == 'backend_job_id' and type(value) is int and value > 0:
            result[key] = value
        elif key in ('round_index', 'tool_index') and type(value) is int and 0 < value <= 4096:
            result[key] = value
        elif key == 'http_status' and type(value) is int and 100 <= value <= 599:
            result[key] = value
        elif key == 'provider_request_id' and type(value) is str and re.fullmatch(r'req_[A-Za-z0-9_-]{8,96}', value):
            result[key] = value
        elif key == 'operation_id' and type(value) is str and re.fullmatch(r'[0-9a-f]{32}:[1-9][0-9]{0,3}:[1-9][0-9]{0,3}', value):
            result[key] = value
        elif key == 'exception_category' and type(value) is str and value in CATEGORIES:
            result[key] = value
        elif key == 'error_code' and type(value) is str and value in CODES:
            result[key] = value
        elif key == 'mutation_outcome' and type(value) is str and value in ('committed','rolled_back','none','unknown'):
            result[key] = value
        elif key in ('response_outcome','delivery_outcome') and type(value) is str and value in ('completed','failed','pending','unknown','none'):
            result[key] = value
        elif key == 'tool_outcome' and type(value) is str and value in ('returned','error'):
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
        logging.getLogger(component).log(logging.ERROR if error is not None or name.endswith('.failed') or fields.get('tool_outcome') == 'error' else logging.INFO,
            name, extra={'k90_fields':safe_fields(fields)})
    except Exception:
        _alarm()


def _uncaught(exc_type, exc, traceback):
    # Python's default hook prints arbitrary exception text and source lines.
    event('runtime.unhandled', component='runtime', error=exc)


def _thread_uncaught(args):
    _uncaught(args.exc_type, args.exc_value, args.exc_traceback)
