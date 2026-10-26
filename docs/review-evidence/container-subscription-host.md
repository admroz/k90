# Naprawa pakowania subscription_host — 2026-10-26

Gałąź `fix/container-subscription-host`; baza `upstream/main`:
`60a8b8529f9d2aca5fc5b169ddbd25639711cebe`.
Wykonawca: rzeczywisty Codex CLI (`codex exec`, gpt-6.1-sol), potwierdzony
w procesie dla tego checkoutu. Bez dodatkowego agenta.
Przeczytano AGENTS.md, docs/STATUS.md i docs/IMPLEMENTATION_PLAN.md.
Sprawdzono flock, następnie utrzymano blokadę worker.lock podczas zmian.

Zakres: dopisanie subscription_host.py do istniejącego jawnego COPY końcowego
stage app i trzy wykonywalne importy na początku CHECK przed HTTP/chatem.
Zachowano test koordynatora bez zmian i bez osłabienia asercji. Nie zmieniono
logiki auth/summary, prywatności, konfiguracji ani workflow.

RED wykazał dokładnie brak subscription_host.py w COPY oraz brak
subscription_host, subscription_login, summary w CHECK.
Polecenia wykonano z /opt/data/projects/k90-container-host.
Nowe HOME/data/auth i basetemp są pod allowlistowanym scratch, bez dziedziczenia
środowiska, z wyłączonym dotenv i guardem sieci w sitecustomize.py.
Nie czytano produkcyjnych danych ani poprzednich magazynów OAuth.

RED przed zmianą — exit 1, 2 failed in 0.06s

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q tests/test_container_subscription_imports.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/pytest-red
```

GREEN — exit 0, 54 passed in 6.47s

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q tests/test_container_subscription_imports.py tests/test_subscription_*.py tests/test_summary.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/pytest-green
```

Pełna regresja — exit 0: 484 passed, 1 skipped in 105.68s (0:01:45)

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q --basetemp=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/pytest-full > /opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/full.log 2>&1
```

Frontend — oba exit 0, 21 passed:

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home node --check web/app.js
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home node --test tests/web_*.test.mjs > /opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/node.log 2>&1
```

Dodatkowy import rzeczywistego prefiksu CHECK na hoście (nie obrazu), exit 0.
Wynik: `PASS: actual CHECK import prefix; no DB or credential storage opened; offline guard active`.
LiteLLM próbował pobrać publiczną mapę kosztów przy imporcie; guard zablokował
sieć zewnętrzną i użyto lokalnej mapy. Bez logowania/inference.
Dokładne polecenie:

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/container-subscription-host/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. K90_PREVIEW=true K90_SYNC_ENABLED=false /opt/data/projects/k90/.venv/bin/python - <<'PY'
import ast
import os
from pathlib import Path
import sys
from scripts.smoke_container import CHECK
state = Path(os.environ['K90_CHATGPT_STATE_DIR'])
def audit(event, args):
    if event == 'sqlite3.connect':
        raise AssertionError('Imports must not open a database')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        if path == state or state in path.parents:
            raise AssertionError('Imports must not open credential storage')
sys.addaudithook(audit)
imports = []
for node in ast.parse(CHECK).body:
    if not isinstance(node, (ast.Import, ast.ImportFrom)):
        break
    imports.append(node)
exec(compile(ast.Module(body=imports, type_ignores=[]), '<smoke-import-prefix>', 'exec'))
assert {'subscription_login', 'subscription_host', 'summary'} <= set(sys.modules)
print('PASS: actual CHECK import prefix; no DB or credential storage opened; offline guard active')
PY
```

Przejrzano Dockerfile, scripts/smoke_container.py, test koordynatora,
importy subscription_login/host/summary i zależności oraz istniejący workflow
.github/workflows/docker.yml. CHECK wykonuje docker exec przed i po restarcie
Telegrama. Kontener już ma K90_PREVIEW=true, K90_SYNC_ENABLED=false,
--network none i brak montowanych wolumenów. Importy nie wywołują initialize_host,
TokenStore, logowania ani generatora summary.

Quota `/opt/hermes/.venv/bin/hermes usage --json`: 07:13:21 UTC 9% Session / 1%
Weekly; 07:14:35 UTC 11% / 2%; 07:16:26 UTC 12% / 2%. Resety 2026-10-26T12:00:27Z /
2026-11-02T07:00:27Z. Bez resetu i płatnego fallbacku.

Ograniczenia: nie uruchomiono Docker build, kontenera ani jego smoke; nie użyto
socketu Docker. Autentyczna weryfikacja obrazu pozostaje bramką koordynatora
po jego push i utworzeniu PR: GitHub Actions, job test, krok „Build and exercise
container without external network” wykonuje `docker build -t k90:test .`,
`python scripts/smoke_build_context.py k90:test` i
`python scripts/smoke_container.py k90:test`. Wymagany SUCCESS na dokładnym
commicie PR; ten raport nie stanowi dowodu takiego wykonania.
Bez push, PR, merge, deployment, zapisu main/upstream lub operacji produkcyjnych.

Kontrola końcowa: `git diff --check` exit 0; przegląd wszystkich czterech
plików zmian. Test koordynatora dodany do commita w oryginalnej postaci.
