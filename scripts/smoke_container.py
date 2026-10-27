"""CI integration check: real image, no external network, synthetic data only."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid

CHECK = r"""
import json, time, urllib.request, http.cookiejar
import subscription_login
import subscription_host
import summary
def check_photo_history_in_runtime():
    # Run shipped agent code against this container's synthetic DB, without sync.
    import base64, os, random, struct, uuid, zlib
    from copy import deepcopy
    from unittest.mock import patch
    from k90_memory import PrivacyError
    from tools.db import get_conn

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    side = 1280
    stride = side * 3
    pixels = random.Random(90).randbytes(side * side * 3)
    scanlines = b''.join(b'\0' + pixels[i:i+stride] for i in range(0, len(pixels), stride))
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', side, side, 8, 2, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))
    from tools.images import MAX_IMAGE_BYTES
    assert MAX_IMAGE_BYTES * .95 < len(png) <= MAX_IMAGE_BYTES
    encoded = base64.b64encode(png).decode('ascii')
    uri = 'data:image/png;base64,' + encoded
    photo = [{'type': 'text', 'text': 'Synthetic millet lunch, synthetic@example.invalid'},
             {'type': 'image_url', 'image_url': {'url': uri}}]
    owner = 'container-photo-' + uuid.uuid4().hex
    sent, requests, tokens = [], [], []
    answer = 'Synthetic millet; what portion?'

    class FakeTokenStore:
        def __init__(self, *args):
            pass
        def access_token(self):
            tokens.append(True)
            return 'synthetic-container-token'

    def request(url, **kwargs):
        requests.append(url)
        assert kwargs['token'] == 'synthetic-container-token'
        if url.endswith('/models'):
            # Synthetic catalog only; no claim about a real account's models.
            return {'models': [{'slug': agent.MODEL.removeprefix('openai/'), 'visibility': 'list'}]}
        assert url.endswith('/responses')
        sent.append(deepcopy(kwargs['data']))
        return {'status': 'completed', 'output': [{'type': 'message', 'role': 'assistant',
                'content': [{'type': 'output_text', 'text': answer}]}],
                'usage': {'input_tokens': 12, 'output_tokens': 4}}

    with patch.dict(os.environ, {'K90_AGENT_AUTH': 'chatgpt',
            'K90_ALLOW_MODEL_IMAGES': 'true', 'K90_MEMORY_BACKEND': 'local'}):
        import agent
        with patch('subscription_auth.TokenStore', FakeTokenStore), patch('subscription_api.request_json', request):
            assert agent.run_agent(photo, owner) == (answer, False)
            images = [p['image_url'] for item in sent[0]['input']
                      for p in item.get('content', []) if p.get('type') == 'input_image']
            assert images == [uri]
            assert base64.b64decode(images[0].split(',', 1)[1], validate=True) == png
            assert 'synthetic@example.invalid' not in json.dumps(sent[0])
            assert '[REDACTED]' in json.dumps(sent[0])
            os.environ['K90_ALLOW_MODEL_IMAGES'] = 'false'
            assert agent.run_agent('Millet lunch: 150 g, steamed', owner) == (answer, False)
            assert len(sent) == 2
            followup = json.dumps(sent[1])
            assert 'Historical image omitted' in followup and answer in followup
            assert 'Synthetic millet lunch' in followup and '150 g, steamed' in followup
            assert all(value not in followup for value in ('image_url', 'input_image', 'base64', encoded))
            assert 'synthetic@example.invalid' not in followup
            with get_conn() as conn:
                rows = conn.execute('SELECT role, content FROM conversations WHERE user_id=? ORDER BY id',
                                    (owner,)).fetchall()
                assert len(rows) == 4 and json.loads(rows[0]['content']) == photo
                original = conn.execute("SELECT payload FROM agent_events WHERE owner=? AND kind='incoming' ORDER BY id LIMIT 1",
                                        (owner,)).fetchone()
                assert json.loads(original['payload']) == photo
            before = (len(requests), len(tokens))
            for blocked in ('[local-only] synthetic meal', 'Bearer synthetic-secret'):
                try:
                    agent.run_agent(blocked, owner + '-blocked-' + uuid.uuid4().hex)
                except PrivacyError:
                    pass
                else:
                    raise AssertionError('Restricted input reached provider')
            assert (len(requests), len(tokens)) == before
    print('Shipped agent photo/history, original persistence and outbound policy passed (synthetic provider).')

