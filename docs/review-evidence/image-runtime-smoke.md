# Container photo runtime smoke — 2026-10-26

Branch `fix/image-history-performance`, base `6739ffa`. Small acceptance addition;
no redesign, production access, push, PR, merge or deployment.

`CHECK` now defines and calls `check_photo_history_in_runtime()`. Both existing
Docker exec calls run it, before and after the Telegram restart. Docker still
uses `--network none`, no mounts and synthetic preview configuration. The helper
calls shipped `agent.run_agent` directly, bypassing preview HTTP and sync. Only
`subscription_auth.TokenStore` and `subscription_api.request_json` are replaced;
actual SubscriptionConversation, policy, context, local memory and persistence run.
The catalog is synthetic using the configured model slug; no real-account catalog,
OAuth refresh or inference validation is claimed.

A valid generated PNG (224×224 RGB, >128 KiB, PNG signature/chunks/CRC/zlib) is
byte-identical at mocked inference. Text email is masked. Follow-up after consent
is disabled contains the historical omission and meal text, with no image URL or
base64. Conversation and incoming event retain the original photo. Separate unique
owners test local-only and obvious secret rejection before token or provider calls.
UUID owners make repeat executions safe; blocked inputs never enter backend jobs.

Verification uses `/opt/data/projects/k90/.venv/bin/python`, `env -i`,
`PYTHON_DOTENV_DISABLED=1`, and scratch state only. Common prefix for GREEN runs:

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/runtime-smoke TMPDIR=/opt/data/cache/scratch/k90-verification-20261025/runtime-smoke DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/runtime-smoke DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/runtime-smoke/guard.db PYTHON_DOTENV_DISABLED=1 /opt/data/projects/k90/.venv/bin/python -m pytest -q
```

- RED first: `tests/test_container_photo_contract.py`: 1 failed, missing helper.
  RED used the same interpreter/clean environment and scratch HOME; AST-only test,
  before adding helper or behavioral test.
- Packaging + acceptance: append `tests/test_container_subscription_imports.py tests/test_container_photo_contract.py`:
  **4 passed in 3.57s**. Behavioral test extracts the exact helper AST and executes
  it twice against the initialized synthetic fixture DB. Initial helper run caught
  an incorrect mask expectation; fixed to `[REDACTED]`, and event column to `owner`.
- Regression command: append `tests/test_photo_history.py tests/test_opaque_images.py tests/test_history_image_performance.py tests/test_outbound_policy.py tests/test_privacy_composition.py tests/test_memory_privacy.py tests/test_privacy_json_boundary.py`.
  Result: **240 passed in 34.13s**.
- `git diff --check`: PASS. Frontend unchanged; no frontend rerun needed.
- Imports inspected: agent/summary imports do not call refresh/sync; direct
  run_agent uses read-only summary/context loading and local memory backend,
  whose start_worker does not start an HS thread.
- Quota (`/opt/hermes/.venv/bin/hermes usage --json`): 08:23:09Z 62%/10%,
  08:24:37Z 63%/10%, final 08:25:40Z 64%/10% (session/week). No reset/fallback.

Host-prefix verification PASS only. Actual built-image smoke and restart remain
for CI; no Docker/image execution is claimed here. No real credentials or patient
files were read. Existing CI remains responsible for shipped-source packaging.
