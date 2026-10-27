"""Bounded local JSON logs for the Linux container; no payload formatting.

Every write reopens under flock so backend and Telegram share rotation safely.
Logging failures are deliberately isolated from application results.
"""
import fcntl
import logging
from logging.handlers import RotatingFileHandler
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


CODES = frozenset(('runtime_failure', 'provider_request_failed', 'stage_failed', 'tool_returned_error', 'transport_request_failed'))
CATEGORIES = frozenset(('unknown','timeout','connection','validation','permission','io','http','protocol'))


def safe_fields(fields):
    result = {}
    for key, value in fields.items():
        if key in ('fetched','inserted','updated','unchanged','attempts','prompt_tokens','completion_tokens','history_records','context_sections','context_chars','summary_chars','input_chars','response_chars','text_chars','chars','files','bytes') and type(value) is int and 0 <= value <= 10**12:
            result[key] = value
        elif key == 'backend_request_id' and type(value) is str and re.fullmatch(r'[0-9a-f]{32}', value):
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


EVENTS = frozenset((
    'agent.error', 'agent.failure_record.unavailable', 'agent.finish',
    'agent.max_rounds', 'agent.start', 'agent.tool_result',
    'agent.tools', 'agent.usage', 'conversation.claim',
    'conversation.failed', 'conversation.sync_failed', 'conversation.worker_error',
    'delivery.completed', 'delivery.failed', 'garmin.auto_sync_failed',
    'garmin.auto_sync_no_changes', 'garmin.fetch_failed', 'garmin.login_failed',
    'garmin.sync', 'garmin.sync.progress', 'job.completed',
    'job.failed', 'libre.auto_sync_failed', 'libre.auto_sync_no_changes',
    'libre.fetch_failed', 'libre.sync', 'libre.sync.progress',
    'memory.worker.unavailable', 'provider.failed', 'response.completed',
    'response.failed', 'runtime.unhandled', 'stage.failed',
    'summary.async_refresh', 'summary.attempt', 'summary.auto_sync_refresh_failed',
    'summary.fallback', 'summary.refresh', 'summary.refresh_failed',
    'summary.saved', 'summary.startup_refresh_failed', 'telegram.allowed_user_missing',
    'telegram.connected', 'telegram.disabled', 'telegram.image',
    'telegram.image_error', 'telegram.image_rejected', 'telegram.ingress_failed',
    'telegram.message', 'telegram.poll_error', 'telegram.reject',
    'telegram.response', 'telegram.sent', 'telegram.stopped',
    'telegram.submitted', 'telegram.unavailable', 'telegram.update_error',
    'tool.completed', 'tool.failed',
))
COMPONENTS = frozenset(('agent', 'web_runtime', 'webapp', 'telegram_adapter', 'server',
    'summary', 'memory_runtime', 'tools', 'tools.garmin', 'tools.libre',
    'outbound_policy', 'responses_api', 'subscription_api', 'fetch_garmin', 'fetch_libre', 'runtime'))
_CONFIG_LOCK = threading.RLock()
_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = json.dumps(record.safe_record, separators=(',', ':'), allow_nan=False)
        if len((payload+'\n').encode('utf-8')) > 8192:
            raise ValueError('record_too_large')
        return payload


class FlockRotatingFileHandler(RotatingFileHandler):
    """Reopen under the shared lock so both container processes rotate together."""
    def _open(self):
        return os.fdopen(_open(self.baseFilename), 'a', encoding='utf-8')

    def emit(self, record):
        lock = None
        try:
            directory = Path(self.baseFilename).parent
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if directory.is_symlink():
                raise OSError('invalid_log_directory')
            directory.chmod(0o700)
            lock = _open(self.baseFilename + '.lock')
            fcntl.flock(lock, fcntl.LOCK_EX)
            # BaseRotatingHandler handles format/rollover/write failures here.
            super().emit(record)
        except Exception:
            self.handleError(record)
        finally:
            try:
                if self.stream is not None:
                    self.stream.close()
            except Exception:
                _alarm()
            finally:
                self.stream = None
                if lock is not None:
                    os.close(lock)

    def handleError(self, record):
        _alarm()


class ConsoleHandler(logging.StreamHandler):
    def emit(self, record):
        # Resolve stderr at emission, including application launch/test capture.
        self.stream = sys.stderr
        super().emit(record)

    def handleError(self, record):
        _alarm()


