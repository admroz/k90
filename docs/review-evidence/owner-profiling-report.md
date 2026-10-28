# Owner profiling report — author evidence, 2026-10-28

Small authenticated **Diagnostyka / Czasy** panel; fixed read-only
`GET /api/diagnostics/timings` uses existing session/no-store policy. No HTTP file
selector, database, external service or model call. Existing origin/header checks
continue to protect mutations; GET has no side effects.

The reader projects only validated identifiers, finite bounded numbers, UTC dates,
and fixed stage/scope/channel/outcome enums. Unknown fields are discarded before
aggregation. HTML rendering escapes strings. Neither paths nor exception text,
conversation/meal names, provider payloads or raw log lines are returned.

Identity is request ID + scope + scope instance + span ID. Delivery instances stay
under one request/job, separate from processing/model calls. First-event/text
markers do not create calls. Inclusive parent/child durations are never summed.
Exclusive time subtracts the union of complete direct-child UTC intervals, only
with consistent clock IDs and monotonic elapsed/UTC agreement within 1 ms; otherwise
it is absent. Scope-root exclusive is absent. Queue + scope processing duration
is shown only for complete, same-clock, disjoint intervals. Current runtime starts
the processing scope just before emitting queue finish, so total can legitimately
remain absent even when both individual durations exist. Delivery is not user receipt.

Missing/duplicate boundaries, clock changes/resets, ambiguous legacy identities and
backwards chronology remain incomplete. Tool failure can coexist with successful
processing. A skipped/limited/unreadable scan marks returned requests incomplete
and suppresses exclusive time rather than assuming missing children took zero time.

Bound: current profiling.jsonl plus .1/.2/.3, at most 2 MiB/file and 12,000 retained
validated records; 16 KiB/line, latest 50 grouped requests. Files are regular files
opened without following symlinks. In-process concurrent rotation can leave an
incomplete snapshot; the reader is not an atomic logging archive. No scheduler or
new telemetry framework.

Optional `K90_PROFILE_LEGACY_FILES` is an operator-only OS-path-separated list
(first two files, same byte/line limits). Only `agent.phase ... profile={...}` Python
literal dictionaries with the supported current field names/enums and a 32-hex
request ID are understood. It cannot reconstruct missing old identities or invent
boundaries. Missing scope instance means ambiguous records, no forced merge,
unknown model-call count and incomplete measurements. Other historical layouts are
skipped; this is deliberately a bounded subset, not a general log importer.

## Validation

- RED before implementation: absent `profile_report` import, 1 failing test.
- Focused parser/auth/web/profiling run: 73 PASS. Fixtures cover 100 ms parent,
  overlapping 60/50 ms children (20 ms exclusive), repeated delivery, marker count,
  missing boundaries, clock reset/change, truncation, privacy and rotation.
- Real Chromium on synthetic HTTP: authenticated main view/details, single job,
  one numbered model call, two delivery attempts, UTC/local date, private unknown
  field discarded, explicit no-data and error/recovery states. Screenshots retained
  in the private phase directory. No unchanged-feature browser campaign.
- Final isolated/offline regression on code `f6742b06ac8d9789548c820b6e4125dea5a4c4ce`:
  **761 passed / 1 existing optional-import skip**, 315.69 s. Final boundary parser:
  13 PASS, parser/auth/web 56 PASS. Node broad suite 28 PASS, final renderer 2 PASS,
  JavaScript syntax exit0 and diff whitespace check exit0.
- The first broad run retained 756 PASS / 1 skip / 3 performance-test timeouts:
  copied private nested watchdog polled at30s while these tests allow3/4s. Corrected
  private template polling (nested .05s, direct1s); test limits and app unchanged.
  The corrected full regression above includes all three unchanged performance tests.
- Fresh upstream/main after completion still equals base `2f0711e`; unmerged PR21
  was not integrated. Final commits after the tested code are evidence/status only.

Initial browser harness attempts failed on missing synthetic DB parent and Chromium
Unix-socket path length; corrected only the private fixture DB/TMPDIR. Failed logs
are preserved. No application workaround or private production input was used.

## Operations and gates

No schema changes. Existing SQLite/documents/config backup procedure is unchanged;
profiling logs remain bounded diagnostic files and need not be imported/restored
into a metrics DB. Deploy the image containing the explicit `profile_report.py`
Docker COPY; enable `K90_PROFILING_ENABLED=true` if desired. Verify login, view and
one synthetic request after owner-authorized rollout. Rollback to the prior image;
no data migration or log deletion is necessary.

Author tests are synthetic/offline. Independent immutable-SHA review, actual fork
CI/built-image smoke, PR and owner rollout are later coordinator gates. No local
Docker daemon success, production operation, live provider, merge, image publication
or deployment is claimed.
