# k90 — bieżący status zadania

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