class FrameworkErrorHandler(logging.Handler):
    def emit(self, record):
        error = record.exc_info[1] if record.exc_info else None
        event('runtime.unhandled', component='runtime', error=error, level=logging.ERROR)


KNOWN_LIBRARIES = ('litellm', 'LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy',
    'openai', 'httpx', 'httpcore', 'requests', 'urllib3', 'garminconnect', 'garth', 'libre_link_up')
_DESTINATION = None


def silence_libraries():
    """Known SDK settings, also applied after LiteLLM's import-time setup."""
    for name in KNOWN_LIBRARIES:
        logger = logging.getLogger(name)
        logger.handlers[:] = [logging.NullHandler()]
        logger.setLevel(logging.CRITICAL + 1)
        logger.propagate = False
        logger.disabled = True


def configure_logging():
    """Configure owned sinks and the finite SDK/framework launch boundaries."""
    global _CONFIGURED, _DESTINATION
    try:
        with _CONFIG_LOCK:
            directory = Path(os.getenv('DATA_DIR', str(Path(__file__).parent/'data'))) / 'logs'
            destination = (str(directory), tuple(LIMITS.items()), BACKUPS)
            if _CONFIGURED and destination == _DESTINATION:
                return
            for name in ('k90.app', 'k90.profile'):
                logger = logging.getLogger(name)
                for handler in logger.handlers:
                    handler.close()
                logger.handlers.clear()
                logger.setLevel(logging.DEBUG)
                logger.propagate = False
            formatter = JsonFormatter()
            for filename, limit in LIMITS.items():
                handler = FlockRotatingFileHandler(directory/filename, maxBytes=limit,
                    backupCount=BACKUPS, delay=True, encoding='utf-8')
                handler.setFormatter(formatter)
                handler.setLevel(logging.ERROR if filename == 'errors.log' else logging.DEBUG)
                logging.getLogger('k90.profile' if filename == 'profiling.jsonl' else 'k90.app').addHandler(handler)
            console = ConsoleHandler()
            console.setFormatter(formatter)
            logging.getLogger('k90.app').addHandler(console)
            root = logging.getLogger()
            root.handlers[:] = [logging.NullHandler()]
            silence_libraries()
            access = logging.getLogger('uvicorn.access')
            access.handlers[:] = [logging.NullHandler()]
            access.propagate = False
            access.disabled = True
            framework = logging.getLogger('uvicorn.error')
            framework.handlers[:] = [FrameworkErrorHandler()]
            framework.setLevel(logging.ERROR)
            framework.propagate = False
            sys.excepthook = _uncaught
            threading.excepthook = _thread_uncaught
            _DESTINATION = destination
            _CONFIGURED = True
    except Exception:
        _alarm()


def write_record(name, record):
    """Internal bridge: callers supply a constructed content-free record."""
    try:
        configure_logging()
        logger = logging.getLogger('k90.profile' if name == 'profiling.jsonl' else 'k90.app')
        level = {'DEBUG':10, 'INFO':20, 'WARNING':30, 'ERROR':40, 'CRITICAL':50}.get(record.get('level'), 20)
        logger.log(level, '', extra={'safe_record': record})
    except Exception:
        _alarm()


def event(name, *, component='agent', error=None, level=None, **fields):
    """Explicit application event; never interpolate private messages or errors."""
    try:
        if name not in EVENTS or component not in COMPONENTS:
            return
        if level is None:
            level = logging.ERROR if error is not None or name.endswith('.failed') or fields.get('tool_outcome') == 'error' else logging.INFO
        if level not in (10,20,30,40,50):
            return
        record = dict(utc=datetime.now(timezone.utc).isoformat(),
            level={10:'DEBUG',20:'INFO',30:'WARNING',40:'ERROR',50:'CRITICAL'}[level], component=component, event=name)
        if error is not None:
            record.update(exception_metadata(error))
        record.update(safe_fields(fields))
        state = _context() or {}
        for key in ('request_id','scope_id','job_id','channel','scope'):
            record[key] = state.get(key)
        record.update(safe_fields({key:state.get(key) for key in ('round_index','tool_index','operation_id')}))
        write_record('app.log', record)
    except Exception:
        _alarm()


def _uncaught(exc_type, exc, traceback):
    event('runtime.unhandled', component='runtime', error=exc)


def _thread_uncaught(args):
    _uncaught(args.exc_type, args.exc_value, args.exc_traceback)
