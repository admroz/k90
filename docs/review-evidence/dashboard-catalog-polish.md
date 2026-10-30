# Owner UI follow-up — author verification, 2026-10-29

Source milestone: `b2bb0fccc9744909e7c22933623b96e1a3290acd`, following energy
milestone `21770ef`; base `69c3443`. Branch
`fix/dashboard-catalog-polish-20261029`. This is author evidence, **not an
independent review, deployment or live-data verification**. Scope/backlog:
[OWNER_UI_FOLLOWUP.md](../OWNER_UI_FOLLOWUP.md).

## Delivered behavior

- Today only: resting calories are the mean of available measurements in the
  previous seven calendar days, excluding today; half-up nearest100, just `~`
  before the value. Zero measurements remain real zero; no available value stays
  missing. Past-day views use actual Garmin. Raw measurement/chart data are not
  replaced with fabricated estimated observations.
- Meal readers use newest date/time first, missing times last, stable id-desc
  ties. The daily panel, dashboard data, default raw table and agent readers
  agree; explicit raw-table sorting remains available. Small labelled edit/delete
  icons preserve the existing revision controls and deletion confirmation.
- Existing SVG charts connect actual available points through gaps with their
  elapsed-time spacing. Missing observations are not generated. Each point,
  including ranges above100 points, has an escaped date/value/unit target;
  pointer hover, keyboard focus/Enter and touch reveal values. No chart library.
- Existing Omów behavior is a compact labelled AI action, still preparing the
  existing chat prompt without sending it. Garmin targets are limited to
  owner-confirmed weight and dynamic sleep-record dates; other Garmin categories
  show `G—` with an accessible missing-link explanation, not guessed URLs.
- Catalog becomes compact rows/actions and a responsive edit form. Close and
  Escape work after validation and stale-version errors, preserve typed inputs
  until closed, and return focus to the trigger.

## Exact catalog failure and narrow repair

The existing owner-column migration in `tools/product_review.py` adds a nullable
column and does not claim historical products. `_revise` correctly rejects an
unowned (`owner IS NULL`) product. The panel previously filled its editor from
the catalog list without the explicit owner-binding preview already available
in chat. A synthetic migrated **current confirmed version2**, edited through the
real browser and HTTP API, returned the exact409:

`owner or version mismatch; preview required`

The new authenticated, CSRF-protected `POST /api/catalog/{id}/preview` parallels
chat's explicit show operation: it requires the configured owner, exact current
integer version and either that owner or NULL on the record. Only an explicit
preview can bind an unowned legacy row. Editing, listing and confirmation do
not implicitly claim it. The UI opens the editor from that returned preview.
Stale and foreign-owner records still fail; editing still creates an unconfirmed
new version. No bulk data repair, schema change, weakened `_revise`/confirmation
check or automatic stale-write retry.

The production database was not read. This reproduces and fixes the legacy
failure path; it does **not** prove the owner’s particular production row was
unowned rather than stale. Genuine concurrent edits remain409, with typed input
retained and a working close button.

## TDD / actual execution

Private command/log roots are under `/opt/data/jobs/k90-ui-polish-20261029`;
synthetic data, HOME/auth and pytest basetemp stay under the matching scratch
root. Existing small guards were reused with the correct worktree/PYTHONPATH,
synthetic paths and **80% any-window stop / unknown fail closed**. No production
files, real auth, provider or Garmin calls in app tests.

| Slice | Observed RED | Observed GREEN |
| --- | --- | --- |
| Previous-calendar-week energy |5 failures: today777 instead of2000 / missing estimate flag |5 passed |
| Tilde rendering |1 failure: no `~` |1 passed |
| Consistent meal ordering |1 failure: morning first |6 focused Python passed |
| Legacy explicit preview API |3 failures: missing endpoint404 |3 passed, including foreign/stale/CSRF checks |
| Real legacy browser edit |genuine409 instead of200 |genuine200, preview then versioned revision |
| Compact actions / error close |missing compact row/action labels / missing close control |6 Node passed; browser close passed |
| Sparse chart connection |2 move commands instead of1 |14 renderer/owner Node passed |
| All chart targets |0 targets for101 measurements |101 actual targets; no imputed missing point |
| Verified weight link |browser0 links instead of1 |browser1 exact owner-approved link |
| Keyboard chart focus |real focus changed, tooltip did not |native focus listener, visible correct date/value/unit |
| Catalog Escape / focus return |disabled controls moved focus to BODY |error form focus restored, Escape closes, trigger focused |

Full Python first run: **841 passed, 1 skipped in421.84s**. Exact-source
repeat: **840 passed, 1 failed, 1 skipped in416.17s**. The failure is the unchanged
`test_actual_emissions_missing_span_evidence[provider_bounds]` at
`tests/test_profile_report.py:135`: intact queue timing was conservatively marked
incomplete. Read-only replay against the parser byte-identical to base69c3443
confirms a queue UTC/monotonic discrepancy **1.530152ms**, above its existing1ms
threshold; only `queue_wait` is incomplete, model calls remain2. Focused retry of
that unchanged module: **17 passed in3.72s**. No diagnostic code or timing threshold
was modified; this intermittent full-suite limitation remains for separate review.
The existing skip is `tests/test_imported_data.py:17: No local import selected`.
Final relevant Python suite: **146 passed in137.09s**.
Frontend final: **37 passed**, app/catalog/browser syntax and `git diff --check`
passed. Two older Python assertions were updated from ascending/id-ascending
order to the owner-approved descending order; lightweight DOM fixture gained
`addEventListener` rather than altering production code to satisfy a mock.

Real Chromium145.0.7632.6, dev-only Playwright Core1.64.1:
`tests/browser/ui_polish.cjs` + `ui_polish_fixture:app`, genuine FastAPI/SQLite.
Final browser PASS includes meal edit and delete cancel/confirm with readback,
legacy preview/edit/confirm/0.5piece=32kcal, real validation409 and concurrent
stale409, retained fields, close/Escape/focus return, previous-week energy and
actual past-day reading, sparse elapsed-time1/27 spacing, hover/focus/keyboard and
390px touch emulation, AI keyboard intent, dynamic sleep date2026-10-28 rather
than frozen today29, missing-link indicators, no horizontal overflow and no
uncaught JavaScript errors. Screenshots were visually inspected. Reproduction
and environment notes: [browser README](../../tests/browser/README.md).

## Garmin provenance and limits

Owner-confirmed on2026-10-29:
- `https://connect.garmin.com/app/weight`
- `https://connect.garmin.com/app/sleep/2026-10-29` (date is dynamic in the UI).

Public verification preserved these paths in Garmin SSO's `service` redirect,
then met a Cloudflare/sign-in gate; direct fetch returned403. No Garmin login or
authenticated destination verification was attempted. Searches of official
Garmin support (HRV Status and Body Battery FAQ) did not establish additional
direct category routes; the existing repository contained none. Consequently
HRV, Body Battery, RHR, stress, respiration and activity/energy links remain
**unverified/unavailable in this patch**, not asserted nonexistent. Manual blood
pressure and Libre glucose do not advertise Garmin destinations.

## Remaining gates / excluded work

Parent independent review and eventual single PR are pending. No PR, merge,
CI dispatch, image publication, deployment, live provider integration, physical
mobile-device or WebKit claim. The workflow was inspected: this `fix/` branch is
outside push triggers, and publication requires main; workflow left unchanged.
Diagnostics (per-request token input/output/cache when reported, missing not0,
optional discrete expandable chat details and timing waterfall) and data cleanup
remain separate deferred backlog, with no runtime implementation here.
