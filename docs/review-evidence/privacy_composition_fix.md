# Privacy composition fixes — synthetic evidence, 2026-10-25

Implementation based on independent FAIL at source checkpoint `6a3b306`; starting
checkout HEAD `4afa708`, branch `feat/long-term-memory`. **Not a security approval.**
Independent review and coordinator regression remain required. No commit, staging,
push, production data, external model/HS/OAuth call, install or deployment here.
STATUS, VERIFICATION and implementation plan were not edited.

## Coordinator follow-up (12:02 UTC)

The coordinator inspected the exact diff and durable tests and independently ran
the offline suite: 384 passed / 1 skipped in 88.06s, original probe 13 passed in
1.49s, frontend syntax OK and 21 passed. A further adversarial source-name probe
then found that a JSON-string key encoding only a reserved name (rather than a
whole restricted object) could preserve an escaped alias: e.g. the literal mapping
name `"api\u005fkey"`. Added 20 durable five-receiver cases in
`test_encoded_scalar_semantic_key_denied`: RED 20 failed / 86 deselected (0.87s).
The fix rejects encoded scalar reserved names instead of renaming them or losing
field/value semantics; ordinary protocol names and measurement JSON remain intact.

Exact commands (same inspected safe harness and env below):
```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh parent-scalar-key-red tests/test_privacy_composition.py -k encoded_scalar
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh parent-scalar-key-green tests/test_privacy_composition.py tests/test_memory_privacy.py tests/test_privacy_json_boundary.py
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh composition-parent-final
```
GREEN 140 passed in 7.31s; final full suite 404 passed / 1 skipped in 105.83s,
exit 0; same explicit unselected local-import skip. Final durable composition suite
now has 106 cases (86 implementer + 20 coordinator). Earlier scratch exploratory
expectations for a plain non-identifier phone string were overbroad and are not
claimed as defects; the durable RED uses actual escaped reserved names and a
numeric identifier. No independent approval of the final fix is claimed.
Quota 2026-10-25T12:02:09Z: Session 35%, Weekly 19%; reset times unchanged.

## Diagnosis and conservative redesign

1. Mapping names only used text regexes, unlike values. JSON/escaped restrictions
   in a key therefore reached all five external receiver stubs. Names now enter
   the same recursive walk with shared depth, node and aggregate character budgets.
   Encoded names are inspected without renaming/canonicalizing them. If sanitizing
   decoded contents would change them, reject rather than partially rewriting a
   protocol name. Plain key redaction/collision checks and reserved fields remain.
2. `json.loads` discarded earlier duplicate pairs, including `local_only:true`
   before `false`. One `strict_json_loads` uses an object-pairs hook to reject any
   duplicate, including decoded-equivalent escaped names, at every decoded level.
   Non-finite constants also fail closed. Privacy, legacy multipart parsing,
   restored history and model tool-argument execution share this decoder.
   Runtime capture now classifies the original bounded tree through PrivacyPolicy
   before text extraction: any rejected original is conservatively local-only.
   It deliberately does not apply configured redact terms or make image-consent
   decisions there; the normal outbound/Worker policies still do those checks.
3. Summary added headings and instructions before checking raw documents, making
   standalone JSON look like arbitrary prose. Source documents now pass one
   shared-budget policy call before headings; safe copies feed normal and fallback
   summaries. Raw documents/revisions remain unchanged. System prompt/profile and
   operational context components are checked before prefixes; actual operational
   SQL row fields are checked before dates/formatting. Recall checks complete
   record content AND metadata before truncation/serialization/header. Document
   ingestion/snapshots persist the conservative flag and idempotence includes it.

No arbitrary embedded-JSON regex extraction was added. Normal Markdown link,
checklist, paragraph and ordinary JSON measurement tests reach all five receivers.
Raw incoming events, legacy conversations and canonical documents remain local
and unchanged; tests assert this, not just absence of receiver calls.

## Definition/use trace and sibling review

