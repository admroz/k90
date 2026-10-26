# Timeline, text-filter switch and profiling — implementation verification

2026-10-26, branch `feat/chat-timeline-profiling`, base upstream/main
`020d542344e79ae132619ff6407c2624a831b422`. Source checkpoints:
`6e5f317` (timeline), `44e86a8` (filter), `49689ee` (profiling/runtime smoke),
`6d3e4b13750e637088e2711eb07cce4d3854cc81` (profiling error visibility).
This is author verification, not independent review, deployment or live acceptance.

## Vertical TDD evidence

- Timeline RED: backend returned no entries after a failed request and later
  Telegram submission; frontend had no timeline renderer. GREEN: persistent
  request-linked slots, inline statuses, reload/pagination and owner isolation.
  A separate RED exposed retry identity across owners; fixed without retries.
- Filter RED: `K90_TEXT_FILTER_ENABLED=false` still rejected a synthetic bearer
  string. GREEN: shared model policy changes only automatic basic text regex
  rules; explicit terms, local-only, structure/budgets and image consent remain.
- Profiling RED: missing profiler; then missing queue/processing correlation.
  GREEN: shared `agent.phase` stages, generated per-job identity, UTC chronology,
  monotonic timing, parent spans and summaries. No separate competing logger.
- Additional behavioral RED/GREEN: partially saved answer hiding a failed job;
  legacy ownership inferred incorrectly from current configuration; HS timeout
  lost before safe BackendError wrapping; returned sync error marked finish.
  All fixed with focused behavioral tests. Existing audit rows remain untouched.

The old dismissal tests were replaced because dismissal is explicitly removed.
Their replacement executes the actual app in a VM, denies localStorage access,
loads more than one page, polls old state transitions, verifies chronological
placement and deduplication, reloads, and checks that no POST/retry is generated.
The renderer also tests escaping untrusted user/error text. Existing unrelated
regression expectations remain enforced. The prior phase-log test explicitly
opts into profiling now that its required default is disabled.

## Executed verification

All Python runs use `/opt/data/projects/k90/.venv/bin/python`, `env -i`, synthetic
HOME/DB_PATH/DATA_DIR/K90_CHATGPT_STATE_DIR and `PYTHON_DOTENV_DISABLED=1`.
Final runs additionally set TMPDIR below the task scratch directory and load an
offline audit guard rooted at this checkout via PYTHONPATH. The guard rejects
non-loopback network and private configuration/data reads. Earlier focused runs
used the inspected existing guard and synthetic pytest temporary databases.
No production data, auth store or real provider credentials were loaded.

Focused results (overlapping sets, not additive counts):

- `tests/test_web.py tests/test_web_runtime.py`: 56 passed.
- Switch + outbound + privacy composition/memory/JSON suites: 167 passed.
- Profile/runtime/web/Telegram/photo log subset: 93 passed.
- Latest runtime/switch/profile subset: 35 passed.
- Built-image helper contracts: 5 passed **on host**, including exact embedded
  helper execution. The valid synthetic 1280×1280 PNG is over 95% of the 5 MB
  accepted limit. Actual shipped agent handles photo then textual follow-up;
  persisted conversation/event originals remain equal to input; historical image
  bytes are absent from the second outbound request. Helper executed twice.
- Profile/app-memory/Garmin/Libre follow-up: 32 passed.
- Full source `49689ee`: 581 passed, 1 existing skip, 136.94 seconds.
- Final full source `6d3e4b13750e637088e2711eb07cce4d3854cc81`: **583 passed,
  1 existing optional-import skip**, 136.90 seconds. Later edits are docs only.
- `node --check web/app.js`: PASS. `node --test tests/web_*.test.mjs`: 23 passed.
- `git diff --check`: PASS.

One attempted focused invocation referenced nonexistent `test_memory_runtime.py`:
pytest exited 4 with no tests run; it was corrected to `test_app_memory.py`.
An initial synthetic SDK fixture used dictionaries instead of SDK content objects;
the fixture was corrected without changing production code to accommodate it.

## Boundaries and remaining external gates

No Docker daemon/socket or actual local image build/run was used. `profiling.py`
is explicitly copied by Dockerfile. The real built-image smoke in CI now invokes
the new runtime behavior and the near-limit photo contract. Actual image build,
CI outcome and independent review remain later coordinator gates. No final PR,
merge, deployment, restart or provider/account/model change was performed.

Timeline migration is additive. Exact request identity and owner/role associate
jobs with saved records; identical text and dates never deduplicate sources.
When legacy jobs have no owner evidence at all, they inherit the configured
single owner; past configuration cannot be reconstructed without records.
Conflicting recorded owners are isolated. API clients must refresh numeric
`before` cursors after upgrading to timeline IDs; the response list shape remains.

Profiling records no prompt, health/meal content, attachment, base64, credential,
exception message, private URL or user identifier. Separate submission/processing/
delivery/background scopes share generated job correlation where available.
Nested spans overlap and must not be summed. A queue wait crossing a process
clock boundary has null duration and explicit clock_reset, rather than an estimate.
Web delivery measures API response preparation, not browser receipt. First-event
and first-text timing comes only from actual subscription SSE; other transports
have completion timing only. HS timeout spans are emitted before safe fallback;
returned sync errors preserve their original result and increment stage_errors.

Permanent quota stop is >=80% of ANY window or unknown, including night work;
older 90% documentation is historical and superseded. Usage was refreshed at
phase boundaries. Private checkpoints retain actual usage and push readbacks.
