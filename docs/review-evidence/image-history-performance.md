# Image history performance and dismissible failure cards

Base: upstream/main at 5f90fec (PR13 included). Branch: fix/image-history-performance.
Executor: Codex CLI, source interpreter /opt/data/projects/k90/.venv/bin/python.
Synthetic data only; no application inference, real images, production reads,
provider calls, HS writes, Docker access, configuration tuning, push or deployment.

## RED / GREEN and mechanism

Before implementation, the parent's unchanged 128 KiB projection regression failed:
1 failed in 3.06s, subprocess exceeded its 3s deadline. The added long-token test
also failed at its 4s deadline; email compatibility characterization passed.
After implementation both deadlines pass, including 512 KiB projection and
512 KiB tokens without @, with a missing domain dot, with a long invalid domain,
a valid very long local part, and a long dotted domain with trailing punctuation.

The original unanchored greedy email local part retried every suffix of a run.
The replacement consumes a maximal local-part run once and attempts the unchanged
domain grammar at its end. All suffixes have the same following @ and domain, so
a failed full run implies failed suffixes. Successful matches resume at the domain
end, exactly as re.sub does, including immediately adjacent punctuation/local parts.
Failed domain attempts and local scans traverse each run only a bounded number of
times. No email length cap or intentional redaction-semantic difference was added.
Unicode word characters, punctuation, partial malformed-address matches and
leftmost/non-overlapping behavior remain covered by the original grammar oracle:
3,906 exhaustive strings over a/@/./+/space plus explicit valid/malformed examples.

project_history still inspects the original with image-field inspection allowed
before projecting recognized historical images. No filters were disabled and no
unvalidated input is silently discarded. Local-only, metadata, nested encoded JSON,
duplicate keys, secrets, image consent and envelope checks remain enforced. Local
originals and audit events remain unchanged. Generic filtering is not a guarantee
of complete anonymization.

Measured project_history seconds in this checkout (one sample each; synthetic A
base64, not a decoded picture). For the old comparison only the email substitution
function was temporarily replaced in a separate benchmark process by its exact
original regex, leaving all remaining projection/filtering code intact:

| Base64 characters | Old | New |
| --- | ---: | ---: |
| 8,192 | 0.325085 | 0.001825 |
| 16,384 | 1.289140 | 0.003426 |
| 32,768 | 5.039620 | 0.006415 |
| 131,072 | >3s RED deadline, not a completed timing | 0.025705 |
| 524,288 | Not run | 0.103058 |

Parent's separately reported old measurements were .2888/1.158/4.5622 seconds
for 8k/16k/32k. These are separate observations, not replaced by this run.

## Reproduction and isolation

All Python commands below used this environment wrapper, stored outside Git at
/opt/data/cache/scratch/k90-verification-20261025/image-performance/run-tests:

~~~sh
#!/bin/sh
exec env -i PATH=/usr/bin:/bin \
 HOME=/opt/data/cache/scratch/k90-verification-20261025/image-performance/home \
 DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/image-performance/data \
 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/image-performance/test.db \
 XDG_CONFIG_HOME=/opt/data/cache/scratch/k90-verification-20261025/image-performance/auth \
 PYTHON_DOTENV_DISABLED=1 \
 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. \
 /opt/data/projects/k90/.venv/bin/python "$@"
~~~

Test basetemps are separate subdirectories under that same allowlisted scratch
prefix. No previous private .env, application data or credential directory was used.

~~~sh
R=/opt/data/cache/scratch/k90-verification-20261025/image-performance/run-tests
B=/opt/data/cache/scratch/k90-verification-20261025/image-performance
"$R" -m pytest -q tests/test_history_image_performance.py --basetemp="$B/red"
"$R" -m pytest -q tests/test_history_image_performance.py tests/test_photo_history.py tests/test_web_runtime.py --basetemp="$B/green2"
"$R" -m pytest -q --basetemp="$B/full"
"$R" -m pytest -q docs/review-evidence/privacy_boundary_probe.py docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py --basetemp="$B/privacy153"
node --check web/app.js
node --test tests/web_*.test.mjs
~~~

The initial RED command preceded all implementation changes; its parent test was
subsequently parameterized for 128/512 KiB. Green2: 65 passed in 43.27s.
The actual run_agent upload -> text test now uses 512 KiB synthetic base64 across
API, Responses and subscription, local and fake HS, and both followup consent
values. It checks original persistence, omitted historical images, zero diet
side effects and no image sent to HS. All provider/HS receivers are in-process
synthetic transports.