- PrivacyPolicy -> outbound_policy -> Chat; Responses constructor/final payload;
  subscription constructor before instruction joining, token/catalog and inference;
  Worker outbound_document/retrieve and HindsightBackend retain/recall.
- Runtime `_local_only` -> `_event` (begin_turn/record_pair), recall query before
  `_text`, document_changed; memory_admin -> original raw backfill before extraction.
- document_changed -> patient_documents import/write and snapshot_documents ->
  tools.db.init_db; an unchanged old document source can have its flag repaired.
- Summary `_load_patient_parts` -> refresh -> `_generate_summary` -> prompt builder;
  `_fallback_summary` independently checks its source dictionary before collapsing.
- agent load_history -> `_run_agent`; `_build_system_message` -> `_run_agent`;
  tools.context -> system builder; memory_runtime recall -> bounded context append.
- Tool patient/health/lab/diet results retain dictionaries/rows through serialization
  rather than prefixing raw content. Existing recursive outbound guards cover them;
  new document-tool receiver tests check all three model boundaries. Subscription
  add_tool_result already checks originals; Responses retains JSON result structure.
  An additional RED found duplicate model arguments could execute before next-round
  outbound validation; strict decoding now rejects them before execute_tool.

## Exact commands and results

Working directory for every command: `/opt/data/projects/k90`. Read AGENTS, full
VERIFICATION, plan, operations, architecture, STATUS, review report/tests and both
original harness files before editing/testing. Supervisor lock PID 167165 was
confirmed using `lslocks -o PID,COMMAND,PATH` and
`ps -o pid,ppid,args -p 167165,167177`. Sole checkout writer; no children delegated.

`R` below is the inspected original harness, not the reviewer's read-only harness
(which denies checkout writes needed by some existing pytest fixtures). It uses
`env -i`, synthetic HOME/DB/DATA_DIR/auth, disabled dotenv/Telegram, local memory,
and the existing audit guard denying non-loopback network and private files. This
is application defense-in-depth, not an OS sandbox. Logs/basetemp are outside repo.

```sh
R=/opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh
bash "$R" composition-keys-red tests/test_privacy_composition.py
# exit 1: 21 failed, 20 passed in 0.80s; key restrictions and depth bypass
bash "$R" composition-keys-green tests/test_privacy_composition.py tests/test_privacy_json_boundary.py tests/test_memory_privacy.py
# exit 0: 75 passed in 0.72s
bash "$R" composition-duplicates-red tests/test_privacy_composition.py -k 'duplicate or local_ingestion'
# exit 1: 29 failed, 41 deselected in 1.56s; receiver leaks and lost source flags
bash "$R" composition-duplicates-green tests/test_privacy_composition.py tests/test_admin_memory.py tests/test_app_memory.py tests/test_memory_worker.py tests/test_review_final_cycle.py
# exit 0: 105 passed in 9.53s
bash "$R" composition-sources-red tests/test_privacy_composition.py -k 'summary_sources or actual_summary or system_sources or operational_raw or history_duplicate or recall_metadata or document_snapshot'
# exit 1: 11 failed, 70 deselected in 4.97s; ten expected behavioral failures,
# one TEST typo: today_local() is already str, not date; corrected before source fix
bash "$R" composition-operational-red tests/test_privacy_composition.py -k operational_raw
# exit 1: 1 failed, 80 deselected in 0.46s; correct behavioral RED after typo fix
bash "$R" composition-sources-green tests/test_privacy_composition.py tests/test_summary.py tests/test_patient_documents.py tests/test_context.py tests/test_app_memory.py tests/test_model_wiring.py
# exit 0: 124 passed in 24.90s
bash "$R" composition-full
# exit 0: 383 passed, 1 skipped in 88.59s
bash "$R" composition-original-probe docs/review-evidence/privacy_boundary_probe.py
# exit 0: 13 passed in 1.49s
bash "$R" composition-independent-matrix /opt/data/cache/scratch/k90-review-20261025-new/test_receiver_adversarial.py -k test_contract
# exit 0: 80 passed, 3 deselected in 0.88s; implementer rerun, NOT independent review
bash "$R" composition-tool-arguments-red tests/test_privacy_composition.py -k duplicate_tool
# exit 1: 1 failed, 85 deselected in 2.83s; execute_tool received lossy false flag
bash "$R" composition-tool-arguments-green tests/test_privacy_composition.py tests/test_agent.py tests/test_responses_api.py tests/test_subscription_api.py
# exit 0: 115 passed in 12.07s
bash "$R" composition-final-full
# exit 0: 384 passed, 1 skipped in 83.15s; final source/test state
bash "$R" composition-collect tests/test_privacy_composition.py --collect-only
# exit 0: 86 tests collected in 0.03s
set -o pipefail; node --check web/app.js && node --test tests/web_*.test.mjs 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/composition-node.log
# exit 0: syntax OK; 21 passed, 0 failed
git diff --check
git diff --cached --check
# both exit 0, no output
```

