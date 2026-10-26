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
    if len(rows)==2:
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
