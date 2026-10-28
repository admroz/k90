# Manual meal editing — author verification, 2026-10-28

Base: `a4160f36524b502abcf003c4ca4ec7cb3b6a5183` (owner-merged PR18/PR19).
Branch: `feat/manual-meal-editing-20261027`. Author acceptance evidence below; independent review and image/CI are separate gates.

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

Continuation after the initial safe pause preserved all original failed logs.
The coordinator diagnosed a missing `HERMES_HOME` in the private nested supervisor
environment. Adding it to the supervisor only restored real usage_api admission;
synthetic application HOME/data/auth and offline protection remained isolated.
No quota exemption, synthetic quota, watchdog removal or credential change.

Actual continuation evidence:

- `node --check web/app.js`: exit0.
- `node --test tests/web_*.test.mjs`: **26 passed**, 0 failed.
- Real Chromium with authenticated loopback HTTP and synthetic SQLite: **PASS**.
  Edited description, quantity/unit, all macros, date/time; decimal comma,
  zero/null, move to previous day, source-day empty and destination-day sum,
  persistent values after reload. Original and edited XSS payloads rendered as
  text. A competing real HTTP write caused409; unsaved typed description and
  focus stayed intact, with one save request and an actionable conflict message.
  Native delete dialog included name/date: cancel left the row intact; confirm
  removed it and cleared the day sum. Private failed-save/deleted screenshots
  and exact browser/server command logs retained by coordinator.
- `python -m pytest -q`: **747 passed, 1 skipped in 316.44s**. The skip is
  the existing optional import path.
  Added real confirmed-catalog consumption -> WWW override -> product revision
  -> chat correction -> stale WWW rejection -> SQLite backup/restore coverage,
  asserting original snapshot bytes, conversation rows and audit survive.

Fresh independent review, exact-SHA image smoke/fork CI and PR creation remain
coordinator gates. Host Python/Node/Chromium is not actual image execution.
No production access, live model call, image publication, merge or deployment.

Before deployment, take the supported SQLite backup including documents and
local settings. New audit content is private patient data and belongs in the
backup, never application logs. Restore was tested synthetically through SQLite's
backup API, not production. Additive columns/tables can remain on rollback, but
an old writer does not maintain the new revision/audit guarantees: stop writers
and restore a compatible backup/code pair if reverting. No production migration
or downgrade has been attempted.
