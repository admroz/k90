# Personal self-hosted preparation — coordinator closure, 2026-10-25

Tested source: `ef87b75e102f661bc35eaec383ddd2a284f5be8d`.
Only docs/ follow this source. Preparation PASS is not production/live acceptance.

## Exact-source coordinator execution

The coordinator reread the existing run-fixes.sh and sitecustomize.py before use.
They run env -i, dotenv disabled, synthetic DB/DATA_DIR/HOME/auth, local memory,
Telegram disabled and an audit guard denying non-loopback network/private files.
Loopback HTTP receivers are allowed. This is not an OS sandbox.

From repo cwd:

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh final-ef87b75-full
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh final-ef87b75-probes docs/review-evidence/privacy_boundary_probe.py docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py -p no:cacheprovider
node --check web/app.js
node --test tests/web_*.test.mjs
```

Exit 0 for each. Python 407 passed / 1 skipped in 83.03s; sole skip is
unselected local imported data, tests/test_imported_data.py:17. Probes 153 passed
in 17.44s, one LiteLLM event-loop DeprecationWarning; JS syntax OK, frontend
21 passed / 0 failed. No real HS/provider or production access in these tests.

## Actual GitHub-hosted container/CI

Both coordinator and final independent reviewer fetched exact run/jobs/step status
and actual synthetic logs through inspected ci_evidence.py. Credentials remained
in helper memory, never in reports, repository or public workflow.

```sh
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/ci_evidence.py 40214045103
```

Exit 0. Run https://github.com/hermesinski/k90/actions/runs/40214045103,
event push, head_sha ef87b75e102f661bc35eaec383ddd2a284f5be8d, completed/success.
Test job 121231213864, amd64/ubuntu-24.04, completed/success:

- pytest -q: 407 passed / 1 skipped in 12.49s.
- node --check web/app.js and node --test tests/web_*.test.mjs: success, 21 passed.
- docker build -t k90:test .: actual successful image build.
- python scripts/smoke_build_context.py k90:test: actual Docker COPY/runtime
  exclusion check, root/two nested depths, 12 synthetic private paths plus public
  positive control PASS. No owner files in disposable context.
- python scripts/smoke_container.py k90:test: --network none, synthetic preview,
  HTTP/login/static/dashboard/chat PASS before and after Telegram adapter KILL
  and supervised restart; backend PID retained; disposable container cleaned up.
- Publication job `build` 121231505502 skipped, no steps. No registry publication
  or deployment. The image build in test job is distinct from skipped publication.

Runtime smoke does not test real models, HS or OAuth. Build downloads public
requirements/base image; runtime is deliberately without external network.
Original logs remain private scratch ci-40214045103; safe exact result excerpts
above are the durable evidence. GitHub run remains the external verification handle.

## Independent review and bounded documentation closure

The final read-only reviewer inspected the full delta f39ad1f..ef87b75, prior
security evidence and full runbook, ran 19+34 focused synthetic tests and the
actual Compose probe, and independently fetched successful CI. Source/configuration
and CI/container verdict PASS. Original report is preserved byte-for-byte:
`independent_preparation_ef87b75.md`; SHA256
`909e5dbc6408769562157335db748cc7009be53bca32b6c527e6ebbd27bc1dea`.

Its exact-source final documentation verdict was NOT PASS: D1 build guard missed
staged edits; D2 current status/manifests were still historical BLOCKED. Do not
hide that distinction or claim reviewer saw future edits. Reviewer explicitly
allowed preparation closure after those bounded docs corrections/read-back,
without more executable changes or a new live-integration project.

Coordinator D1 closure: applied the reviewer's exact `git diff --quiet HEAD --`
command, and tested clean/unstaged/staged cases in a new synthetic Git repository.
The clean tree passes, unstaged and staged edits each exit 1, without Docker/build
or private data. Filled the exact tested source SHA in the runbook.

Coordinator D2 closure: preserved historical manifests as
historical-independent-review-f39ad1f.json and historical-acceptance-f39ad1f.json,
retained original security report/probes and historical partial HS evidence.
Current manifests now identify ef87b75, distinguish revised preparation scope
from deferred live checks, and reference actual coordinator/independent/CI results.
STATUS, VERIFICATION and IMPLEMENTATION_PLAN carry current scope; historical
measurements were not rewritten. This is coordinator documentation closure,
not another independent source review or invented reviewer rerun.

Additional non-deploying coordinator commands:

```sh
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/runbook_check.py
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/compose_probe.py
```

Exit 0 each. Runbook: 39 sh commands, each one line, bash syntax parsed; build
clean/unstaged/staged guard PASS; both insertion fragments validated with real
standalone Compose 5.6.1 against synthetic services/env, preserving existing auth
fixture/storage/default networks and shared alias/external network. Base Compose
semantic passthrough/password-required/volume-target PASS. No actual owner Compose,
real env, daemon, network connect, login, HS smoke, migration or rollout executed.

## Owner-deferred live checks (not preparation gates)

- Own k90 OAuth login/import, real catalog/inference/refresh/stream/tools/images,
  account credits/billing verification; no live final adapter authorization here.
- Actual two-stack host paths/DNS/HS version/auth/trusted network, production bank
  provisioning, synthetic retain/recall/cleanup and backup/rollback at deployment.
- Actual service restart persistence and bank ACL remain unproven. Extensive HS
  infrastructure testing is explicitly outside revised preparation acceptance.
- Existing partial real HS test at older source is historical, not reexecuted or
  promoted to final topology proof. Security limitations remain unchanged.

Both children finished. No running writers, PR, main/upstream writes, image
publication, production migration/deployment, provider/reset/account switch.
Quota 17:04:12Z Session 21%, Weekly 30%, known resets 21:37:40Z / Nov 1 06:22Z.
90% pause policy active; no banked reset or paid fallback used.

Final coordinator documentation consistency/read-back command:

```sh
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/validate_preparation.py
```

Exit 0, PASS: eight areas, matching source/PASS, empty preparation gates, explicit
live deferrals, existing safe evidence paths, original report hash and historical
manifest byte-for-byte comparisons, docs-only source boundary. Repeated
runbook_check.py exit 0 with the same 39-command/Compose/guard result. Candidate
scan of 10 explicitly reviewed docs files: no findings; both diff checks pass.
Latest quota 17:09:47Z Session 25%, Weekly 31%, resets unchanged. Final clean
checkout/remote equality is checked again after the documentation push.
