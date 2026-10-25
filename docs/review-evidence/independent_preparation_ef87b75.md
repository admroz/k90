# Final independent preparation review — ef87b75

## Verdict and exact scope

- Reviewed source: `ef87b75e102f661bc35eaec383ddd2a284f5be8d`, branch `feat/long-term-memory`, repository `/opt/data/projects/k90`.
- **PASS — changed executable/configuration source, bounded offline checks, and independently read-back actual CI/container evidence.** No blocking application/security regression found in the new delta.
- **FAIL / not yet final-delivery PASS — documentation/evidence closure at this exact SHA.** The runbook's source-tree verification misses staged changes, and the current acceptance/status manifests still describe the superseded f39ad1f BLOCKED scope. These are bounded documentation corrections, not a requirement for more HS infrastructure, live OAuth, or another application implementation cycle.
- Final preparation can pass after the exact documentation corrections below and their read-back. Those corrections have **not** been made or reverified by this reviewer. Only docs may follow the reviewed source.
- This is personal-use preparation acceptance, not production integration, deployment, merge approval, bank ACL proof, or complete anonymization. `full_live_acceptance: false` remains mandatory.

## Independently verified CI/container evidence

Read both scratch helpers before use. Used the GitHub REST API through the inspected helper; Git credential-helper output remained in memory and was never printed. No dispatch, settings write, push or deployment by this reviewer.

