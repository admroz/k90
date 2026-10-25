# SIWC host-ID fix — local executor evidence

Branch: `fix/oauth-host-id`; baseline `17beba2353cbc1e1a2d39d71bc9b5a78f11a2ed4`.
Scope: only the confirmed UUID host-ID bug; no device/runtime migration.

Official primary source, retrieved 2026-10-25:
[OpenAI SIWC overview](https://developers.openai.com/siwc/token-sharing-open-source),
“Host-ID” section: persist a UUIDv4 prefixed with `urn:uuid:`; JWK thumbprint URIs
and `did:key` are also supported. No invented replacement identity format.

## Implementation and review

`subscription_host.initialize_host` is the existing initialization boundary moved
into one shared module, used by both the operator CLI (same public import) and
`subscription_protocol.authorize`. New IDs use UUIDv4 URNs. The existing store lock,
registration symlink refusal and private atomic writer remain in use.
Only an exact lowercase canonical bare UUIDv4 in a registration with **only**
`host_id`, and no `credentials.json` filesystem entry, is migrated. The UUID itself
is preserved. Even empty/unknown binding metadata blocks migration. Credential
presence uses `lexists`, including dangling symlinks, without opening credentials.
Missing registration with credentials also fails closed. Bound legacy identity
raises the fixed code `host_identity_bound`; no reset or rotation is attempted.

Existing other IDs remain untouched, including valid URNs, JWK and did:key values.
This narrow repair does not add a general parser/validator for other ID formats:
noncanonical legacy UUID representations are not guessed or rewritten. Existing
synthetic-host fixtures in injected login/import mocks remain unchanged; protocol
boundary tests independently inspect the outgoing `ext_agent_host_id`. Signature,
audience, nonce, state, scope, token validation and API fallback behavior are unchanged.

Tests cover UUID stability, migration idempotence/private mode, metadata and
credential-file protection, credential and registration symlinks, JWK/did:key
preservation and shared authorize behavior using an intercepted browser function.
No real browser is opened; protocol callbacks and all tokens are synthetic.

## Exact verification commands and results

Initial quota/lock/status review:

```sh
/opt/hermes/.venv/bin/hermes usage --json
flock -n /opt/data/jobs/k90-autonomy/worker.lock -c 'echo LOCK_AVAILABLE'
```

Lock available. Quota readings (UTC, Session/Weekly): 22:21:29 42%/41%,
22:22:41 44%/41%, 22:23:24 45%/41%, 22:24:36 46%/41%,
22:25:22 47%/41%, 22:26:46 49%/42%. No reset or paid fallback.

An initial host-ID pytest invocation used the command below **without**
`PYTHON_DOTENV_DISABLED=1`. It exited 4 during conftest import: the supplied audit
guard blocked automatic `.env` opening before any contents were read. All subsequent
runs disabled dotenv explicitly, keeping that guard active.

Expanded tests before implementation (RED):

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-host-id-fix/home DB_PATH=/opt/data/cache/scratch/k90-host-id-fix/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-host-id-fix/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-host-id-fix/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q tests/test_subscription_host_identity.py > /opt/data/cache/scratch/k90-host-id-fix/red.log 2>&1
```

10 failed / 8 passed. After the first implementation, the relevant subset passed
42 tests; after protocol/idempotence/missing-registration tests, 48 passed.
Further TDD for unknown/verified metadata:

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-host-id-fix/home DB_PATH=/opt/data/cache/scratch/k90-host-id-fix/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-host-id-fix/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-host-id-fix/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q tests/test_subscription_host_identity.py > /opt/data/cache/scratch/k90-host-id-fix/red-metadata.log 2>&1
```

2 failed / 24 passed, then restricted migration to the original host-only shape.

Final relevant subset:

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-host-id-fix/home DB_PATH=/opt/data/cache/scratch/k90-host-id-fix/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-host-id-fix/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-host-id-fix/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q tests/test_subscription_host_identity.py tests/test_subscription_login.py tests/test_subscription_auth.py tests/test_subscription_protocol.py tests/test_subscription_api.py > /opt/data/cache/scratch/k90-host-id-fix/targeted.log 2>&1
```

50 passed in 3.84s (exit 0).

Full offline regression:

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-host-id-fix/home DB_PATH=/opt/data/cache/scratch/k90-host-id-fix/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-host-id-fix/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-host-id-fix/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q > /opt/data/cache/scratch/k90-host-id-fix/full.log 2>&1
```

Exit 1: 432 passed / 1 skipped / 1 failed in 83.18s. The failure was
`test_working_copy_preserves_source_and_drops_pending_transport_jobs`: it creates
a synthetic `.env` fixture in default `/tmp`, outside the guard's allowlisted
scratch root. No application assertion failed. Rerun with the fixture temp directory
inside the existing guard allowlist (guard unchanged):

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-host-id-fix/home DB_PATH=/opt/data/cache/scratch/k90-host-id-fix/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-host-id-fix/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-host-id-fix/auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. /opt/data/projects/k90/.venv/bin/python -m pytest -q --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-oauth-host-id-fix > /opt/data/cache/scratch/k90-host-id-fix/full-safe-temp.log 2>&1
```

Exit 0: **433 passed / 1 skipped in 86.25s**. The skip is the existing
unselected downloaded-backup import test. No test or guard was weakened.

Collection used the same environment and `python -m pytest --collect-only -q`,
saved to `/opt/data/cache/scratch/k90-host-id-fix/collected.log` to identify the
fixture failure. Final source review includes all five intended files and
`git diff --check` (exit 0). No secrets or patient data are included.

## Limits

Local source and synthetic offline evidence only. No Docker access/test, production
credential/config/database reads, real OAuth/login/inference, deployment, push, PR,
merge or main/upstream write. Coordinator verification remains required before push.
