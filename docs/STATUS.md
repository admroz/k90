# k90 — bieżący status zadania

## Chat scroll anchor — 2026-10-26

Branch fix/chat-scroll-anchor; author implementation and real Chromium acceptance
PASS on synthetic desktop/narrow history. Behavioral RED captured before source
change: Enter exposed older history with10128px bottom gap before animated
recovery. Instant restoration plus stable visible-message anchor gives0px maximum
gap across Enter and polling/status frames. Reading/prepend/reload/attachment and
submission behavior PASS. Frontend23 PASS; offline Python594 PASS/1 existing skip,
web subset58 PASS. Branch-only WIP checkpoints pushed, no PR/merge/deployment.
Coordinator independent review and actual image CI remain separate gates.
Evidence: [chat-scroll-anchor.md](review-evidence/chat-scroll-anchor.md).


## CI SQLite correction — 2026-10-26

Feature branch feat/chat-timeline-profiling, base bd73eb9; uncommitted correction
awaits fresh independent review before commit/push. Deterministic application
capture regression RED: four database-is-locked failures, history already safe.
Write intent now reserved before runtime initialization reads, preserving existing
caller transactions. Original immutable private probe changed from reproduced=true
to reproduced=false / original_writer_already_reserved, without probe edits.
Two additional reproduced profiling blockers corrected in separate RED/GREEN slices:
SDK timeout hierarchy and returned tool errors. Offline synthetic verification:
594 Python passed / 1 existing optional-import skip (145.56s); frontend 23 PASS,
JS syntax PASS; 29 unchanged independent probes replayed PASS by the writer.
Host suite executes unchanged shipped photo->text helper; actual container CI is
still pending, and replay is not a fresh independent review. No retries, timeout
increase, provider/auth changes, PR, merge or deployment. One source writer.
Private fix-ci result/checkpoint retains commands, immutable snapshot and hashes.

## Chat timeline, text filter and profiling — 2026-10-26

Branch feat/chat-timeline-profiling; tested source `6d3e4b13750e637088e2711eb07cce4d3854cc81`.
IMPLEMENTED — author verification complete; independent review is a later gate.
Four self-reviewed source WIP commits pushed only to origin feature branch,
remote SHA confirmed. Three vertical TDD slices: persistent request-linked
conversation timeline, explicit model text-filter (default true), optional
content-free stage profiling (default false). Final isolated offline Python:
583 passed / 1 existing optional-import skip (136.90s). Frontend 23 PASS,
JavaScript syntax and diff checks PASS. The full suite executes shipped-agent
photo->text with a valid PNG over 95% of 5 MB and unchanged stored originals,
and the exact new embedded container helper on HOST. Actual Docker build/CI
is not claimed; independent review, actual image/CI and final PR stay with
coordinator. No merge/deployment/provider/account changes or production access.
Permanent quota stop is NOW >=80% in ANY window or unknown, superseding older
90% policies below and in IMPLEMENTATION_PLAN. One writer throughout.
Evidence: [chat_timeline_profiling.md](review-evidence/chat_timeline_profiling.md).
Private CHECKPOINT/result retain final head, usage, commands and push readbacks.

## Container photo runtime acceptance — 2026-10-26

Branch fix/image-history-performance, base 6739ffa. Added direct shipped run_agent
photo/follow-up smoke to CHECK (both existing executions). Synthetic provider/auth
only; real history/policy/persistence. TDD RED confirmed; packaging + helper 4 PASS,
photo/history/privacy regressions 240 PASS. Host helper executed twice; actual
image/restart remains CI confirmation. No push/PR/merge/deployment. Quota 64%/10%.
Evidence: [image-runtime-smoke.md](review-evidence/image-runtime-smoke.md).

## Opaque image owner steering — 2026-10-26

Branch fix/image-history-performance, tested source
fd515d97c0a27b11e46e647e6a69ed5f4842cdc3 (parent 0901b09).
Owner-approved image bytes bypass text regex scans/substitutions after strict
envelope/base64/signature/MIME/size/budget validation. No image PII analysis,
anonymization or OCR; text protection, consent, original persistence, historical
omission, HS text-only policy, phase logs and UI dismissal preserved.
534 Python passed / 1 existing skip (129.52s); privacy matrix + extra probes
166 passed / 1 existing warning (24.53s); adapted photo probes 79 passed (48.96s);
frontend 24 passed, JS syntax and diff checks PASS. Quota 08:17:07Z 58% / 9%.
Single writer, synthetic offline verification only; no push/PR/deployment.
Ready for coordinator's independent review and actual-image CI after exit.
Evidence: [image-opaque.md](review-evidence/image-opaque.md).
The older image-performance entry below describes its preserved parent stage.

