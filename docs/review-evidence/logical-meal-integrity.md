# Logical meal integrity — author verification, 2026-10-27

Tested source: `22bee1754ef08877a99b6dd3b0f1c2285136fe24`.
Runtime implementation: `08bc8a796a469b989e417c561e5e77b62b4898ee`;
the next commit only makes five mocked sync test fixtures explicit.
Base: `eab2614bf313bda92346c3ac7086b0b2d474e830`.
Independent verification and actual image/CI remain separate gates.

Real dispatcher + synthetic SQLite RED reproduced four committed portion rows
followed by rejected `log_meal`. Reverse ordering retained only the free estimate
(50 kcal instead of 306 kcal for the synthetic catalog+fruit breakfast).
The replacement contract writes one meal, complete catalog snapshots and an
owner/request/slot operation result in one transaction. Tests cover duplicated
list entries, stale version/unit/estimate refusal, precommit rollback, replay and
conflict, update/delete history after deletion, new-message independence, failure
of event persistence after commit and crash recovery without write replay.

All three existing adapters were exercised offline through the real agent,
dispatcher, queue and SQLite after read/update/multiple calls: matching call IDs,
all tool outputs, namespace and encrypted reasoning replay in memory, filtering,
completion and injected second-boundary failure. Additional fixtures cover timeout,
incomplete Responses, interrupted subscription SSE and fail-closed tool-output
filtering. SDK retries are disabled only in the synthetic HTTP fixture for a
single deterministic timeout attempt. Provider source/settings were unchanged.
No production provider defect was reproduced; historical diagnosis is UNKNOWN.

Author verification on the tested source:

- Python `python -m pytest -q`: **698 passed, 1 existing skip**, 230.63 s.
- Node `node --test tests/web_*.test.mjs`: **25 passed**; `node --check web/app.js`: PASS.
- Additive legacy migration twice and SQLite API backup/restore: PASS.
- Exact extended container catalog helper executed twice on host: PASS; includes
  catalog+fruit meal, durable ledger/snapshot backup and replay after restore.
- Existing `Dockerfile COPY tools/` packages every changed runtime module; no new
  module or logging PR dependency. Actual image execution was not performed here.

The first full run had 690 passes/1 skip/8 failures: five mocked sync tests inherited
sync disabled, and three timed subprocess tests waited on the wrong batch-guard
variant. Local fixtures and the copied task-only guard were corrected; neither
application performance limits nor privacy checks were relaxed. The full repeat
above passed. Earlier provider fixture assertions were corrected to compare
privacy-filtered replay rather than raw synthetic email text.

No live inference/OAuth/HS/Garmin/Libre, production data repair, merge, deployment,
image publication or PR creation. Tests are author evidence, not independent approval.
Backup/rollback and the complete chat contract are in [PRODUCT_CATALOG.md](../PRODUCT_CATALOG.md#jeden-logiczny-posiłek-w-rozmowie).
Owner live checks must establish deployed SHA/prompt compatibility and investigate
any recurring provider failure with safe diagnostics. Returning to an older writer
loses these guarantees; stop mutations and preserve the current SQLite backup first.
