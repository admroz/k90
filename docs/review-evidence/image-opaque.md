# Owner-approved opaque image boundary — 2026-10-26

Branch `fix/image-history-performance`, parent `0901b09582171dfc27598c3537dd4f979abc0ac1`.
Source commit: `fd515d97c0a27b11e46e647e6a69ed5f4842cdc3`
(subsequent delivery commit changes documentation only).
The worktree initially matched that parent and was clean. The autonomy writer
flock was available and acquired; after the transient capacity interruption it
was checked again and reacquired, with no competing holder. No reset occurred.

## Explicit owner decision and implementation

The owner authorizes new vision uploads WITHOUT image-content PII analysis or
anonymization and accepts responsibility for visible contents. No OCR, image
recognition service, blurring, EXIF removal or new model was added. Only text
receives basic protection: obvious credentials, e-mail, phone, PESEL, configured
redact terms and existing local-only rules. Ordinary meal/health text is allowed.

The narrow exception lives inside the existing bounded privacy tree walk.
Only exact Chat Completions `image_url` and Responses `input_image` parts can
designate opaque data. Unknown fields inside those parts, unknown attachment
types and malformed envelopes are rejected. Validated base64 in the URL position
returns unchanged before `_text`, so neither secret/PII regex scans nor text
substitutions see image bytes. JSON-encoded versions use the same walk and
cumulative depth/node/character budgets; encoded duplicate keys and ambiguity
remain fail-closed. This is not a generic exception for strings starting with
`data:image` or prose containing a URI. Remote HTTP(S) URLs receive technical
validation AND ordinary textual privacy checks, never opaque handling.

Technical checks require canonical base64, matching PNG/JPEG/WebP byte signature
and MIME, the existing intake size ceiling, and the current boundary budgets.
Signature checks reuse `tools.images`; they are not a full image decoder or a
claim that arbitrary image contents are safe. Existing HTTP/Telegram intake
validation is unchanged. A MIME label over encoded plain text is rejected.
No arbitrary file/audio/video/PDF attachment is newly accepted.

New images still require explicit `K90_ALLOW_MODEL_IMAGES=true`. Original input,
events and conversation records remain local and unchanged. Historical pictures
are validated structurally and omitted before provider transport regardless of
current consent. Text/context remains, HS stays text-only, and no historical
image is replayed. Extra image metadata is blocked rather than ignored; surrounding
text/metadata is filtered normally. UI dismissal and content-free phase timing
from `0901b09` are untouched.

## TDD and changed fixtures

Before implementation, `tests/test_opaque_images.py` produced **14 failed,
3 passed in 0.15s**. Failures demonstrated raw image data entering `_text`,
substitutions changing provider payloads, and unsupported envelopes passing.
One prose check was corrected to use an explicit configured redact term, since
an uninterrupted long digit string is not necessarily a conventional identifier.
After the first implementation the targeted suite had **191 passed in 34.07s**.
An interim full run had **508 passed, 1 skipped in 120.34s**.

Review then added three RED cases for encoded plain text labelled PNG, unknown
image MIME and a PNG signature labelled JPEG: **3 failed, 39 deselected in 0.08s**.
These drove reuse of intake signature/size checks. The subsequent targeted suite
had **135 passed in 39.97s**. Tests also cover invalid/noncanonical base64, encoded
restrictions, secrets/local-only metadata, remote URLs, total/depth/decoded-size
budgets, denied consent, unchanged original persistence and provider bytes.

The owner-approved scope intentionally differs from the old binary-as-text
filter. No previous assertions were removed or loosened. Six test modules had
synthetic fixtures changed from base64-encoded words/zeroes to signature-bearing
synthetic data, because the old words are now correctly rejected as false images.
The large actual-agent fixture now contains 524,268 base64 characters, including
11-digit runs separated by `/`, exposing the old PESEL substitution corruption
across API, Responses and subscription adapters, local/HS, and both history
consent settings. Tests assert exact current-image preservation and text-only
follow-up/HS payloads. These synthetic signatures do not prove real image decoding;
actual-image CI and independent review remain coordinator gates.

Historical reviewer scripts/reports remain unchanged. A scratch copy of
`photo-history-review-resumed-probes.py` changes only its two occurrences of
`c3ludGhldGlj` to `iVBORw0KGgpzeW50aGV0aWM=` to exercise the new signature rule.
Its run here is regression evidence, not a new independent review.

