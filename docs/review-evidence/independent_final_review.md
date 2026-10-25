# Independent adversarial review — final k90 source

## Verdict

**Scoped PASS: no blocking receiver-level privacy bypass or subscription-safety defect reproduced in the examined final source.** This is an independent, bounded offline source/security review, NOT integration, deployment, complete anonymization, or merge approval.

Source requested: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`.
Observed HEAD before/after: `8133b1bbd1488ef8747095fb39a5bfd9f098e1b7`; diff from requested source contains only six documentation/evidence files. `git status --porcelain=v1` empty and `git diff --check` exit 0 at completion. No checkout or Git writes performed. All created probes, synthetic state and reports are beneath this report directory.

## Executed evidence

Working directory for every command: `/opt/data/projects/k90`.

```sh
R=/opt/data/cache/scratch/k90-review-final-20261025/run-review.sh
bash "$R" focused-confirm tests/test_privacy_composition.py tests/test_privacy_json_boundary.py tests/test_model_wiring.py tests/test_subscription_auth.py tests/test_subscription_login.py tests/test_subscription_protocol.py tests/test_subscription_api.py tests/test_memory_worker.py tests/test_memory_backend.py tests/test_review_blockers.py tests/test_review_final_cycle.py
# exit 0: 202 passed in 15.79s

bash "$R" new-matrix /opt/data/cache/scratch/k90-review-final-20261025/test_adversarial_final.py
# exit 0: 112 passed in 2.97s

bash "$R" actual-flows /opt/data/cache/scratch/k90-review-final-20261025/test_actual_flows.py
# exit 0: 18 passed in 11.55s

bash "$R" wire /opt/data/cache/scratch/k90-review-final-20261025/test_wire_receivers.py -s
# exit 0: 10 passed, 1 warning in 8.45s

