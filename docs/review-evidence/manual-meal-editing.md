# Manual meal editing — WIP checkpoint, 2026-10-28

Base: `a4160f36524b502abcf003c4ca4ec7cb3b6a5183` (owner-merged PR18/PR19).
Branch: `feat/manual-meal-editing-20261027`. Author work is paused, not accepted.

The candidate adds whole-meal editing and confirmed deletion to the meals panel,
using the existing PR19 transaction and operation ledger. Nullable quantity/unit,
CAS revision and local `meal_changes` before/after audit are additive. Chat tools
now require the revision returned by `get_recent_meals`. Original catalog
snapshots and historical conversations are not rewritten. Deletion removes the
active row but retains operation results, audit revision and original evidence.
No new Python module or Docker COPY requirement was introduced.

Actual author evidence, isolated synthetic SQLite/HOME/auth, dotenv disabled,
independent network guard (loopback only), project virtualenv Python:

- RED: `python -m pytest -q tests/test_manual_meals.py`: 13 failed before
  implementation; missing mutation routes returned 405. Private immutable batch
  command/output records retained by coordinator.
- First GREEN: same command: 13 passed in 11.02s.
- Expanded focused run: `python -m pytest -q tests/test_manual_meals.py
  tests/test_diet.py tests/test_logical_meal.py
  tests/test_meal_provider_roundtrip.py tests/test_web.py`: **101 passed in 91.81s**.
  Covers real authenticated HTTP/SQLite moves, null/zero, replay, stale revision,
  delete/audit, 401/origin/custom-header protection, invalid values including raw
  NaN/Infinity, and additive migration/SQLite backup restoration. Existing provider
  fixtures were updated to send the newly required chat revision.

Browser acceptance did **not run**: the nested server guard returned unknown quota
`{}` and paused before launching its server. This triggers the task's fail-closed
unknown-limit policy. A private browser script exists but has no passing result
or screenshots. Chromium executable was found; missing Playwright was installed
only as scratch tooling. Do not infer browser success from tooling installation.

Pending: Node syntax/tests, real Chromium full flow and failed-save/cancel/delete,
final broader Python regression, stronger real catalog/history preservation probe,
and review of the complete candidate. The current UI implementation has not been
executed. All remaining tests require renewed trustworthy admission. Independent
review, exact-SHA image smoke/fork CI and PR creation remain coordinator gates.
No production access, live model call, image publication, merge or deployment.

Before deployment, take the supported SQLite backup including documents and
local settings. New audit content is private patient data and belongs in the
backup, never application logs. Restore was tested synthetically through SQLite's
backup API, not production. Additive columns/tables can remain on rollback, but
an old writer does not maintain the new revision/audit guarantees: stop writers
and restore a compatible backup/code pair if reverting. No production migration
or downgrade has been attempted.