check_photo_history_in_runtime()

def check_observability_in_runtime():
    import io, json, logging, os, tempfile
    from unittest.mock import patch
    from k90_memory import PrivacyError, PrivacyPolicy
    from outbound_policy import sanitize_payload
    from web_runtime import init_runtime, enqueue, ConversationWorker, timeline
    from agent import save_history
    capture = io.StringIO()
    logger = logging.getLogger('agent')
    handler = logging.StreamHandler(capture)
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        with tempfile.TemporaryDirectory() as scratch, patch.dict(os.environ, {
                'DB_PATH': scratch + '/synthetic.db', 'DATA_DIR': scratch,
                'CONVERSATION_USER_ID': 'synthetic-smoke',
                'K90_TEXT_FILTER_ENABLED': 'false', 'K90_PROFILING_ENABLED': 'true',
                'K90_MEMORY_BACKEND': 'disabled'}):
            assert sanitize_payload('synthetic@example.invalid') == 'synthetic@example.invalid'
            try:
                PrivacyPolicy().sanitize_text('Bearer synthetic-secret')
            except PrivacyError:
                pass
            else:
                raise AssertionError('HS baseline was disabled')
            init_runtime()
            first = enqueue('web:synthetic-failed', 'synthetic first')
            def fail(_):
                raise RuntimeError('private diagnostic must not escape')
            assert ConversationWorker(fail).run_once()
            second = enqueue('telegram:synthetic-later', 'synthetic later', 'telegram', 123)
            def succeed(content):
                save_history('synthetic-smoke', content, 'synthetic answer')
                return 'synthetic answer'
            assert ConversationWorker(succeed).run_once()
            rows = timeline('synthetic-smoke')
            assert len(rows) == 4 and rows[1]['state'] == 'failed' and rows[-1]['state'] == 'done'
            assert rows[-1]['content'] == 'synthetic answer'
            assert timeline('synthetic-other') == []
            assert timeline('synthetic-smoke', rows[2]['id']) == rows[:2]
            assert timeline('synthetic-smoke') == rows
            from pathlib import Path
            events = [json.loads(line) for line in (Path(scratch)/'logs'/'profiling.jsonl').read_text().splitlines()]
            assert 'agent.phase' not in capture.getvalue()
            assert 'logging_setup.py' in __import__('sys').modules['logging_setup'].__file__
            ids = {first['profile_id'], second['profile_id']}
            correlated = [r for r in events if r['request_id'] in ids]
            assert {r['request_id'] for r in correlated} == ids
            assert {'queue_wait', 'processing', 'persistence'} <= {r['stage'] for r in correlated}
            assert 'private diagnostic' not in capture.getvalue()
            assert 'synthetic@example.invalid' not in capture.getvalue()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
    print('Timeline, model filter switch, HS baseline and profiling runtime passed (synthetic offline).')

check_observability_in_runtime()