## Reproducible isolated commands

All Python verification uses `/opt/data/projects/k90/.venv/bin/python`, not a
system interpreter. The scratch wrapper is:

```sh
#!/bin/sh
exec env -i PATH=/usr/bin:/bin \
 HOME=/opt/data/cache/scratch/k90-verification-20261025/image-opaque/home \
 DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/image-opaque/data \
 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/image-opaque/test.db \
 XDG_CONFIG_HOME=/opt/data/cache/scratch/k90-verification-20261025/image-opaque/auth \
 PYTHON_DOTENV_DISABLED=1 \
 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. \
 /opt/data/projects/k90/.venv/bin/python "$@"
```

The supplied `sitecustomize.py` network/private-file guard is active. All
basetemps, synthetic auth, databases and logs are under the allowlisted prefix.
No production data/.env/credentials, inference, HS writes or Docker socket access.

```sh
R=/opt/data/cache/scratch/k90-verification-20261025/image-opaque/run-tests
B=/opt/data/cache/scratch/k90-verification-20261025/image-opaque
"$R" -m pytest -q tests/test_opaque_images.py --basetemp="$B/red"
"$R" -m pytest -q tests/test_opaque_images.py -k text_claiming --basetemp="$B/format-red"
"$R" -m pytest -q --basetemp="$B/final-full"
"$R" -m pytest -q docs/review-evidence/privacy_boundary_probe.py docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py /opt/data/cache/scratch/k90-verification-20261025/review_probes.py /opt/data/cache/scratch/k90-verification-20261025/test_independent_boundary_probe.py --basetemp="$B/final-probes"
"$R" -m pytest -q "$B/photo_resumed_signature_probe.py" --basetemp="$B/photo-probes"
"$R" "$B/benchmark.py" > "$B/final-timings.json"
node --check web/app.js
node --test tests/web_*.test.mjs
git diff --check
```

RED commands refer to their pre-implementation source states, not the final tree.
Final full Python suite: **534 passed, 1 existing skip in 129.52s**.
The signature-adapted resumed historical probes: **79 passed in 48.96s**.
Final probes: **166 passed, 1 existing LiteLLM event-loop deprecation warning in
24.53s** (the prior 153-case matrix plus 13 scratch probes). Frontend: **24 passed
in 329.70ms**, JS syntax PASS. No frontend source changed in this follow-up.

## Large payload timings

`benchmark.py` uses deterministic `random.Random(171).randbytes`, a JPEG signature
prefix and canonical base64. It performs three current-policy and historical
projection calls per size, asserting exact preserved bytes or image omission.
Current policy uses `max_chars=2000000`; history uses the unchanged model default
of 2,000,000 with original plus decoded-tree budget accounting. Times in seconds:

| Base64 characters | Current (three calls) | History (three calls) |
| ---: | --- | --- |
| 131072 | .281397, .000758, .000532 | .003694, .003109, .003118 |
| 524288 | .003049, .003113, .003180 | .015076, .014950, .014817 |
| 917504 | .005739, .006454, .007140 | .028205, .027836, .027541 |
| 1572864 | .008996, .009515, .009391 | budget blocked: .004032, .002820, .002904 |

The first current call includes cold import of the shared intake validator.
The initially attempted 1.5 MiB historical timing raised `PrivacyError` because
the original-plus-decoded budget exceeds 2M; the final script explicitly asserts
this rejection. No budget was raised to make the measurement pass. Fixtures are
large realistic-size random binary payloads, not complete JPEG codec fixtures.
These local timings do not establish production end-to-end latency or web/GIL
responsiveness. Prior measurements remain in `image-history-performance.md`.

No push, PR, merge, deployment, account/provider switch or usage reset. Independent
review, actual-image CI and PR decisions remain with the coordinator after exit.
Quota checks: 08:05:48Z session 43% / weekly 7%; 08:07:40Z 46% / 7%;
08:09:13Z 48% / 8%; after interruption 08:12:09Z 51% / 8%;
08:14:19Z 55% / 9%; final verification 08:17:07Z 58% / 9%.
No unknown or >=90% window; no quota pause was required.
