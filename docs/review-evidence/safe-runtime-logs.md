# Safe local runtime logs — author evidence

Implementation tested at `77f7fbc06f7486d79ad5a21a86f8bc7f889f113b`.
This evidence entry and the status entry are subsequent documentation changes.
Fresh independent verification and an actual image build/smoke remain outstanding.

Behavioral tests first reproduced missing durable profiling, operational output
containing arbitrary exception text/tracebacks, missing diagnostics with timing
disabled, absent tool/response outcome separation, lost HTTP metadata, malformed
SDK metadata replacing a workload exception, unrestricted queue event text,
uncaught exception output, missing CLI/legacy Telegram correlation and caught
dispatcher exceptions without an error record. These were corrected in focused
RED/GREEN slices using synthetic fixtures.

The resulting boundary writes app/errors JSON and a separate profiling JSONL.
Tests exercise two concurrent processes, rotation/reopening in a third process,
retention bounds, 0700/0600 permissions, sink failure preserving the stored job
result, SDK/protocol status metadata, repeated delivery scope identity and
bootstrap imports for web, Telegram and CLI. Canary inputs cover arbitrary
objects, exception messages, URLs, secrets, image/base64 payloads and extra fields
across files and console. A returned tool success never proves commit:
`mutation_outcome` remains unknown without transaction evidence.

Author offline results:

- `python -m pytest -q`: **680 passed, 1 skipped**, 220.08 seconds.
- `node --check web/app.js`: exit 0 at `4e39fbfdf0f3f548a6abf5e626c3bf656df1bbcd`.
- `node --test --test-isolation=none tests/web_*.test.mjs`: **25 passed** at that
  same source; only Python fake-source test opt-ins changed before `77f7fbc`.
- Docker COPY contract and shipped observability helper executed on the host as
  part of Python tests. This does **not** establish a successful image build.

Tests used isolated synthetic data/auth directories, disabled dotenv, default
sync/Telegram off, fake model/source boundaries and inherited network restrictions.
Five existing fake-source unit tests explicitly enable sync after installing their
fake, so the offline default cannot bypass their assertions. Node used one test
process; child Python tests ran under separate watchdogs without relaxing their
timing assertions. No production artifacts, real providers or live auth were used.
The provider failure cause remains undetermined.

Runtime format, limits, backup/retention and owner deployment/rollback checks:
[WEB.md](../../WEB.md#trwałe-logi-operacyjne). No PR, image publication or deployment
is claimed by this author checkpoint.