bash "$R" new-combined /opt/data/cache/scratch/k90-review-final-20261025/test_adversarial_final.py /opt/data/cache/scratch/k90-review-final-20261025/test_actual_flows.py /opt/data/cache/scratch/k90-review-final-20261025/test_wire_receivers.py
# exit 0: 140 passed, 1 warning in 17.15s
```

Logs with those exact labels are in this directory. `run-review.sh` contains the exact complete sanitized environment/command. It uses `env -i`, local DB/data/HOME/auth/TMPDIR, disabled dotenv, local memory backend, no bytecode/pytest cache writes, and the inspected prior offline network/private-file guard. Additional scratch `sitecustomize.py` prohibits checkout mutation. No installs, credentials, actual model/OAuth/HS endpoints, existing banks or Hermes settings were used.

## What was independently challenged

- All three model paths: Chat Completions shared boundary, API-key Responses, subscription Responses; both HS HTTP implementations, retain and recall boundaries.
- New receiver matrix: canonicalized restricted names, non-boolean local-only values, multi-layer encoded restricted objects, escaped scalar key names, nested attachment fields, overflow-to-infinity JSON, duplicate escaped-equivalent names, trailing JSON, array restrictions, explicit local-only markers, and identifier redaction. Rejected content caused zero captured transport calls; subscription rejection also occurred before token access. Normal Markdown and measurements reached receivers.
- Actual application paths, not just standalone sanitizer calls: incoming capture; restored assistant history; stored profile summary; real SQL meal context; patient-document tool results; full summary refresh. All three model modes blocked the new nested encoded local-only fixture. Originals remained unchanged locally, and rejected incoming content was captured with a restricted memory source.
- Actual localhost HTTP receivers: real LiteLLM/OpenAI SDK serialization, subscription `request_json`, HS stdlib transport and application `memory_runtime._transport`. Allowed email was redacted on the received wire while BP 120/80 survived; restricted input produced no HTTP requests. Subscription HTTPSConnection was deliberately redirected to local HTTP while preserving/asserting the expected provider hostname: this tests serialization, NOT TLS or provider authentication. Synthetic tokens only.
- Malicious HS reference response: stale, deleted, unknown and other-owner content did not hydrate into the selected owner's results.
- Subscription provider-limit test: a synthetic HTTP-429 diagnostic propagated without invoking either paid API path. Existing auth/protocol regressions also exercised signature checking, refresh pending-state recovery/rejection, newest-token revocation, protected file permissions, explicit import and callback checks.

## Source review scope and residual limits

Read AGENTS.md, STATUS.md, IMPLEMENTATION_PLAN.md, VERIFICATION.md and OPERATIONS_MEMORY_AUTH.md in full. Examined privacy/outbound_policy, agent, Responses/subscription adapters, OAuth store/protocol/login, memory runtime/admin/store/worker/backend, summary, patient documents and operational context. Main source boundaries are precomposition checks in agent/summary/context/runtime, final payload filtering in each model adapter, and independent Worker/HS filtering plus owner/revision hydration.

No new blocking finding supported by these probes. No minimal FAIL reproducer is supplied because none was reproduced.

Unclosed external gates remain unapproved: real final OAuth/login/refresh/catalog/billing behavior; HS service ACL/bank authorization and restart persistence; real container build/smoke and CI. Existing documentation of another operator's real HS test was read but was not independently reexecuted or promoted into approval.

The policy explicitly does not locate arbitrary JSON embedded in prose or fully anonymize unconfigured names/addresses. Image consent permits external disclosure, not image/EXIF anonymization. Current source restrictions cannot retract earlier external disclosures; stale in-flight HS writes/deletes are eventual, not immediate. Same-UID/root credential access and slow-stream total deadlines remain documented trust/availability limits, not newly demonstrated bypasses.

Full repository pytest was deliberately not rerun: some fixtures write into checkout, incompatible with this task's explicit read-only rule. The 202-case targeted regression and 140 new cases above were actually executed; earlier 404/1-skip results are not represented as this review's execution.

## Issues encountered

First focused run: 201 passed / 1 failed solely because the extra review write guard misresolved a dir_fd-relative scratch cleanup as a checkout path (`registration.json`). Corrected only the scratch guard to resolve that descriptor; exact same selection then passed 202/202. Initial evidence remains `focused.log`. No source fix or hidden test skip.

Wire test warning: LiteLLM DeprecationWarning about absent current event loop; tests and wire assertions passed.

Quota: initial usage_api 2026-10-25T12:22:28Z Session 51%, Weekly 21%; mid-stage 54/21 and 56/22; final 2026-10-25T12:30:42Z 57/22. Resets 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. No reset, paid fallback or account change.

## Created files

`REPORT.md`, `run-review.sh`, `sitecustomize.py`, `test_adversarial_final.py`, `test_actual_flows.py`, `test_wire_receivers.py`, logs (`focused.log`, `focused-confirm.log`, `new-matrix.log`, `actual-flows.log`, `wire.log`, `new-combined.log`), plus generated synthetic pytest/DB/home/auth state under this directory. No checkout files modified.

---

## Durable preservation and rerun — 2026-10-25

Everything above this separator is the original independent review report, preserved
verbatim. Its references to "this directory", logs, the original filenames and clean
checkout describe the reviewer's original scratch execution, not this durable copy.
Those scratch logs/guards are not claimed to be durable or silently moved here.
The original guard-only failure and LiteLLM warning remain disclosed above.

This appendix and `independent-review.json` were added by the delegated
implementation/evidence-preservation writer, **not a second independent reviewer**.
No application or existing test was changed. STATUS, VERIFICATION and PLAN are owned
by the coordinator and were not edited. No acceptance PASS, commit or push was made.
The supervisor lock was held; this bounded sole-writer task was explicitly delegated
by the coordinator, which reserved the checkout until completion.

### Artifact review and provenance

Each of the three complete probe files and the original report was read before
copying for secrets/PII. Only explicit synthetic markers, numeric test identifiers,
reserved `.invalid` addresses, synthetic tokens and local operational paths were
found; no actual credentials or patient records were included. The probes are
byte-for-byte copies, confirmed with `cmp` (all exit 0):

| Original scratch artifact | Durable filename | SHA256 |
| --- | --- | --- |
| `test_adversarial_final.py` | `independent_final_adversarial.py` | `e25c29d50cf47f7aa2ed29ef0721f957b9e7c9c3242ab94d4536d5b014fa2219` |
| `test_actual_flows.py` | `independent_final_flows.py` | `fca10825ea03ea70232ba63855f6804fcfe67344d5acac974c9bd045934623e1` |
| `test_wire_receivers.py` | `independent_final_wire.py` | `81723fe541b9d10ac0b947b6cd97ccb7b01ce4798c6a965453ec189b6865a56b` |

Source reviewed: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`; preservation
started at HEAD `8133b1bbd1488ef8747095fb39a5bfd9f098e1b7`. The six committed
changes between them are documentation/evidence only, confirmed with
`git diff --name-only f39ad1fd54674f78be6a4ca35a1064fdc39a37a2 HEAD`.

