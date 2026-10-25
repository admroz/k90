# Compose checkpoint — WIP, not final acceptance

2026-10-25 14:22 UTC. Revised scope is OWNER_ACCEPTANCE.md.

Changed Compose to service env_file `.env`; explicit overrides only password,
DATA_DIR, DB_PATH and timezone alias (explicit TZ wins). Image, bind, ports and
restart policy unchanged. Added environment-variant/OAuth-path ignore rules and
static regression contracts. No real configuration, credentials or production
files opened. Application sources and privacy policy unchanged.

Executed by coordinator, repo cwd:

    bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh compose-red tests/test_compose_contract.py
    # exit 1: 2 failed before changes
    bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh compose-green tests/test_compose_contract.py
    # exit 0: 2 passed
    bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh revised-compose-full
    # exit 0: 406 passed, 1 skipped in 84.51s
    node --check web/app.js
    node --test tests/web_*.test.mjs
    # exit 0: syntax OK, 21 passed
    python /opt/data/cache/scratch/k90-verification-20261025/compose_probe.py
    # exit 0: semantic_passthrough, password_required, volume_target PASS

Full Python regression uses the previously documented env -i/offline guard;
only skip is unselected local data import. No real models/HS or OAuth calls.

Docker Compose plugin unavailable locally. Downloaded official standalone
Compose v5.6.1 from docker/compose GitHub release API/assets to scratch only;
SHA256 matched upstream asset checksum:
47737f4236e6d3ccea7291995203f8f018058783b4c3a9469119811a0b5db8c0.
Probe copied YAML to new scratch directory, wrote only synthetic `.env`, used
env -i-equivalent subprocess env, captured config JSON privately and asserted
ChatGPT/summary/memory/new unknown option passthrough, explicit TZ precedence,
data paths, volume target and missing-password rejection. Never rendered a real
environment. This verifies Compose semantics, NOT container startup.

Implementation child was read-only after misinterpreting supervisor-held lock;
no files changed. Independent read-only reviewer inspected complete tracked diff
and new test but could not retrieve its own quota and stopped before testing:
review INCOMPLETE (reported FAIL to complete verification, no reproduced code
finding). Coordinator quota was available, 75% then 76% then 78%; do not count
this child as independent PASS. Both children terminated; no writer remains.
Next session must independently review these new configuration changes.

CI diagnosis (authenticated credential helper, credentials never printed):
GET actions/permissions: 200 enabled=true allowed_actions=all.
GET actions/workflows: 200 total_count=0; main contains docker.yml.
GET workflow docker.yml: 404; PUT workflow enable: 404; exact readback workflows
still 200 total_count=0. Failed enable changed no confirmed external state.
Generic Actions cause remains undiagnosed; do not ask owner to diagnose it yet.
Next: inspect fork Actions activation/registration and obtain hosted test runs;
add isolated pinned HS service and deterministic local model/embedding fixtures.
UPDATE: later external owner-document clarification supersedes that HS next
step: extensive HS infrastructure testing is deferred to deployment; preserve
short synthetic deployment smoke and adapter/privacy tests instead. Coordinator
stopped implementation on discovering this external write to the checkout.
No CI/container/HS restart PASS and no live OAuth proof claimed.

Historical acceptance manifests remain BLOCKED and reference older source;
this checkpoint does not replace them with fabricated PASS. Live OAuth/provider
checks are owner-deferred under revised acceptance, not current blockers.
