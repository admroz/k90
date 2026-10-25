# k90_memory integration contract

This package is an offline-testable foundation, not an enabled application hook.
SQLite originals/history are authoritative. Hindsight is a disposable index.
There is no automatic history import, UI, LLM call, bank creation or scheduler.

## Local API (caller owns commit/rollback)

```python
from k90_memory import (
    initialize, upsert_source, delete_source, search_local, hydrate,
    SourceRef, rebuild_queue,
)

initialize(conn)  # schema/FTS5 when supported; DOES NOT commit
source = upsert_source(
    conn, source_id="conversation:123", owner="owner", role="user",
    content="Syntetyczny tekst", occurred_at="2026-01-01T12:00:00Z",
    kind="conversation", local_only=False,
)
conn.commit()  # commit conversation and source/outbox together in application code

sources = search_local(conn, "owner", "tekst", limit=10)
sources = hydrate(conn, "owner", [SourceRef("conversation:123", 1)])
delete_source(conn, "conversation:123", "owner")
conn.commit()

rebuild_queue(conn, "owner")  # active current sources only; no remote import
conn.commit()
```

- Source identifiers must be strings; choose opaque application IDs, never names,
  e-mail addresses, credentials, or patient identifiers. Identifiers/provenance
  that a policy would rewrite are blocked rather than silently changed.
- Sources are keyed by `(owner, source_id)`. Every upsert creates the next revision;
  deletion appends a tombstone retaining all earlier content, role and date.
  Deleting an absent/already deleted source is idempotent. Recreating a tombstoned
  source creates another revision, never resets the counter.
- `memory_sources`, `memory_versions`, `memory_fts`, `memory_outbox` are package
  tables. The schema uses individual statements/savepoints, not executescript.
  Upsert/delete/FTS/outbox roll back as one operation on any error. Existing caller
  transactions are preserved; a fresh connection starts an uncommitted transaction.
- `Source` is frozen and includes `role`, `occurred_at`, `kind`, `local_only`,
  `revision`, `deleted`. Original local text is never redacted in place.
- Search is owner-scoped, uses quoted literal word tokens (not user MATCH syntax),
  caps query length/token/result count, and falls back to parameterized literal
  substring search if the FTS table is absent. Fallback is not semantically equal
  to FTS tokenization/ranking and may scan the owner's active sources.
- Hydration only accepts a current, nondeleted revision of the requested owner,
  deduplicates, and bounds examined references/results. It returns LOCAL ORIGINALS,
  including local-only sources; they are NOT safe to forward without the policy.
- Neither assistant suggestions nor health measurements are promoted to facts.
  Build model context with the original role/date, not the generated HS fact text.

## Worker and backend

```python
from k90_memory import HindsightBackend, PrivacyPolicy, Worker, retrieve

policy = PrivacyPolicy(redact_terms=("Fikcyjne Nazwisko", "ul. Testowa 7"))
backend = HindsightBackend(
    "https://trusted-memory.example.invalid", "configured-k90-bank", policy=policy,
    timeout=5, max_response_bytes=1_000_000,
)
worker = Worker(
    get_conn, backend, policy=policy,
    pseudonym_key=deployment_stable_random_key_bytes,  # >=16 bytes; keep outside source text
)
worker.run_once(limit=20)  # run in application worker; returns CLAIMED count
sources = retrieve(
    conn, "owner", "spacer", backend=backend, policy=policy,
    pseudonym_key=deployment_stable_random_key_bytes, limit=10,
)
```

`get_conn()` must return a fresh SQLite connection owned/closed by the worker,
not a contextmanager or a connection with an existing transaction. Initialize
and commit schema once before running workers. Mutations and worker traffic
must use the same local database. Application code schedules repeated ticks.

`BackendProtocol` is `retain(MemoryDocument) -> None`,
`delete(document_id) -> None`, `recall(owner_tag, query, limit) -> list[SourceRef]`.
Replacement backends receive already sanitized documents and owner pseudonyms.
Retain/delete must acknowledge completion or raise; deletion must be idempotent.
A custom backend must provide its own bounded timeouts. `retrieve` falls back to
local search on ordinary backend/filter errors, missing valid refs, or no backend.
It does not turn a local fallback result into permission for model egress.