### Reproduce using the coordinator's existing helper

Inspect `run-fixes.sh` and its `sitecustomize.py` before use. Both were inspected
for this rerun: the helper clears inherited environment with `env -i`, uses only
synthetic HOME/SQLite/data/auth paths, disables dotenv/Telegram and selects local
memory. Its Python audit guard blocks non-loopback network, repository data,
.env and profile/memory reads. This is defense-in-depth, not an OS sandbox.
Localhost HTTP is intentional; no real provider or HS endpoint was contacted.
This rerun uses the coordinator guard, not the reviewer's extra checkout-write guard.

Actual command, working directory `/opt/data/projects/k90`:

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh independent-durable-final docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py -p no:cacheprovider
```

Actual result: **exit 0; 140 passed, 1 warning in 16.89s**. No skip or failure.
All test selections point to durable repository paths, not scratch probe files.
The 202 existing regressions above remain attributed to the original independent
review, not claimed as rerun by the preservation writer.

### Fixed safe environment expansion

The following expanded helper invocation was also actually executed. `S` is set
in a separate shell statement **before** any `$S` expansion; do not place that
assignment inside `env -i` and expect the shell to expand later arguments from it.
The expansion additionally suppresses bytecode; pytest cache is disabled in both
commands. No inherited credentials/environment or scratch test files are needed.
The already-inspected scratch helper/guard remain prerequisites; if pruned,
reconstruct the offline harness from `docs/VERIFICATION.md` and inspect it first,
never silently run without the guard or against a real database.

```sh
cd /opt/data/projects/k90
S=/opt/data/cache/scratch/k90-verification-20261025
set -o pipefail
env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME="$S/home" TMPDIR="$S" PYTHONPATH="$S:." PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 DB_PATH="$S/data/test.db" DATA_DIR="$S/data" K90_CHATGPT_STATE_DIR="$S/auth" K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py -p no:cacheprovider -q -rs --tb=short --basetemp="$S/pytest-independent-durable-expanded" 2>&1 | tee "$S/independent-durable-expanded.log"
```

Actual pytest result: **140 passed, 1 warning in 16.88s**. Same warning in both:

```text
docs/review-evidence/independent_final_wire.py::test_wire_receiver[False-chat]
  /opt/data/projects/k90/.venv/lib/python3.13/site-packages/litellm/_service_logger.py:59: DeprecationWarning: There is no current event loop
    loop = asyncio.get_event_loop()
```

Existing durable evidence is context, not additional approval:
`privacy_composition_fix.md`, `privacy_json_contract.md`,
`privacy_boundary_probe.py`, `privacy_boundary_probe.log`,
`privacy_parent_regression.txt`, `integration_checkpoint_20261025.md` and
`hindsight_live_probe.json` in this directory. Integration checkpoint and HS summary
retain their own partial scope; no OAuth, HS ACL/restart, container/CI or deployment
gate is closed by this offline review or preservation rerun.

Preservation tooling issues: one combined read-only shell probe containing Python
`-c` and one programmatic copy via `execute_code` were blocked by unattended-mode
policy before execution. Normal read/write tools and `cmp` were used instead;
no settings were changed. No source correction was necessary.
Quota at start 2026-10-25T12:33:24Z: Session 59%, Weekly 22%; after test batch
2026-10-25T12:37:37Z: 60%/22%. No reset, paid fallback or account change.