The sole full-suite skip is `tests/test_imported_data.py:17: No local import
selected`; no production import was selected. Final suite includes real synthetic
SQLite begin_turn/backfill -> Source -> Worker -> blocked outbox and no retain,
actual summary refresh -> no provider/no saved summary, all five direct receiver
boundaries, sibling composition checks and local-original preservation. Four
additional tool/Markdown coverage cases passed without further source changes;
they are coverage additions, not claimed as new RED fixes.

Harness expansion (replace LABEL and append optional pytest selection before -q):

```sh
set -o pipefail
env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHON_DOTENV_DISABLED=1 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest -q -rs --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-LABEL 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/LABEL.log
```

Guard reconstruction is documented in VERIFICATION; inspect it before reuse.
The scratch independent matrix appends its own JSONL; no aggregate totals from
that append-only file are claimed here. Durable tests do not depend on scratch
reports or write evidence logs into the checkout.

Quota via `/opt/hermes/.venv/bin/hermes usage --json` (usage_api, Session/Weekly):
11:42:26Z 8%/14%; 11:45:17Z 14%/15%; 11:47:47Z 16%/16%; 11:51:01Z 20%/16%;
11:52:09Z 21%/16%; 11:54:24Z 25%/17%. Resets 2026-10-25T16:33:40Z and
2026-11-01T06:22:00Z. No reset, paid fallback, provider/account switch.

## Changed files and residual risks

Source: `k90_memory/privacy.py`, `memory_runtime.py`, `memory_admin.py`, `agent.py`,
`summary.py`, `tools/context.py`. New durable `tests/test_privacy_composition.py`
and this report; updated privacy_json_contract and OPERATIONS_MEMORY_AUTH.

Conservative rejection can reduce recall or block an entire summary/conversation;
malformed leading JSON and unsafe encoded key names are not downgraded to prose.
The flag can now mean any rejected original, not only a literal local-only marker.
Image inspection at capture does not authorize HS images or model image delivery.
Existing plain Markdown grammar and heuristics still have false positives and do
not guarantee anonymization. Arbitrary JSON hidden inside prose, arbitrary user
encodings, previously flattened legacy content without recoverable originals and
already-exported remote content are not automatically repaired. Re-backfill can
repair source flags only where the original legacy row is retained; document
snapshots repair current documents. Production repair/export/purge requires an
operator-controlled procedure. No actual HS authorization/persistence, OAuth,
container, CI or deployment verification; independent adversarial review remains
mandatory. No approval/READY claim is made.

One attempted read-only execute_code batch was blocked by unattended-mode policy;
normal read_file calls were used instead. One multi-hunk test cleanup patch was
rejected as ambiguous with no writes; repeated with unique context. Neither was
worked around by changing host/Hermes settings. The transient operational test
typo is disclosed above. No known failing test remains in the executed final suite.
