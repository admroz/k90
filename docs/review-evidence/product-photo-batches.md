# Joint product photo batches — author evidence, 2026-10-28

Dependent feature on accepted point1 source `f33897b74a5ba1bc5c266d452e8906c0f83d7143`.
Point1 PR21 was still unmerged at last owner-main fetch (`2f0711e`). This branch
may be pushed as WIP; no duplicated point1+6 PR is authorized. No point4/PR22 code
is included. Independent verification, exact-SHA fork CI/image and final PR are
coordinator gates. No author self-approval, production access or live inference.

WWW accepts one message with 1–4 photos, each <=5,000,000 decoded bytes and total
<=10,000,000. Legacy `image` remains; simultaneous `image` and `images` fields
are rejected. Strict envelope/base64/MIME/signature checks precede enqueue. Both
Content-Length and streamed bodies are limited to14,000,000 bytes. One invalid
photo rejects the whole request. Selection previews, individual removal and
aggregate budget are shown; failed submission retains the selection and request ID.

The current Telegram adapter stores album parts through authenticated internal
HTTP before acknowledging offsets. Backend SQLite deduplicates update/message
IDs, orders captions/photos by message ID, and atomically seals/enqueues one
message. Quiet threshold2s, collection threshold10s; the next part checks elapsed
thresholds, and idle polls flush too. Poll timeout3s and network delays mean
actual idle delivery may occur later than the threshold. Silence does not prove
album completeness. A late new element yields one explicit incomplete/resend-all
notice without a second inference. Over4 photos, invalid input or aggregate excess
reject the entire unsealed album with a transport-only response. The production
adapter bounds streamed downloads before accumulation; legacy server.py retains
its existing single-photo implementation and has no album support claim.

Inbox bounds:32 pending groups,1000 retained groups,7-day sealed/rejected identity
retention. Pending payload survives restart; private inbox images/captions are
cleared after seal/reject, with originals in the existing queue/events. Old-owner
pending albums are never delivered after an owner configuration change. Dedup and
late suppression expire after retention; very old Telegram replays are outside
that guarantee. Inbox-full returns retryable429 without offset acknowledgment.

One batch source event can produce only one catalog draft; a different second
proposal fails in the backend. Point1 owns consent and version checks. The model
prompt requires joint barcode/name/logo/macros interpretation and clarification
for conflicting products/codes, illegibility,100g vs100ml or portion/package
ambiguity, without adding macros. This is not deterministic image recognition;
synthetic clarification tests do not prove live vision accuracy. Meal semantics
are retained. Authenticated evidence returns all photos plus legacy first `image`.
Historical photos are omitted from later model requests; HS remains text-only.

Author evidence: initial RED6; focused85 PASS/1 obsolete7.1MB limit test failed,
then corrected to the approved14MB threshold. Acceptance14 PASS; transport57 PASS
with one test helper typo, corrected. Joint HTTP/SQLite/agent17 PASS; boundary23
PASS including realistic8MB JSON, exact decoded limits and chunked14MB+1.
Real Chromium initially found thumbnail removal blocked by old overflow styling;
after correction PASS: multiselect/remove/error preservation/joint3-image HTTP send.
Final settled source `a03419cd4c0cdc70cb09dcc131933a611828058e`: Python792 PASS /
1 existing optional-import skip (382.15s), Node26 PASS, JS syntax PASS. The earlier
full run was interrupted after discovering the separate old Content-Length bound;
its log remains retained. Final SHA/readback and every command are in the private
phase checkpoint. Subsequent documentation-only commit does not change tested code.

Migration is additive (`telegram_albums`, `telegram_album_parts`), no existing data
rewrite and no new root runtime module/Docker COPY requirement. Use supported
SQLite backup including queue/events and new tables, with documents/config saved
by the existing owner procedure. On rollback stop the adapter/backend together,
back up first, and drain or explicitly discard pending albums: an older adapter
cannot preserve album semantics. Do not replay uncertain already-run jobs.
Live Telegram timing/delivery, real vision quality, deployment, OAuth and HS
integration remain deferred to the owner; synthetic provider fixtures are local.