- Run **40214045103**, event `push`, `head_sha=ef87b75e102f661bc35eaec383ddd2a284f5be8d`, status `completed`, conclusion `success`.
- Test job **121231213864**, `test (amd64, ubuntu-24.04)`, completed/success.
- Actual step `Build and exercise container without external network` completed/success, 2026-10-25 16:56:51Z–16:57:23Z.
- Actual runner log: **407 passed, 1 skipped in 12.49s**; frontend **21 passed, 0 failed**, JS syntax step successful.
- Actual runner log: **Build-context secret exclusions PASS at root and two nested depths**.
- Actual runner log: **HTTP, static assets and chat work while Telegram has no network**, before and after isolated Telegram restart.
- Actual runner log: **Container smoke test passed, including isolated Telegram restart**.
- Publish job named `build`, ID **121231505502**, completed/**skipped**, with no steps. Distinguish this skipped publication job from the real local image build that did execute in the test job.
- Run address: `https://github.com/hermesinski/k90/actions/runs/40214045103`.
- Retrieved synthetic CI logs: `/opt/data/cache/scratch/k90-verification-20261025/ci-40214045103/`.

## Review findings and exact bounded corrections

### D1 — source-image guard misses staged tracked edits (required runbook correction)

`docs/DEPLOYMENT_RUNBOOK.md:235–244` says the build requires a clean tracked source tree, but `git diff --exit-code` compares working tree against index, not against HEAD. A staged source change can therefore enter an image tagged as the reviewed source even when this command succeeds. This is an operator integrity/usability defect in the command, not an application defect.

Replace the one-line build command at line 239 with:

```sh
test "$(git -C "$K90_SOURCE_DIR" rev-parse HEAD)" = "$K90_SOURCE" && git -C "$K90_SOURCE_DIR" diff --quiet HEAD -- && docker build -t k90-local:memory-reviewed "$K90_SOURCE_DIR"
```

`--quiet HEAD --` rejects both staged and unstaged tracked changes without printing their contents. Keep the existing separate-source-checkout instructions and warning not to put private files into the build context. This does not establish absence of arbitrary untracked material; do not claim that it does.

### D2 — refresh current preparation evidence, preserve historical evidence (required closure)

At reviewed SHA, `docs/review-evidence/acceptance.json` still names f39ad1f, BLOCKED/BLOCKED_OWNER, no container proof, and four historical gates; `independent-review.json` intentionally records the historical f39ad1f security PASS. `docs/STATUS.md` still says CONTINUE and lists runbook/new CI as pending. These are honest historical/WIP documents, not a final revised-scope manifest.

Bounded closure:

1. Preserve the historical independent report/probes, historical HS partial evidence and original provenance. Do not relabel the old reviewer or old tests as an ef87b75 execution. If replacing a current manifest, retain an explicitly historical copy/reference.
2. Point current preparation acceptance and current independent preparation evidence to **ef87b75e102f661bc35eaec383ddd2a284f5be8d** and this report; keep the historical independent security PASS separately identified at f39ad1f.
3. Retain all eight scope areas (table below), add actual run/job/log facts above and the coordinator's separately completed exact-source full regression. Do not claim the coordinator regression was run by this reviewer.
4. Use `deferred_live_checks` for real k90-only OAuth/provider/catalog/refresh/stream/tools/images/account billing and owner-topology HS DNS/auth/trusted-network/retain-recall checks. Record unproven actual HS restart persistence/bank ACL honestly, without making extensive HS infrastructure a preparation blocker. Set `full_live_acceptance: false`.
5. Close preparation `remaining_gates` only after D1 and this evidence refresh are applied/read back and the coordinator's exact-source regression is successful. Then a preparation PASS/ready-for-owner-review is consistent with OWNER_ACCEPTANCE; it is not deployment permission.
6. Update STATUS and the top of VERIFICATION with the revised outcome, exact source, actual CI evidence, documentation-only follow-up boundary and deferred live checks. Keep historical sections explicitly historical rather than rewriting their results.

**No further executable-source change or live integration is required by these findings.** The final documentation can pass after D1+D2 and a bounded documentation consistency/read-back check. This report does not fabricate that future re-verification.

## Mandatory runbook / privacy / topology review

Read OWNER_ACCEPTANCE first, then the full 519-line deployment runbook. Read the full f39ad1f..ef87b75 delta and historical review/evidence; did not redo the old JSON privacy audit.

- Two separate stacks, original Hermes Compose unavailable: minimal insertion patches and explicit path/service placeholders are legitimate. Existing HS volumes/auth/models/networks are retained; default-vs-custom network merging is explained.
- Shared-network alias and internal API port are explicit. `docker network connect --alias` attaches the existing container without an HS restart; the Compose patch only persists a future topology. The runbook explicitly forbids HS Compose up/restart/down and defers recreate to a separate owner operation. No hidden migration/restart requirement found.
- Ownership is explicit: HOST operator with Docker rights, Mac normal user, container root matching the actual Dockerfile. Data mount and compose project identity are preserved. No silent UID change.
- Auth transfer matches CLI and TokenStore interfaces: login on browser Mac, own private k90 store, SSH transfer of credentials only, root-owned writable isolated import staging, verified import, destination host identity retained, status and cleanup, no source logout that would revoke the transferred session. No borrowed Hermes credentials or invented device flow.
- Backup includes SQLite API plus stopped-k90 full data archive, hidden OAuth state, configuration, documents, WAL/SHM and HMAC; no live single-file-copy claim. HS backup remains its owner's existing procedure. Private archive/readability/retention precautions are explicit.
- Rollback includes local-backend fallback, explicit document export, fresh backup, stopping only k90, preserved newer data and an owner decision before restoring an older snapshot/new data directory. It warns against old rotated OAuth state, data loss, table deletion and global destructive Docker commands. The restore is intentionally an owner-reviewed choice, not an automatic destructive command.
- Privacy limits, bank-vs-ACL distinction, global token limits, HS model egress, private network trust, safe-cookie HTTPS requirement, local-only filtering and image/EXIF limits are explicit. Health/status are not represented as inference evidence. No owner data or HS endpoint was contacted by this reviewer.
- Short deployment smoke uses only a newly named `k90-test-*` bank and a fictional document; production bank provisioning stays owner-controlled. It documents exact-bank cleanup/read-back, no service restart, possible HS quota consumption and fallback to local. Commands match current backend exports/signatures; not executed against HS here.
- Compose env_file passes configuration without a YAML allowlist. Only password validation, /data paths and TZ alias are overridden; image, volume, bind and runtime choice remain operator-controlled. Empty-value caveat is documented.
- Recursive Docker ignore rules and the synthetic smoke are sound: only the actual ignore file is copied, 12 fake private paths cover root/two depths with public positive control; unique disposable image cleanup cannot target the base image. Feature workflow publication guard still requires main. The runtime smoke is network-none/preview/synthetic, not provider integration.

## Eight-area preparation coverage

| Area | Evidence / honest boundary |
| --- | --- |
| documents_sqlite | Historical independent/source evidence preserved; current runner regression passed; own document tests passed. No production migration. |
| local_memory | Historical ledger/FTS/outbox/hydration/privacy evidence preserved; no application changes in this delta; current runner regression passed. |
| outbound_privacy | Historical f39ad1f security PASS remains historical; policy/application unchanged; recursive image-context protections reviewed and real runner-tested. Not full anonymization. |
| hindsight_integration | Existing adapter/error/fallback/privacy and partial historical real HS evidence preserved; short runbook smoke reviewed. Current owner topology/auth/ACL/restart unproven and deferred, not fabricated. |
| subscription_adapter | CLI topology/ownership/import/logout reviewed; own offline auth/login/protocol/API tests passed; real login/provider/account behavior owner-deferred. |
| regression | Actual ef87b75 runner 407 passed/1 skipped, frontend 21 passed; coordinator independently running its full offline regression. Own focused runs separately recorded below. |
| container | Actual ef87b75 amd64 image build, recursive-ignore smoke and network-none application/Telegram-restart smoke passed on hosted runner. No local Docker privilege request or production startup. |
| ci | Exact-source completed run/job/steps/logs read back independently; publication skipped. No main write, publication or deployment. |

## Executed commands and results

Working directory `/opt/data/projects/k90` unless noted. Read guard before tests: `/opt/data/cache/scratch/k90-verification-20261025/sitecustomize.py`; it blocks non-loopback network and private repository data/env/profile access. This is an audit guard, not an OS sandbox. Bytecode and pytest cache disabled; all fixture state in existing scratch.

Read-only source checks:

```sh
git rev-parse HEAD
git status --short
git diff --stat f39ad1f..ef87b75
git diff --name-only f39ad1f..ef87b75
git diff f39ad1f..ef87b75 -- .dockerignore .gitignore .github/workflows/docker.yml docker-compose.yml scripts/smoke_build_context.py tests/test_compose_contract.py
git diff f39ad1f..ef87b75 -- DEPLOY.md docs/IMPLEMENTATION_PLAN.md docs/MEMORY_ARCHITECTURE.md docs/OPERATIONS_MEMORY_AUTH.md docs/STATUS.md docs/VERIFICATION.md
git diff --check f39ad1f..ef87b75
git diff --quiet HEAD --
git status --porcelain=v1
```

Exact HEAD matched requested SHA; checkout clean, diff-check exit 0. Other added documentation/evidence files read with read_file, including both manifests, full previous independent report and three preserved probes, Compose and integration checkpoints and historical HS JSON.

Focused run 1, exit 0, **19 passed in 0.43s**:

```sh
env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest tests/test_compose_contract.py tests/test_subscription_login.py tests/test_subscription_auth.py -p no:cacheprovider -q -rs --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-final-independent-ef87b75
```

Focused run 2 used exactly the same env prefix with:

```sh
.venv/bin/python -m pytest tests/test_subscription_protocol.py tests/test_subscription_api.py tests/test_patient_documents.py -p no:cacheprovider -q -rs --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-final-independent-ef87b75-protocol
```

Exit 0, **34 passed in 17.07s**. No failures/skips in these focused runs. Did not repeat a full regression already assigned to coordinator.

Additional inspected helpers actually executed:

```sh
python /opt/data/cache/scratch/k90-verification-20261025/compose_probe.py
python /opt/data/cache/scratch/k90-verification-20261025/github_ci.py status
python /opt/data/cache/scratch/k90-verification-20261025/ci_evidence.py 40214045103
/opt/hermes/.venv/bin/hermes usage --json
```

All exited 0. Actual standalone Compose synthetic config semantic_passthrough/password_required/volume_target PASS, `real_env_read=false`, no daemon required. CI results recorded above. Inspected helper generated disposable synthetic Compose fixture/config and CI logs in the existing verification scratch directory; pytest generated disposable synthetic state there. The only authored deliverable is this new report. No checkout/Git modification or background process.

Quota observations: 16:59:23Z Session 17%/Weekly 30%; 17:00:23Z 18%/30%; 17:00:59Z and 17:01:58Z 19%/30%, all from usage_api with known windows. No reset, paid fallback, provider/account switch. Initial quota command location required discovery; no tests started before a successful quota read.

## Tooling issues

An attempted read-only in-memory CI extraction using terminal Python `-c`, and a subsequent execute_code attempt, were blocked before execution by unattended policy. No protection/settings change; used the explicitly requested, inspected existing ci_evidence.py instead. An initial guessed backend filename did not exist; read actual `k90_memory/backend.py`. No test failure or application correction arose. No children spawned.
