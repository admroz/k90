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


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "k90:test"
    name = "k90-smoke-" + uuid.uuid4().hex[:10]
    # No volume is mounted, and --network none prevents real Telegram/LLM/source access.
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            "none",
            "-e",
            "WEB_PASSWORD=smoke-test-password",
            "-e",
            "WEB_COOKIE_SECURE=false",
            "-e",
            "TELEGRAM_BOT_TOKEN=123:offline-test",
            "-e",
            "TELEGRAM_ALLOWED_USER_ID=123",
            "-e",
            "K90_PREVIEW=true",
            "-e",
            "K90_SYNC_ENABLED=false",
            image,
        ],
        check=True,
    )
    try:
        ready = False
        for _ in range(40):
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)",
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("Backend did not start")
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
        print("Container smoke test passed, including isolated Telegram restart.")
    finally:
        subprocess.run(["docker", "logs", "--tail", "50", name], check=False)
        # This removes only the unique disposable container created above, with no user volumes.
        subprocess.run(["docker", "rm", "-f", name], check=False)


if __name__ == "__main__":
    main()