def check_catalog_in_runtime():
    import os, sqlite3, tempfile
    from unittest.mock import patch
    from tools.db import init_db, get_conn, create_db_backup
    from tools.food_catalog import propose, confirm, log_portion, revise
    from tools.food_off import lookup
    with tempfile.TemporaryDirectory() as scratch, patch.dict(os.environ, {
            'DB_PATH': scratch+'/catalog.db', 'DATA_DIR': scratch,
            'BACKUP_DIR': scratch+'/backups'}):
        init_db()
        draft = propose(dict(name='Synthetic container skyr', brand='Fixture', barcode='5900531004544',
                             basis='100g', kcal=64, protein=12, carbs='4,1', fat=0, provenance='manual'))
        init_db()
        product = confirm(draft['id'], 1)
        assert lookup('5900531004544') == product  # Local lookup must need no network.
        result = log_portion(product['id'], 2, 150, 'g', 'container-portion')
        assert result['nutrition'] == dict(kcal=96, protein=18, carbs=6.15, fat=0)
        assert log_portion(product['id'], 2, 150, 'g', 'container-portion') == result
        edited = dict(product, kcal=80)
        assert revise(product['id'], 2, edited)['status'] == 'draft'
        with get_conn() as conn:
            assert conn.execute('SELECT count(*) FROM posilki').fetchone()[0] == 1
            assert conn.execute('SELECT kalorie FROM posilki').fetchone()[0] == 96
        backup = create_db_backup()
        with sqlite3.connect(backup['path']) as conn:
            assert conn.execute('SELECT count(*) FROM food_product_versions').fetchone()[0] == 3
    print('Catalog migration, local lookup, review, portion snapshot/idempotency and backup passed (synthetic offline).')

check_catalog_in_runtime()

base = 'http://127.0.0.1:8000'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path, body=None):
    request = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json', 'X-K90-Request':'1'})
    with client.open(request, timeout=5) as response:
        return json.load(response)
assert call('/healthz')['ok']
call('/api/login', {'password':'smoke-test-password'})
assert call('/api/dashboard')['latest']['waga'] is None
with client.open(base+'/static/app.js') as response:
    assert response.status == 200
call('/api/messages', {'request_id':'web:smoke', 'text':'hello'})
deadline = time.monotonic()+10
while time.monotonic()<deadline:
    rows = call('/api/messages')
    if len(rows)==2 and rows[-1].get('state') == 'done':
        assert rows[-1]['role']=='assistant'
        break
    time.sleep(.1)
else:
    raise AssertionError('Conversation worker did not answer')
assert call('/api/session')['telegram_enabled']
print('HTTP, static assets and chat work while Telegram has no network.')
"""



LOG_WRITER = r"""
import os, sys
os.environ['DATA_DIR'] = os.getenv('K90_LOG_SMOKE_DIR', '/data/log-smoke')
os.environ['K90_PROFILING_ENABLED'] = 'true'
import logging_setup as logs, profiling
logs.LIMITS.update({name:4096 for name in logs.LIMITS})
with profiling.request_scope('cli', sys.argv[1]*32):
    for index in range(1,9):
        profiling.indices(index,1)
        with profiling.span('tool'):
            logs.event('tool.failed', error=TimeoutError('CANARY_LOG_SECRET'), mutation_outcome='unknown')