Claims use short `BEGIN IMMEDIATE` transactions, random lease tokens, durable
attempt counters, and CAS acknowledgements. No DB connection/lock remains open
during backend I/O. Default lease is 60 s; crashes are retried after expiry.
Retries use capped exponential backoff; errors store fixed codes only.
`blocked` privacy jobs require explicit `rebuild_queue` after correcting policy.
Pending obsolete retains are superseded; deletion jobs are separately durable.
The batch limit counts all work, including deletion jobs, not just successful
retains. A backend outage does not undo local application commits.

**Important revision design:** document IDs are stable per **source revision**,
not shared by all revisions of a source. HMAC-derived IDs/tags exclude raw owners.
HS has no conditional/fenced replace; a merely stable source-level document ID
would let a delayed old HTTP request overwrite a newer correction after a lease
expires. Revision-specific IDs make that overwrite impossible. Corrections queue
old-document deletion; stale in-flight completions queue cleanup again. Replays
of the same revision reuse exactly the same document ID and `update_mode=replace`.
Keep the pseudonym key stable across restarts/rebuilds, and separate it from
credentials used by other features. Rotating it requires deliberate bank cleanup.

Hindsight uses fixed configured URL/bank, fully quoted path components, HTTPS by
default, no redirects/proxy inheritance, bounded bodies/responses and socket
I/O timeouts. HTTP requires explicit `allow_internal_http=True` (the deployer
must ensure the configured host is actually internal). Sync retain sends
`async:false` and verifies success, bank, item count and `async:false` in the ack.
Only raw `world`/`experience` results with document provenance are used; observations
and server-generated text are never authoritative. Recall uses HMAC owner tags,
`all_strict`, low budget, capped tokens, and no included entity/chunk payloads.

A bank/tag is NOT authorization. Auth/network ACLs, HTTPS deployment, backups,
retention, protection of the pseudonym key, and access separation from other
agents are separate deployment requirements, not implemented by this package.

## Outbound policy for the application LLM boundary

```python
from k90_memory import PrivacyPolicy, PrivacyError

try:
    safe_messages = policy.sanitize(messages)   # fresh tree, including keys/JSON arguments
    safe_text = policy.sanitize_text(text)
except PrivacyError:
    # Do not call the model/backend, do not log input or original exception.
    pass
```

The policy masks common e-mail, PESEL and Polish/US/international telephone
formats, plus case-insensitive literal configured terms. Health context itself
is allowed. It blocks recognized secrets/Bearer/API-key assignments, sensitive
JSON keys, local-only flags/explicit markers, binary/unknown objects, excessive
sizes/depth, nonfinite numbers, key collisions and policy failures. JSON-encoded
arguments are decoded and sanitized, including escaped keys. Control fields such
as role/call IDs are not silently rewritten; such a redaction blocks the payload.
Unknown extra argument dictionaries are not exempted. There is no logging of
payloads or upstream response bodies in this package.

Images/files/multipart attachments are blocked by default. A separately created
`PrivacyPolicy(allow_images=True)` is explicit MODEL-boundary consent, not image
redaction; consent never enables HS image/file indexing. The HS/worker boundary
always applies a second image-disallowing baseline policy. Only textual
`conversation`, `document` and `note` kinds can be retained.

## Limits / remaining integration responsibilities

- This is heuristic masking, NOT complete anonymization. Configure names,
  addresses and other identifiers locally. Obfuscation, encoded arbitrary blobs,
  novel credential formats, unusual phone formats and contextual reidentification
  are not guaranteed detectable. Conservative false positives may block payloads.
- Do not send credentials as model payload fields. Transport credentials must be
  independently configured; this adapter does not discover tokens or add auth.
- Parent must install the shared policy immediately before EVERY model call,
  including summaries, restored originals, tools/results, image paths and retries.
  This package alone does not secure existing application LLM calls.
- Source changes immediately invalidate local hydration, but remote deletion is
  eventual. An upstream request that times out can continue server-side; without
  server cancellation/CAS no client can guarantee instantaneous erasure of a late
  old request. Revision IDs prevent newer overwrite and hydration prevents stale
  context; unknown late remote residues may still require operational cleanup.
- Tightening a policy does not purge an already indexed bank retroactively. A
  policy/key change needs a deliberate purge/new-bank and rebuild procedure.
  `rebuild_queue` does not erase unrelated bank contents or recover lost outbox
  deletion jobs from historical versions.
- Stdlib timeout bounds socket operations, not a strict total wall-clock deadline
  against a pathological slow-drip peer. Normal timeouts trigger local fallback.
- No real HS/network/LLM tests have been run by this subagent. Schema payloads were
  checked against the supplied local OpenAPI; live integration remains for parent.
