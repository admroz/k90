# Own-application logging simplification — 2026-10-27

Author checkpoint; independent review and actual image CI remain separate gates.
This revision supersedes the global interception claims in the historical
safe-runtime-logs report, which is preserved unchanged.

The application now uses ordinary `k90.app`/`k90.profile` loggers, explicit safe
events and a small stdlib `RotatingFileHandler` subclass. A per-stream flock
covers reopen, rollover, write and close for the two container processes.
There is no `Logger.callHandlers` replacement, template translation, foreign
record normalization, pytest forwarding or arbitrary-handler/factory guarantee.
Known SDK loggers are suppressed at bootstrap; narrow Uvicorn and uncaught
process/thread hooks retain safe categories without exception text.

Actual application calls were converted before removing template translation.
Warnings retain their explicit level and bounded numeric fields; provider
status/request metadata, correlation with profiling off, operation identifiers,
profile schema, file permissions/retention and separate error copies remain.
Tool success still means `mutation_outcome=unknown`; response and delivery
outcomes remain separate. No backend/auth/provider or meal-ledger changes.

Synthetic isolated checks: initial RED 2 failed (global dispatch replacement
and missing explicit warning event); adjusted focused suite 84 passed; actual
ASGI/thread, summary/sync and related web/source checks 62 passed. These are
host checks, not certification of the installed image or live integrations.
Final broad Python/Node results and exact tested SHA are retained by the
coordinator in the private point3-simplify-implementation phase artifacts.
The shared image helper's photo/privacy code is unchanged; only its logging
assertions now inspect actual operational files. Docker COPY still includes
`logging_setup.py` and `profiling.py`.

Remaining gates: fresh independent same-source review, exact-image CI/build
and network-none smoke with persistent-volume restart/recreate, then the
coordinator's PR decision. No image publication, merge or deployment.

## Fetcher diagnostic correction — 2026-10-27

Fresh independent review found HTTP diagnostics lost when the Libre fetcher
caught a client error and returned its string. The analogous outer Garmin
fetcher catch had the same loss. Both catches now emit their existing safe
failure event with the exception before preserving the original error result.
No auth, retry, provider or result behavior changed. Real synthetic client
regressions cover both boundaries with profiling on/off, HTTP503/category/code,
correlation, error copies and private canaries. Tight RED reproduced all four
cases plus the unchanged independent Libre probe. Focused GREEN evidence and
final SHA are in the private point3-simplify-fix1 artifacts; independent follow-up
and final normal CI/image acceptance remain pending. No duplicate full suite.
