# Optional size of one piece — author evidence, 2026-10-29

Base `511d2dd0bd98b6a8a3b58b81d25b793b522ab514`, independent PR2 branch
`feat/catalog-piece-size-20261029`. Tested source:
`408e4c44745b73834b2f162d8aa5583b41dcfb2e`; later commit is documentation only.

Optional JSON `piece_size`, native unit from existing per100 basis. No new macro
basis/product/schema. Shared Decimal converter feeds standalone and logical meal
writes; additive snapshots retain submitted count/unit, used size, native amount,
product version and macros. Revisions distinguish omission from explicit null;
size-only and macro-only corrections preserve other fields. Existing consent,
current confirmed version and operation ledger remain in control.

Synthetic offline author checks (application interpreter, sanitized scratch,
dotenv disabled, network/SQLite and separate batch quota guards):

- Real RED: 11 new tests failed on base; minimal conversion/revision GREEN plus
  existing catalog/logical meal tests: 45 PASS. Initial scratch guard-path setup
  failure retained separately, not counted as RED.
- Missing-converter error RED1: generic tool error failed clarification check;
  narrow error now asks for the one-piece size or native quantity.
- Final focused run: 87 PASS across `test_catalog_piece_size`, `test_food_catalog`,
  `test_logical_meal`, `test_product_review`, `test_food_catalog_web` and
  `test_food_catalog_chat` (84.30s). Covers g/ml, fractional szt, invalid/missing
  conversion, independent edits/clear/basis guard, consent/stale/replay conflict,
  mixed catalog/remainder exactly once and unchanged snapshots after future edits.
- All `tests/web_*.test.mjs`: 29 PASS; `node --check web/app.js` and
  `node --check web/catalog.mjs` PASS.
- Real Chromium + shipped FastAPI/frontend, synthetic DB and forbidden model:
  create/edit/confirm; 0.5 szt × 90 g at 80 kcal/100g = 36 kcal; real stale409
  preserves 2.5 szt; invalid zero preserves editor values; lost successful HTTP
  response then changing unit uses a new request ID; untouched size blocks basis
  change; explicit clear removes szt option; native10g = 8 kcal. Main/error
  screenshots inspected. First expanded browser harness clicked a stale DOM
  button during reload; wait for the new version fixed the harness only. Both
  failed and successful logs retained privately.

Private implementation phase retains exact commands, guard states, logs,
screenshots, source/final SHA and remote readback in result.json/checkpoint.md.
Independent critical review is pending. Full suite and actual exact-SHA fork
CI/image checks are deferred to the parent coordinator. No live LLM, production
data, integration/deployment claim, PR creation, merge or image publication.