## Image performance checkout — 2026-10-26

Branch fix/image-history-performance, base 5f90fec (PR13). Local implementation
ready for independent coordinator review; no push/PR/merge/deployment.
Linear email scan, content-free preparation/provider phase logs and explicit
browser-local failure/interruption dismissal. Synthetic verification:
491 Python passed / 1 existing skip, 153 privacy probes passed / 1 warning,
24 frontend passed and JS syntax OK. No production/provider/HS access.
Evidence: [image-history-performance.md](review-evidence/image-history-performance.md).
Quota 08:02:32Z: session 39%, weekly 6%; not paused.
The historical status below concerns the previous memory task.


Stan: READY_FOR_REVIEW — revised personal self-hosted preparation PASS.
Aktualizacja: 2026-10-25 17:10 UTC. Branch feat/long-term-memory, fork hermesinski/k90.
Nie jest to full live acceptance, zgoda na merge ani wdrożenie. PR nie utworzony;
finalne omówienie/utworzenie PR pozostaje z właścicielem.

Testowane źródło i potwierdzony origin:
ef87b75e102f661bc35eaec383ddd2a284f5be8d. Po nim wyłącznie docs/.
Końcowy dokumentacyjny HEAD/remote SHA potwierdzany w prywatnym outcome.json
oraz git HEAD/ls-remote; manifesty celowo wskazują wspólne TESTOWANE źródło.

Zweryfikowane:
- Dokumenty SQLite/rewizje, autorytatywna pamięć lokalna/FTS/outbox, polityka
  outbound, wymienny adapter HS i opcjonalna osobna subskrypcja w aktualnym kodzie.
- Koordynator na ef87b75: 407 Python passed / 1 jawny skip niewybranego importu,
  153 privacy probes PASS / 1 LiteLLM warning, frontend 21 PASS, JS syntax OK.
- GitHub-hosted run 40214045103 SUCCESS na dokładnym ef87b75: 407/1 skip,
  frontend 21, rzeczywisty Docker build, secret-context smoke i network-none
  HTTP/chat + izolowany restart Telegrama PASS. Publikacja obrazu skipped.
- Niezależny finalny read-only reviewer: source/configuration i CI/container PASS,
  własne 19+34 testy i rzeczywista syntetyczna walidacja Compose PASS. Historyczny
  security PASS f39ad1f zachowany. Dwie wskazane korekty docs zamknięte przez
  koordynatora: guard staged/unstaged i aktualizacja manifestów/statusu; bez
  udawania ponownego niezależnego review przyszłych edycji.
- Pełny runbook: docs/DEPLOYMENT_RUNBOOK.md. Dwa osobne stacki, minimalne patche
  dla istniejącego HS bez migracji/restartu, shared network/alias, prywatny .env,
  Mac-local OAuth → SSH → trwały k90-only store, backup/smoke/rollback.
  39 jednoliniowych komend sprawdzono składniowo, obydwa fragmenty Compose
  rzeczywistym config na syntetykach; guard odmawia staged i unstaged zmian.

Brak otwartych bramek PRZYGOTOWANIA według OWNER_ACCEPTANCE. Odroczone do
właściciela: live OAuth/catalog/refresh/provider inference i kredyty, rzeczywiste
ścieżki/DNS/HS API/auth/trusted-network, bank k90 i deployment retain/recall/cleanup.
HS bank ACL i restart-persistence niepotwierdzone; rozbudowany projekt HS testów
nie jest wymagany. Nie twierdzimy pełnej anonimizacji ani produkcyjnej integracji.

Dowody: review-evidence/acceptance.json i independent-review.json (PASS, wspólny
source), independent_preparation_ef87b75.md (oryginalny niezależny raport z jawnie
zachowanymi ustaleniami D1/D2), preparation_delivery_ef87b75.md (ich zamknięcie).
Historyczne manifesty/raporty/partial HS zachowane bez zmiany pomiarów.

Quota: 17:09:47Z Session 25%, Weekly 31%; resety 21:37:40Z / Nov 1 06:22Z.
Obowiązuje >=90% pauza, 80 warning, unknown fail-closed. Obie delegowane role
zakończone, pojedynczy writer pod lockiem nadzorcy. Bez resetów/fallbacku,
main/upstream writes, produkcji, zmian Hermesa/HS lub cudzych tokenów.

Następny krok: właściciel przegląda gałąź i runbook; PR dopiero na końcu z nim,
bez automatycznego merge/deploy. Powiadomienie Telegram przekazuje nadzorca.
