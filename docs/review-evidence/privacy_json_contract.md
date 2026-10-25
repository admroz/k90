# Leading JSON privacy contract — 2026-10-25

Synthetic offline implementation evidence; not a final security approval, real
provider test, deployment claim, or proof of complete anonymization.

## Diagnosis and bounded change

`k90_memory/privacy.py` previously attempted JSON decoding only for leading
objects/arrays, then inferred safety from a malformed prefix not matching a
regex. Thus `{broken,` and `{/*comment*/` fell back to prose, where escaped
`api\\u005fkey` did not match the text secret rule. Leading JSON strings were
never decoded, so nested JSON encodings also bypassed semantic key checks.
Both model adapters use this shared policy before their receiver boundaries.

The new contract:

- A string beginning (after whitespace) with `{`, `[`, or `"` is decoded as a
  complete JSON value. Successful decoding recursively uses the same depth,
  node and aggregate character budgets; serialization retains encoding layers.
- A malformed object-like or quoted encoding is denied, independent of its key
  prefix. No unescaping regex or malformed-secret-key allow/deny list is added.
- The sole malformed-array fallback is a complete plain bracketed Markdown label:
  a nonempty whitespace/checklist label or an alphabetic-leading label, without
  JSON structural punctuation/quotes/backslashes, and not a JSON literal keyword.
  It still passes the existing text restrictions/redaction. This preserves plain
  links, bracket labels, checklists and the redaction marker.
- Tool `arguments` still require complete JSON, with no Markdown fallback.
- Original input trees remain unchanged. Rejected input is not logged by the
  policy; errors retain the fixed diagnostic.

## Exact execution

Working directory: `/opt/data/projects/k90`.
Read the existing `run-fixes.sh` and `sitecustomize.py` before using them. The
helper uses `env -i`, disabled dotenv, synthetic HOME/DB/DATA_DIR/auth, local
memory backend, and the existing non-loopback/private-file audit guard. The
guard is defense-in-depth, not an OS sandbox. No install or provider call.

```sh
R=/opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh
bash "$R" privacy-contract-probe-red docs/review-evidence/privacy_boundary_probe.py
# exit 1: 6 failed, 7 passed in 1.62s; all six original receiver leaks reproduced
bash "$R" privacy-contract-tests-red tests/test_privacy_json_boundary.py
# exit 1: 14 failed, 6 passed in 0.78s (before production changes)
bash "$R" privacy-contract-green tests/test_privacy_json_boundary.py docs/review-evidence/privacy_boundary_probe.py tests/test_memory_privacy.py tests/test_outbound_policy.py tests/test_responses_api.py tests/test_subscription_api.py tests/test_review_blockers.py tests/test_review_final_cycle.py
# exit 0: 100 passed in 12.49s
```

Scratch logs are `<label>.log` and fixture directories `pytest-<label>` under
`/opt/data/cache/scratch/k90-verification-20261025/`; they may be pruned.
Durable tests: `tests/test_privacy_json_boundary.py` (20 cases). Twelve denial
cases exercise both real adapters with fake external receivers and assert that
no client/token/catalog/inference call occurs. Other cases cover plain Markdown,
redaction through multiple encodings, idempotence, shared depth/character limits,
and the mandatory JSON contract for tool arguments.

Quota from `/opt/hermes/.venv/bin/hermes usage --json`: 08:12:16 UTC 74% session /
11% weekly; 08:14:05 UTC 76% / 12%. No reset, fallback or provider change.

## Limits and remaining verification

- Conservative rejection now includes arbitrary brace-leading prose, malformed
  quote-leading prose and richer bracket-label syntax outside the plain-label
  grammar. This may cause false positives; do not bypass policy to fix those.
- This is a leading-JSON contract, not an arbitrary embedded-encoding extractor.
  Generic PII rules still cannot guarantee recognition of every identifier or
  secret in unrestricted prose; configured redact terms remain necessary.
- Focused GREEN includes the original independent probe. Full regression and
  independent adversarial review remain for the coordinating agent. No actual
  HS/OAuth, container, remote write, commit or push was performed in this phase.