"""


def check_log_storage(directory, *, record=False, verify=False):
    """Same acceptance runs on host fixtures and inside the network-none image."""
    import hashlib
    import json
    from pathlib import Path
    directory = Path(directory)
    logs = directory/'logs'
    assert logs.stat().st_mode & 0o777 == 0o700
    snapshot, records = {}, {}
    for name in ('app.log', 'errors.log', 'profiling.jsonl'):
        files = [path for path in logs.glob(name+'*') if not path.name.endswith('.lock')]
        assert 1 < len(files) <= 4, (name, len(files))
        records[name] = []
        for path in files:
            assert path.stat().st_mode & 0o777 == 0o600
            raw = path.read_bytes()
            assert len(raw) <= 4096 and b'CANARY' not in raw
            snapshot[path.name] = hashlib.sha256(raw).hexdigest()
            records[name].extend(json.loads(line) for line in raw.splitlines())
    app, errors, profile = (records[name] for name in ('app.log', 'errors.log', 'profiling.jsonl'))
    assert len(app) == len(errors) == 16
    assert {row['request_id'] for row in app} == {'1'*32, '2'*32}
    assert {json.dumps(row, sort_keys=True) for row in app} == {json.dumps(row, sort_keys=True) for row in errors}
    assert all(row['component'] != 'profiling' and 'stage' not in row for row in app+errors)
    assert profile and all(row['component'] == 'profiling' for row in profile)
    marker = directory/'log-snapshot.json'
    if record:
        marker.write_text(json.dumps(snapshot, sort_keys=True))
        marker.chmod(0o600)
    if verify:
        assert json.loads(marker.read_text()) == snapshot, 'logs changed across container lifecycle'


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "k90:test"
    name = "k90-smoke-" + uuid.uuid4().hex[:10]
    volume = name + '-data'
    subprocess.run(['docker', 'volume', 'create', volume], check=True)
    command = ['docker', 'run', '-d', '--name', name, '--network', 'none',
               '--mount', 'type=volume,source='+volume+',target=/data',
               '-e', 'WEB_PASSWORD=smoke-test-password', '-e', 'WEB_COOKIE_SECURE=false',
               '-e', 'TELEGRAM_BOT_TOKEN=123:offline-test', '-e', 'TELEGRAM_ALLOWED_USER_ID=123',
               '-e', 'K90_PREVIEW=true', '-e', 'K90_SYNC_ENABLED=false', image]

    def wait_ready():
        for _ in range(40):
            result = subprocess.run(['docker', 'exec', name, 'python', '-c',
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"],
                capture_output=True, check=False)
            if result.returncode == 0:
                return
            time.sleep(.5)
        raise RuntimeError('Backend did not start')

    def storage_check(*, record=False, verify=False):
        import inspect
        code = inspect.getsource(check_log_storage) + "\ncheck_log_storage('/data/log-smoke', record="+repr(record)+", verify="+repr(verify)+")"
        subprocess.run(['docker','exec',name,'python','-c',code],check=True)

    try:
        subprocess.run(command, check=True)
        wait_ready()
        subprocess.run(["docker", "exec", name, "python", "-c", CHECK], check=True)

        def pid(program):
            return subprocess.check_output(
                [
                    "docker",
                    "exec",
                    name,
                    "supervisorctl",
                    "-c",
                    "/app/supervisord.conf",
                    "pid",
                    program,
                ],
                text=True,
            ).strip()

        backend_pid, telegram_pid = pid("backend"), pid("telegram")
        assert int(backend_pid) > 0 and int(telegram_pid) > 0
        subprocess.run(
            [
                "docker",
                "exec",
                name,
                "supervisorctl",
                "-c",
                "/app/supervisord.conf",
                "signal",
                "KILL",
                "telegram",
            ],
            check=True,
        )
        for _ in range(20):
            current = pid("telegram")
            if current not in ("0", telegram_pid):
                break
            time.sleep(0.5)
        else:
            raise AssertionError("Telegram adapter did not restart")
        assert pid("backend") == backend_pid, "Telegram crash restarted the backend"
        subprocess.run(["docker", "exec", name, "python", "-c", CHECK], check=True)
        # Two real processes in the image share flock/open/rotate/write sinks.
        children = [subprocess.Popen(['docker','exec',name,'python','-c',LOG_WRITER,str(index)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE) for index in (1,2)]
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0
            assert b'CANARY' not in stdout+stderr
            assert b'"component":"profiling"' not in stdout+stderr
        storage_check(record=True)
        subprocess.run(['docker','restart',name],check=True)
        wait_ready()
        storage_check(verify=True)
        subprocess.run(['docker','rm','-f',name],check=True)
        subprocess.run(command,check=True)  # Same disposable /data volume, new container.
        wait_ready()
        storage_check(verify=True)
        print('Container smoke passed: isolated Telegram restart, split logs and persistent /data recreate.')
    finally:
        subprocess.run(["docker", "logs", "--tail", "50", name], check=False)
        # Remove only this run's unique disposable container and synthetic volume.
        subprocess.run(["docker", "rm", "-f", name], check=False)
        subprocess.run(["docker", "volume", "rm", volume], check=False)


if __name__ == "__main__":
    main()