To reproduce the timing table, run the following through the same wrapper
(the \x60 spelling denotes the original literal backtick):

~~~python
import json, re
from time import perf_counter
from outbound_policy import project_history
from k90_memory import privacy
old = re.compile(r"(?i)[\w.!#$%&\x27*+/=?^\x60{|}~-]+@[\w-]+(?:\.[\w-]+)+")
def raw(n):
    return json.dumps([{"type": "text", "text": "Synthetic meal"},
        {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + "A" * n}}])
new = privacy._redact_emails
for label, sizes in (("old", (8192, 16384, 32768)),
                     ("new", (8192, 16384, 32768, 131072, 524288))):
    privacy._redact_emails = (lambda s: old.sub("[REDACTED]", s)) if label == "old" else new
    for n in sizes:
        start = perf_counter()
        project_history(raw(n))
        print(label, n, perf_counter() - start)
~~~

## Failure-card behavior

Queued/running cards always remain visible. Failed/interrupted cards remain visible
until the user explicitly selects “Ukryj w tej przeglądarce”. The CSP-safe listener
only updates browser storage/rendering: no request, retry, requeue, tool execution,
DB change, audit deletion or history deletion. Backend /api/jobs continues returning
failure/interruption states; done jobs remain excluded and are never presented as
failures. Cards show channel and creation time to distinguish old cross-channel
failures from current work.

localStorage key k90.dismissed-jobs.v1 contains at most 500 request IDs (each at
most 200 characters), without message content, status, timestamp or channel.
The oldest dismissals expire when full; old cards can reappear. New IDs remain
visible, and an active state is never hidden even if its ID is stored. Clearing site
storage or using another browser restores visibility. When storage is unavailable,
dismissal works only for the current page; malformed storage fails visibly.
Frontend tests cover reload, bounded storage, fresh failures, active/done states
and invoking the actual app listener without any network mutation. Backend contract
tests verify that repeated job reads preserve queue/database states.

## Phase profiling and limits

New content-free logs: conversation.claim with sequence/channel only, agent begin,
capture/history/context/recall elapsed milliseconds, provider.start round and
provider elapsed milliseconds (also emitted on failure). No prompts, tokens,
URLs, patient/source text or credentials are added to these logs. No schema change.
Provider phase includes boundary filtering and response conversion, so it is not a
pure network-duration metric. With one conversation worker, sequence plus channel
and timestamps correlate the phases.

Compare job created_at -> conversation.claim for queue waiting; claim -> agent begin
covers pre-agent processing such as sync/commands; then capture/preparation/provider
phases distinguish subsequent work. Existing agent.start is after preparation.
The owner's job44 observation was 142s total, with 125.083s before agent.start and
17.055s afterward. This code fixture does not establish the cause of every second.
Production phase profiling remains for the owner after review/deployment. No
GIL/web-starvation or bounded thread-responsiveness claim is made by this work.
Real integration, container CI and production acceptance remain untested here;
the coordinator will run image CI after independent review.

## Final verification and review handoff

- Full Python: 491 passed, 1 skipped in 123.08s. The skip is the existing
  explicitly unselected local data import, not a waived new regression.
- Privacy probes: 153 passed in 22.51s; one existing LiteLLM event-loop
  DeprecationWarning. All transports synthetic/local, no application inference.
- Additional scratch review_probes.py and test_independent_boundary_probe.py:
  13 collected tests passed in 5.21s (plus module-level synthetic assertions).
  Command used the same wrapper, -m pytest -q, these two absolute scratch paths,
  and --basetemp under image-performance/probes.
- Frontend: 24 passed; node --check web/app.js passed.
- git diff --check passed after whitespace cleanup.
- New logging tests were RED (2 failed) before instrumentation, GREEN afterward.
  Dismissal tests were RED before the exported feature existed, GREEN afterward.
- Self-review covered complete implementation/test diff, preserved email matching
  grammar and scan progression, browser-only side effects, original-history
  validation and content-free added logs. Independent coordinator review remains
  required before push/PR. No independent approval is claimed.
- Last quota check 2026-10-26T08:02:32Z: session 39%, weekly 6%; neither unknown
  nor >=90%. No reset or fallback used. Not paused for quota.
- Single writer held /opt/data/jobs/k90-autonomy/worker.lock during changes.
