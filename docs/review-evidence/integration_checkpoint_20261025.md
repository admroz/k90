# Integration checkpoint — 2026-10-25

This is partial evidence, NOT acceptance/security approval. Only synthetic inputs
and a newly created `k90-test-*` bank were used. No production data or existing bank
was read/changed; no shared configuration was modified. No k90/Hermes OAuth tokens
were read. Authorized Git credential-helper use is described separately below.
Real OAuth was not run.

## Tested source and local regression

Application fix: `289d3ffd918a066fdf9a8dc9d0cda24c8fd8d585`.
Latest tested source: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2` (changes since
application fix: workflow trigger and docs only). Exact coordinator command:

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh source-f39ad1f-full
node --check web/app.js
node --test tests/web_*.test.mjs
git diff --check
```

Actual exit 0: 404 passed / 1 skipped in 84.41s; skip is explicitly unselected
local import (`tests/test_imported_data.py:17`). Frontend syntax OK, 21 passed.
Harness `env -i`, synthetic paths and offline audit guard are documented in
VERIFICATION.md. No external integrations are inferred from this suite.
Earlier original privacy probe: 13 passed in 1.49s, exit 0. Parent also reproduced
a fresh RED of 20 encoded scalar reserved-key cases before the final source fix;
see privacy_composition_fix.md. A final independent security review is still pending.

## Real Hindsight adapter — partial PASS

Health and OpenAPI GET: 200 / healthy / HTTP API 1.1.0. Schema inspected before
using bank creation, document and memory endpoints. Exact successful command:

```sh
env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home PYTHONPATH="$PWD" PYTHON_DOTENV_DISABLED=1 TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 .venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/hs_live.py
```

Run exit 0. Scratch harness SHA256:
`b8fe10a3aa35f5828449f98c1f3e23ccb7f27158dd06c50ab88a56c392279afd`.
Raw synthetic result SHA256:
`fa597c0bd0f1ba6d30a1549b9d05664defe3c2e33bb35d0669f7b39c30df6bb2`.
Safe durable summary: hindsight_live_probe.json (summarized, not the raw hash target).
The scratch harness/result may be pruned; this report and JSON preserve the actual
executed observations, not a promise that scratch files persist indefinitely.

The harness uses the real application HindsightBackend, Worker, SQLite ledger,
Identity, retrieve and rebuild_queue. Only setup/readback/cleanup call HTTP directly.
A URL assertion restricts every direct request to its own generated bank path.

Observed sequence:

1. Confirm new random bank absent by GET documents 404, PUT create 200, GET
   documents 200 with total 0. Observations disabled only on this test bank to
   avoid unnecessary background consolidation, never a shared/global setting.
2. Persist one synthetic source in its own scratch SQLite. Simulate outage BEFORE
   the first network write. Outbox becomes retry / attempts 1 / backend_unavailable.
3. New Worker instance recovers retry from SQLite and uses real HS retain. Job done;
   exact remote document GET 200, one extracted memory. Synthetic e-mail redacted
   remotely; local authoritative original remains unchanged.
4. Real adapter recall returns source ID / revision 1. retrieve hydrates the local
   original. Other synthetic owner tag returns no results. This checks filtering,
   NOT authorization: the endpoint was reachable without a token.
5. rebuild/replay retains identical revision ID; document listing total 1 with
   exactly one enumerated item (no duplicate).
6. Correction writes revision 2; Worker deletes revision 1 (GET 404) and retains
   revision 2 (GET 200). Real recall returns revision 2 and not revision 1.
7. Delete this test bank, verify absent, recreate same empty test namespace,
   rebuild solely from local sources. Revision 2 document readback 200.
8. Final DELETE 200 success=true, exact GET documents 404: cleanup verified.

The first harness attempt failed on deprecated `/profile` (410), before retain,
and its error handler tried an absent outbox table. Its empty test bank was removed
separately and verified absent (DELETE 200 success=true / GET documents 404). The
harness was corrected for document readback and reliable cleanup before the full
successful run. Neither attempt touched an existing bank.

Not proven: service persistence across an actual Hindsight service restart, bank
ACLs or a restricted token. We did not restart the shared service or probe another
agent's bank. Minimal owner prerequisite: an isolated restartable HS test instance
(or an owner-managed restart window) plus a bank-restricted test endpoint/token
with an allowed/denied test identity pair. Do not send credentials through Git/chat.

## Docker and CI — NOT PASSED

Local Docker command (isolated config, no host settings changed):

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/home DOCKER_CONFIG=/opt/data/cache/scratch/k90-verification-20261025/docker docker info --format '{{.ServerVersion}}'
```

Actual output: cannot connect to daemon at unix:///var/run/docker.sock. The client
returned 0 despite that message; this is NOT a successful container verification.
No image build, container start, daemon install or service restart was attempted.

GitHub API operations used the authorized credential-helper fallback; credentials
remained in memory, never printed or saved in reports. Observations:

- GET Actions runs for feature branch: HTTP 200, empty list.
- GET workflows (public and authenticated): HTTP 200, total_count 0.
- GET Actions permissions: HTTP 200, enabled=true, allowed_actions=all.
- GET workflow directory on main: HTTP 200, docker.yml exists.
- POST docker.yml dispatch for feature ref: HTTP 404 (no run created).
- Added only this feature branch to push test trigger; build/publish condition
  still requires refs/heads/main. Push f39ad1f confirmed by ls-remote. Repeated
  API queries after push still returned empty runs/workflows. No CI PASS claimed.

The exact cause of missing GitHub workflow registration is unconfirmed. Minimal
owner action if a fresh-session recheck is still empty: activate/authorize the
fork's workflow through GitHub Actions and allow a test-only run for the feature
commit, or provide an authorized isolated runner. Do not push main or create an
early PR to work around this. A runner with Docker can close both container/CI
requirements using the existing build + scripts/smoke_container.py pipeline.

## Remaining gates and next action

1. Fresh-session read-only independent adversarial review of f39ad1f. Both earlier
   children finished; a third delegation was explicitly rejected by the one-shot
   session's total-child budget (2/2). This is not approval or an owner blocker.
2. Real k90-only subscription OAuth/refresh/catalog/streaming/tools/image evidence
   requires owner login and an independently owned session. Never use Hermes tokens;
   owner must keep extra app credits disabled. The earlier standalone feasibility
   report is not proof of the final integrated adapter.
3. HS restart/ACL and CI/container access as above. No ready manifests, PR, merge,
   deployment or production migration. Continue local review first; then return
   BLOCKED_OWNER if only these actual external prerequisites remain.

Quota 2026-10-25T12:13:39Z: Session 45%, Weekly 20%. Resets
2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. No resets/paid fallback/account switch.
