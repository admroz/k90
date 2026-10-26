# Weryfikacja — checkpoint 2026-10-25

## 2026-10-26 — owner-approved opaque image follow-up

Worktree /opt/data/projects/k90-image-performance, branch fix/image-history-performance.
Tested source fd515d97c0a27b11e46e647e6a69ed5f4842cdc3; parent 0901b09.
Initial clean worktree and free writer flock confirmed; after capacity interruption
changes preserved and lock reacquired without conflict. Only this run writes source.
Implementation: k90_memory/privacy.py, outbound_policy.py, new opaque tests and
six updated signature-bearing synthetic test fixtures. No old assertions weakened.
Docs: README, OPERATIONS_MEMORY_AUTH and evidence clarify no image PII analysis,
no anonymization/OCR/EXIF removal and no binary-as-text scanning/substitution.
Text basic regex rules and structural/local-only restrictions remain; originals
local, new vision consent required, history never replays images, HS text-only.
Prior UI dismissal and phase instrumentation unchanged.

TDD RED: 14 failures / 3 passes before implementation (0.15s); format hardening
RED: 3 failures / 39 deselected (0.08s). Final full Python 534 passed / 1 existing
skip (129.52s); privacy matrix + extra probes 166 passed / 1 existing warning
(24.53s); signature-adapted historical probes 79 passed (48.96s); frontend 24 PASS
(329.70ms), JS syntax PASS, diff checks PASS. Exact commands, wrapper, logs and
timings: [image-opaque.md](review-evidence/image-opaque.md).
All Python uses actual app venv + env -i synthetic HOME/DATA/DB/auth under
/opt/data/cache/scratch/k90-verification-20261025/image-opaque/, dotenv disabled,
supplied privacy/network guard enabled. No production data/credentials, provider
inference, HS writes or local Docker access. Large random signature-bearing
524288-character base64: current 0.003049–0.003180s, history 0.014817–0.015076s.
1.5 MiB history intentionally blocked by unchanged cumulative 2M character budget.
Quota final verification 08:17:07Z: session 58%, weekly 9%, no pause/reset/fallback.
No source blocker. Coordinator gates after exit: independent review, actual-image
CI and PR decision. No push/PR/merge/deployment performed.

## 2026-10-26 — image history performance checkout

Branch fix/image-history-performance, base 5f90fec. Parent regression RED before
implementation (128 KiB subprocess >3s). Preserved original-history validation;
replaced quadratic email suffix retry with equivalent bounded scans. Added
content-free claim/preparation/provider logs and explicit browser-local dismissal
of terminal failure/interruption cards. No queue/history/audit mutations or retry.
Full Python 491 PASS / 1 existing skip (123.08s), privacy probes153 PASS / 1
existing warning (22.51s), extra synthetic probes13 PASS (5.21s), frontend24 PASS,
JS syntax and diff checks PASS. Precise isolated commands, measurements,
changed behavior and limits: review-evidence/image-history-performance.md.
Latest quota 08:02:32Z session39/week6. No quota pause, reset, provider calls,
HS writes, production reads, Docker access, push, merge or deployment.
Next: independent coordinator review; image CI after review.


## Końcowy odbiór revised preparation — 2026-10-25 17:10 UTC

Koordynator wykonał validate_preparation.py: PASS — wspólny source/PASS obu
manifestów, osiem obszarów, remaining_gates=0, full_live_acceptance=false,
wszystkie evidence paths istnieją, hash niezależnego raportu i historyczne kopie
zgodne byte-for-byte, tylko docs/ po source. Ponowny runbook_check.py PASS.
Skan dziesięciu jawnie przejrzanych kandydatów bez trafień; oba diff checks PASS.
To ograniczony skan, nie gwarancja braku dowolnego sekretu. Quota17:09:47Z
25%/31%, resety21:37:40Z/Nov1 06:22Z. Final clean+remote gate po push.

READY_FOR_REVIEW, nie full-live/merge/deploy. Testowany source
`ef87b75e102f661bc35eaec383ddd2a284f5be8d`; po nim wyłącznie docs/.
Szczegółowe wykonane polecenia, real CI/run/jobs i zamknięcie dokumentacyjne:
[preparation_delivery_ef87b75.md](review-evidence/preparation_delivery_ef87b75.md).
Oryginalny niezależny raport zachowano byte-for-byte w
[independent_preparation_ef87b75.md](review-evidence/independent_preparation_ef87b75.md),
cmp exit0, SHA256 909e5dbc6408769562157335db748cc7009be53bca32b6c527e6ebbd27bc1dea.

Koordynator na exact source: full407 PASS/1 skip (83.03s), probes153 PASS/
1 warning (17.44s), frontend21 PASS, JS syntaxOK. Skip tylko niewybranego
lokalnego importu; ostrzeżenie LiteLLM o event loop. Inspected env-i/offline guard,
syntetyczne dane i loopback receivers, bez modelu/HS/produkcji.

GitHub run40214045103 na ef87b75 SUCCESS, exact jobs/steps/logs odczytali
niezależnie reviewer i koordynator. Test job121231213864 PASS: Python407/1skip
(12.49s), frontend21, Docker image build i oba real smoke PASS. Secret-context:
12 fikcyjnych prywatnych ścieżek root/dwie głębokości i positive control;
runtime --network none/preview: HTTP/chat i izolowany restart Telegrama, backend
PID zachowany. Publish job121231505502 skipped, bez publikacji/deploy.

Finalny niezależny reviewer source/configuration+CI PASS, własne 19+34 testy
PASS, Compose probe PASS. Jego dokładny dokumentacyjny verdict na source
był FAIL_PENDING_D1_D2: guard pomijał staged i aktualne manifesty były stare.
Zgodnie z jego precyzyjną ścieżką zamknięcia koordynator poprawił wyłącznie
docs: dokładny diff --quiet HEAD --, aktualne evidence/manifests/status i
zachowanie historycznych kopii. Nie udajemy niezależnego review tych przyszłych
edycji. Koordynator uruchomił runbook_check.py: 39 jednoliniowych shell komend
parse PASS, clean/unstaged/staged guard PASS, obydwa wstawiane fragmenty sieci
rzeczywistym Compose config na syntetykach PASS; base compose_probe.py PASS.
Bez prawdziwego env/host Compose/Docker daemon/infra zmian/logowania.

Aktualne manifesty wspólnego source mają verdict PASS i remaining_gates=[]
w ramach OWNER_ACCEPTANCE; full_live_acceptance=false, live OAuth/provider
i topology-specific HS smoke/auth/trust pozostają w deferred_live_checks.
Nie testowano live finalnego OAuth ani ACL/restart-persistence HS. Historyczne
partial HS i f39ad1f security PASS zachowane bez relabelowania.
Obie role zakończone. Quota 17:04:12Z 21%/30%, resety 21:37:40Z / Nov1 06:22Z;
bez reset/fallback/account switch, main/upstream writes, merge/deploy/produkcji.

## Wznowienie po resecie 16:37 UTC — Actions uruchomione

OWNER_ACCEPTANCE odczytano jako pierwszy, potem całe VERIFICATION, AGENTS, plan,
architekturę i operacje. Zastany jedyny diff był dopiskiem właściciela o runbooku;
pełny odczyt, skan jednego kandydata bez trafień, hooks tylko sample i workflow
feature bez publikacji. Checkpoint 0a7939a8e5897b76138be0b312fccbcd0f598fc4
push origin feature i ls-remote zgodne. Lock PID212009 jest nadzorcą/rodzicem
tej sesji; brak obcego writera. Pierwsza łączona komenda z Python -c zablokowana
przed wykonaniem; ponowiono bez niej. Bez zmian ochrony/konfiguracji Hermesa.

Quota usage_api: 16:37:53Z Session 1%, Weekly 27%; 16:45:57Z 8%/28%; resety
21:37:40Z / 2026-11-01T06:22:00Z. Reset nastąpił naturalnie; bez banked reset,
płatnego fallbacku, zmiany kont/providera. Aktualna polityka >=90%, 80 warning.

Niezależny read-only reviewer: scoped Compose/OAuth funkcjonalnie PASS,
26 testów (1.69s) + 8 no-fallback/refresh tests (3.67s), syntetyczny Compose
probe PASS, zero zmian checkout. Medium zalecenie: root-only Docker ignore
nie zapewnia dowolnego zagłębienia. Runbook niekompletny. Żadnego nowego
audytu naprawionej historycznej luki JSON. Nie jest to finalny PASS nowego source.

Rzeczywista przyczyna pustego Actions: zalogowana strona forka pokazała
„Workflows aren't being run on this forked repository” i formularz enable,
chociaż REST actions/permissions enabled=true. Zapisane konto przez vault,
bez ujawniania hasła; włączono przejrzane workflows. Odczyt strony „Actions
Enabled”, potem REST workflows total_count=1, docker.yml active. Nie zmieniono
main ani sekretów/rejestru/produkcji. Jeden błędny selektor JS nie wykonał akcji;
ponowiona poprawna akcja i readback potwierdziły skutek.

Polecenia koordynatora (scratch helper odczytany przed użyciem):

```sh
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/github_ci.py diagnose
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/github_ci.py dispatch
.venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/ci_evidence.py 40213398796
```

Run 40213398796, source 0a7939a8e5897b76138be0b312fccbcd0f598fc4,
workflow_dispatch SUCCESS, test job 121229276248 SUCCESS. Logi pobrano przez
authenticated API do prywatnego scratch; przejrzane wyniki: Python 406 passed,
1 skipped in 14.73s; frontend 21 PASS/0 FAIL; rzeczywisty Docker build i
scripts/smoke_container.py network-none PASS, w tym izolowany restart Telegrama.
Job build/publish skipped (121229556194). Bez publikacji, deploymentu i provider calls.

Zalecenie ignore: dodano contract test przed poprawką:
`bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh recursive-ignore-red tests/test_compose_contract.py`
— 1 failed / 2 passed, brak czterech recursive patterns. Po dodaniu wzorców
`**/.env`, `**/.env.*`, `**/chatgpt-auth/`, `**/credentials.json` identyczny
wybór z label recursive-ignore-green: 3 passed in 0.02s, exit 0.
Nowy scripts/smoke_build_context.py kopiuje TYLKO ignore do nowego syntetycznego
kontekstu, testuje 12 fake private paths i publiczny positive control prawdziwym
Docker COPY/run, sprząta unikatowy obraz. Dalszy CI i niezależny review pending.

Historyczne stany/quota poniżej pozostają dowodami swoich sesji, nie aktualną polityką.

Końcowy WIP checkpoint `c3b00f64db2472864e8a35869c5669e856ef47ce`
wypchnięto wyłącznie do origin feature, ls-remote zgodny, checkout czysty.
Przed push jawny skan 10 przejrzanych kandydatów bez trafień i diff checks PASS;
ograniczona heurystyka, nie gwarancja pełnego wykrycia sekretów. Utrwalono też
zewnętrzny dopisek właściciela bez ingerencji w treść. Odczyt po push
14:24:21Z Session 82%, Weekly 26% wymusza PAUSED_FOR_QUOTA. Resety
16:33:40Z / Nov 1 06:22Z. Po źródłach tylko docs. Brak działających dzieci.

## Wznowienie 14:15–14:22 UTC — revised scope, Compose WIP

OWNER_ACCEPTANCE.md odczytano jako pierwszy i zachowano w checkpoint commit
`e910dd9fbfcd5d8d0ae59f161c3007d1bf1ffb06`; push oraz ls-remote zgodne.
Jedyną zastaną pracą był ten nowy dokument właściciela. Pełny odczyt, skan
jednego kandydata i diff checks PASS; hooks tylko sample, workflow nie publikuje
na feature, upstream push DISABLED. Lock PID187532 to rodzic tej sesji,
nie obcy writer. Pierwsza komenda rozpoznania z Python -c zablokowana przed
wykonaniem; ponowiono bez niej i bez zmiany ustawień bezpieczeństwa.

Szczegółowy nowy dowód: review-evidence/compose_checkpoint_20261025.md.
TDD 2 failed → 2 passed; koordynator pełna regresja 406 passed / 1 skipped
(84.51s), frontend 21 passed, syntax OK. Rzeczywisty standalone Compose
na skopiowanym YAML i syntetycznym env: passthrough/password/volume PASS.
Brak kontenera/CI/HS restart proof; niezależny review nowych zmian nieukończony.
Obie delegowane role zakończone. Brak zapisu main/upstream i dostępu do produkcji.

O 14:23 UTC git diff ujawnił obcą zmianę OWNER_ACCEPTANCE.md: dopisek
„Later owner clarification” odracza rozbudowane HS testy do wdrożenia. Nie był
to zapis koordynatora ani jego dzieci. Zachowano cały dopisek; przerwano dalszą
implementację zgodnie z zasadą jednego writera. Tylko bezpieczny WIP checkpoint
i status; kolejna sesja potwierdzi wyłączność. Odczyt quota 14:23:02Z 79%/25%.

Quota usage_api 14:15:03Z 71%/24%, 14:17:05Z i 14:18:16Z 75%/25%,
14:19:36Z 76%/25%, 14:21:52Z 78%/25%; resety 16:33:40Z / Nov 1 06:22Z.
Bez resetów, fallbacku, zmian kont/providerów. Następny etap dopiero po świeżym
odczycie wszystkich okien <80%. Historyczne BLOCKED_OWNER poniżej jest zastąpione
nową zgodą właściciela: nie żądać Docker dostępu ani live OAuth przed odbiorem.

## Zamknięcie tej sesji — BLOCKED_OWNER, 12:45 UTC

Checkpoint dowodów `e31a42754fa181accf2fc0f7a698afaae0996117` wypchnięty
wyłącznie do origin/feat/long-term-memory; HEAD i ls-remote zgodne, checkout
czysty po push. Przed push pełny odczyt nowych syntetycznych plików i diff,
scan_delivery.py (7 jawnych kandydatów, zero trafień), diff checks PASS.
Skan ograniczony heurystycznie; nie oznacza wykrycia każdego możliwego sekretu.
Hooks/workflow sprawdzone przed push: bez aktywnych hooks, brak publikacji na feature.

Ponowny odczyt GitHub API 12:45 UTC po push: runs nadal [], workflows nadal []
(HTTP 200). Wraz z wcześniejszym enabled=true i brakiem lokalnego demona oznacza
brak dostępnego runnera/container proof. Nie deklarujemy przyczyny ani CI PASS.
Właściciel musi aktywować/zdiagnozować workflow forka i zapewnić autoryzowany
test-only runner z Dockerem. Istniejący workflow buduje i wykonuje smoke na feature
bez publikacji. Nie jest potrzebny main write, wczesny PR ani deploy.

Pozostałe minimalne działania właściciela:

1. Odrębnie zalogować finalną aplikację k90 (`subscription_login`, instrukcja
   OPERATIONS_MEMORY_AUTH.md), potwierdzić wyłączone dodatkowe kredyty i zapewnić
   kontrolowany test realnego katalogu/refresh/streamingu/narzędzi/obrazu na
   syntetykach. Tokeny wyłącznie prywatną ścieżką opisanej obsługi sesji; nie
   z Hermesa, Git ani czatu. Historyczny tester wykonalności nie zastępuje tej bramki.
2. Zapewnić izolowany restartowalny HS (lub własne okno restartu) i ograniczony
   endpoint/tożsamości testowe allowed/denied, aby zweryfikować bank ACL oraz
   trwałość po rzeczywistym restarcie. Nie restartować wspólnego serwisu bez zgody
   ani nie badać istniejących banków. Real retain/recall/retry/rebuild/cleanup ma
   już częściowy dowód; nie jest dowodem ACL/restartu.

Acceptance manifest obejmuje wszystkie osiem obszarów i ma verdict BLOCKED;
remaining_gates nie jest puste. Nie ma obietnicy gotowości PR. Niezależny
offline security/source review PASS pozostaje ograniczony do badanego źródła,
syntetyków i lokalnych odbiorników. Nowe zmiany wyłącznie dokumentacyjne.
Przed zamykającym push validate_delivery.py potwierdził: wspólny testowany
source commit obu manifestów, osiem obszarów, cztery otwarte bramki, istnienie
wszystkich wskazanych dowodów, właściwą gałąź/remotes oraz wyłącznie docs od
testowanego źródła. Scan czterech jawnych kandydatów bez trafień; diff checks
PASS. To kontrola spójności dowodów/BLOCKED, nie wynik testów integracji.
Obie role zakończone, brak pozostawionego implementatora. Stan nie jest skutkiem
quota: usage_api 12:45:05Z Session 63%, Weekly 23%; resety 16:33:40Z / Nov 1
06:22:00Z. Nie użyto reset/fallback ani nowych kont. Finalny dokumentacyjny SHA
zostanie potwierdzony ls-remote po push i zapisany w prywatnym outcome.json.

## Wznowienie 12:21–12:43 UTC — niezależny review offline PASS, integracje nadal otwarte

Przed zmianami checkout był czysty; HEAD i zdalne origin feature wskazywały
`8133b1bbd1488ef8747095fb39a5bfd9f098e1b7`. Nie było pracy do ratowania.
Lock worker.lock trzymał nadzorca PID 177930, rodzic bieżącego Hermesa 177942;
brak drugiego implementatora. Odczytano cały ten dokument, AGENTS, plan,
architekturę i operacje. Hooks wyłącznie sample, core.hooksPath nieustawiony;
workflow feature uruchamia testy, publikacja nadal wyłącznie main. Upstream
push DISABLED. Pierwsza łączona komenda rozpoznania została zablokowana przed
wykonaniem przez unattended policy (Python -c); powtórzono bez tego fragmentu,
bez zmian ustawień lub obejścia ochrony.

Osobna read-only rola niezależna: scoped PASS na źródle
`f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`; HEAD różni się wyłącznie docs.
202 istniejące testy + 140 nowych probe cases, w tym rzeczywiste lokalne
odbiorniki HTTP trzech ścieżek modelu i obu transportów HS. Brak odtworzonej
blokującej luki; bez akceptacji prawdziwego OAuth/HS ACL/restart/container/CI.
Pełny raport i trzy syntetyczne probe pliki utrwalono w review-evidence jako
independent_final_*. Osobna rola implementacyjna zachowała je bez zmiany
zachowania (cmp i SHA256 potwierdzone przez prowadzącego) i wykonała dwa
przebiegi 140 PASS. To nie druga niezależna akceptacja. Obie role zakończone.
Manifest independent-review.json zawiera PASS tylko w zakresie offline review.

Prowadzący odczytał cały raport, guard, harness i wszystkie trzy probe pliki,
po czym sam uruchomił (repo cwd, poprzednio opisane env -i i guard):

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh coordinator-1239-full
node --check web/app.js
node --test tests/web_*.test.mjs
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh coordinator-1239-probes docs/review-evidence/privacy_boundary_probe.py docs/review-evidence/independent_final_adversarial.py docs/review-evidence/independent_final_flows.py docs/review-evidence/independent_final_wire.py -p no:cacheprovider
```

Wyniki: pełna regresja 404 passed / 1 skipped in 84.17s (exit 0); jedyny skip
test_imported_data: brak jawnie wybranego lokalnego importu. JS syntax OK,
frontend 21 passed / 0 failed. Probe 153 passed / 1 warning in 17.73s (exit 0):
historyczne 13 + niezależne 140. Warning LiteLLM dotyczy braku bieżącej event loop;
nie oznacza porażki asercji ani realnego wywołania providera. Lokalne oryginały
zachowane. Testy offline nie dowodzą poprawności integracji zewnętrznej.

Świeży odczyt dostępu 12:32 UTC: Docker nadal bez demona (mimo exit 0 klienta),
GitHub Actions API authenticated GET permissions enabled=true, workflows
total_count=0; runs dla feature puste. Nie ponawiano bezcelowo dispatch 404,
nie zmieniano main/ustawień GitHub ani nie tworzono wczesnego PR. Przyczyna
braku rejestracji workflow niepotwierdzona. Brak własnej sesji OAuth k90 oraz
izolowanego restartowalnego HS/ograniczonej tożsamości pozostaje zgodny z
udokumentowanym stanem; nie odczytywano tokenów ani istniejących banków.

Quota usage_api 12:21:42Z 49%/21%, 12:32:15Z 58%/22%, 12:42:59Z 62%/23%;
resety 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. Bez reset/fallback.
Pozostały konkretne bramki dostępu właściciela, nie rutynowy błąd implementacji.
Najpierw checkpoint dowodów i push, następnie końcowy stan BLOCKED_OWNER oraz
lista minimalnych zewnętrznych działań. Bez acceptance PASS/READY/PR.

## Końcowy checkpoint tej sesji — CONTINUE, 12:16 UTC

Najnowsze testowane źródła `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2` zawierają
poprawkę aplikacji 289d3ff i bezpieczny feature-only trigger testów CI. Push/SHA
obu source checkpointów potwierdzone ls-remote. Prowadzący na f39ad1f uruchomił:

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh source-f39ad1f-full
node --check web/app.js
node --test tests/web_*.test.mjs
git diff --check
```

Rzeczywisty wynik: exit 0, 404 passed / 1 skipped in 84.41s, jawny skip
test_imported_data (brak wybranego lokalnego importu); JS syntax OK, frontend
21 passed. Późniejsze zmiany tylko docs. Bez końcowej niezależnej akceptacji.
Read-only końcowy reviewer musi dostać ten source commit, nie tylko stare FAIL.
Obie delegowane role zakończone; trzecia została odrzucona przez limit sesji 2/2.
Następna sesja ma zacząć od tego review, wykorzystując pierwszy slot dziecka.

Trwałe bezpieczne dowody integracji: review-evidence/hindsight_live_probe.json
oraz review-evidence/integration_checkpoint_20261025.md (komendy, wyniki,
ograniczenia i wymagania właściciela). Powtórny API odczyt po feature push nadal
200 z pustymi workflow/runs, permissions enabled=true; brak CI/container PASS.
Nie zgadujemy przyczyny. HS adapter realnie częściowo sprawdzony; brak ACL
i restart-persistence. OAuth bez osobnego logowania właściciela niezweryfikowany.

Nie ustawiamy READY_FOR_REVIEW, nie tworzymy manifestów PASS/PR. CONTINUE wynika
z nieukończonego lokalnego niezależnego review; dopiero po jego zamknięciu ocenić
BLOCKED_OWNER dla rzeczywistego dostępu do OAuth/HS ACL+restart/CI+Docker.
Quota usage_api 12:11:00 UTC 44%/20%, 12:13:39 UTC 45%/20%,
12:16:30 UTC 47%/20%; resety 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z.
Bez reset/fallback. Końcowy push obejmuje wyłącznie jawnie przejrzane docs,
po skanie kandydatów i diff checks; exact final SHA przez HEAD i ls-remote.

## Dostępne integracje — real HS i uruchomienie feature CI

Źródła poprawki `289d3ffd918a066fdf9a8dc9d0cda24c8fd8d585` wypchnięte;
SHA origin potwierdzony przez ls-remote, checkout czysty. Przed push skan
12 jawnie wybranych kandydatów: zero trafień sekretów/znanych real PII/binariów
i baz/cache; odczyt diff i oba diff checks PASS. To ograniczony skan, nie gwarancja.

Trzecia delegacja (read-only final review) odrzucona: oneshot_max_children=2.
Obie wcześniejsze role zakończone. To bramka następnej sesji, nie zgoda security.
Nie obchodzono limitu instalacją CLI ani zmianami konfiguracji Hermesa.

GitHub API: GET actions/runs dla gałęzi i actions/workflows 200 z pustymi listami;
credential-helper/API fallback użyty bez drukowania tokenów. Dispatch docker.yml
na feature ref zwrócił 404. Diagnoza: actions/permissions 200 enabled=true,
workflows total_count=0; plik docker.yml istnieje na main. Zamiast zmiany main
lub wczesnego PR dodano dokładnie tę feature branch do triggera push testów.
Job build/publish nadal wymaga refs/heads/main; na tej gałęzi nie publikuje obrazu.
Nowy push ma dać rzeczywisty wynik testów i container smoke na zdalnym runnerze.

DNS hindsight oraz GET health/openapi: HTTP 200, healthy, API 1.1.0. Realny test
adaptera wykonano bez tokenów, wyłącznie w losowym nowym `k90-test-delivery-*`:
SQLite retry po symulowanej awarii przed siecią, nowy Worker, real retain i odczyt
zdalnego dokumentu (e-mail syntetyczny zredagowany), recall do lokalnych refs,
filtr owner tag, replay bez duplikatu (total=1), korekta z usunięciem rev1,
recall rev2 oraz rebuild do nowego pustego banku z lokalnych źródeł. Exit 0.
Cleanup DELETE banku 200 success=true, dokładny readback documents 404.
To nie dowód ACL (usługa przyjęła brak credentials) ani restartu wspólnej usługi.
Nie czytano/zmieniano żadnego istniejącego banku, w szczególności banku Hermesa.

Pierwszy harness miał błąd readback: deprecated /profile daje 410, a handler
błędu próbował czytać jeszcze nieutworzoną tabelę. Pierwszy pusty bank usunięto
osobnym kontrolowanym cleanup (200 success, potem 404); poprawiono tylko scratch
harness (readback documents i cleanup także po niepełnym create). Kolejny pełny
przebieg powyżej PASS częściowy, bez ukrywania pierwszego harness FAIL.
Scratch polecenia: hs_discover.py, hs_schema.py, hs_live.py i github_ci.py w
/opt/data/cache/scratch/k90-verification-20261025; trwały raport zostanie zapisany
w review-evidence. Środowisko real HS: env -i, PYTHONPATH wyłącznie repo,
PYTHON_DOTENV_DISABLED=1, osobny HOME/TMPDIR, syntetyczna nowa SQLite; offline
guard świadomie nieużyty tylko w tym jawnym teście sieciowym HS.

## Poprawki kompozycji i kluczy — 12:02 UTC, WIP

Implementator TDD naprawił trzy klasy i wspólne parsowanie argumentów narzędzi.
Dokładny ślad RED/GREEN oraz ograniczenia: `review-evidence/privacy_composition_fix.md`.
Prowadzący odczytał cały diff źródeł, testy i raport, ponowił offline regresję:
384 passed / 1 skipped in 88.06s; historyczny probe 13 passed in 1.49s;
JS syntax OK i 21 passed. Własny dodatkowy receiver-level RED ujawnił escaped
aliasy skalarnych nazw kluczy; 20 failed. Odrzucanie encoded reserved names
dało GREEN 140 passed, następnie pełna regresja 404 passed / 1 skipped in 105.83s.
Oba wykonania pełnej regresji używały odczytanego env -i/guard/run-fixes.sh,
wyłącznie syntetyków; brak realnych HS/OAuth/model calls. Nowe testy nie zależą
od scratch. Nie twierdzimy, że implementator jest niezależnym reviewerem poprawki.

Niezależny read-only adversarial review końcowych źródeł nadal potrzebny.
Docker ponownie: klient dostępny, daemon unix:///var/run/docker.sock niedostępny
(komunikat mimo exit 0); brak container PASS. CLI gh/codex nie znaleziono w PATH,
/opt/data/.local/bin/gh nie istnieje. Dalszy odczyt CI przez API dopuszczony.
Odczyt quota 11:56:14 UTC 29%/18%, 12:02:09 UTC 35%/19%; resety
2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. Bez reset/fallback.

## Wznowienie 11:33–11:41 UTC — niezależny review FAIL

Czysty checkout, HEAD i origin/feat/long-term-memory zgodne:
`86c88080594be42c982c6c8d6af8748c72d3cf69`. Brak zastanej pracy do ratowania.
Lock worker.lock trzyma nadzorca PID 167165, rodzic bieżącego procesu 167177;
nie wykryto drugiego implementatora. Odczytano cały ten dokument, plan,
architekturę, operacje i AGENTS.md. Hooks tylko sample, core.hooksPath brak;
workflow push feature nie uruchamia publikacji obrazu, upstream push DISABLED.

Osobno zadany read-only reviewer wykonał świeży adversarial review źródeł
6a3b306 (HEAD różni się tylko docs). Wynik: FAIL. Historyczny probe 13 passed;
ograniczona regresja 100 passed, ale nowa macierz 23 failed/60 passed i trzy
lokalne przepływy 3 failed. Wykryto: encoded JSON w kluczach pomija recursive
decode; duplikat local_only usuwa wcześniejsze true; summary skleja dokument
z prozą przed kontrolą źródła i traci rozpoznanie strukturalnej restrykcji.

Prowadzący odczytał oba nowe testy, raport i bezpieczny harness; wykonał:
`bash /opt/data/cache/scratch/k90-review-20261025-new/run-review.sh parent-flows /opt/data/cache/scratch/k90-review-20261025-new/test_flow_confirmations.py`
Wynik rzeczywisty: 3 failed in 3.16s; marker dociera do atrap retain/summary.
To syntetyczne lokalne SQLite i odbiorniki, bez real HS/modeli/poświadczeń.
Szczegółowy tymczasowy raport: scratch k90-review-20261025-new/REPORT.md;
nowe trwałe regresje i skrócony bezpieczny dowód muszą wejść z poprawką.
Nie uznawać review poprzedniej poprawki za PASS. Następny etap: implementator
TDD, wspólny ograniczony decode bez utraty par oraz kontrola źródeł przed kompozycją.

Quota usage_api 11:33:46 UTC 1%/13%, 11:41:05 UTC 7%/14% (Session/Weekly),
resety 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. Bez reset/fallback.
Real HS/OAuth/container/CI nadal pending. Checkpoint WIP, nie gotowość PR.

## Pauza quota przy wejściu — 08:21 UTC

`/opt/hermes/.venv/bin/hermes usage --json`: usage_api, fetched_at
`2026-10-25T08:21:43.825141+00:00`, Session 80%, Weekly 12%; resety
`2026-10-25T11:22:00+00:00` / `2026-11-01T06:22:00+00:00`.
Zgodnie z mandatem nie rozpoczęto review, implementacji ani regresji.
Nie uruchomiono dzieci, resetów, fallbacku ani nowych integracji.

`git status --short` pusty; gałąź feat/long-term-memory; HEAD i
`git ls-remote origin refs/heads/feat/long-term-memory` identyczne:
`c581ba17280c9cf7d802fbb2a504a5837729a259`. Nie było pracy do ratowania.
`lslocks` i `ps -o pid,ppid,args -p 155429,155445` potwierdziły, że lock
worker.lock trzyma proces nadzorcy będący rodzicem bieżącego Hermesa.
Przejrzano workflow: feature push nie publikuje obrazu; core.hooksPath
nieustawiony, w .git/hooks tylko 14 plików .sample. Upstream push DISABLED.
Checkpoint obejmuje wyłącznie STATUS.md i ten wpis, bez zmiany źródeł/testów.
Historyczne wyniki poniżej nie są świeżym dowodem tej sesji. Następne wznowienie
musi zacząć od quota <80% we wszystkich oknach i niezależnego review poprawki.

## Redesign granicy JSON — świeża regresja prowadzącego 08:17 UTC

Testowane źródła utrwalono w `6a3b3066653eb08dd519b46e69e0e1ecf33a6661`.
Push origin/feat/long-term-memory potwierdzony identycznym SHA przez ls-remote;
working tree czyste po tym push. Skan sześciu kandydatów i oba diff checks PASS.
Końcowy odczyt 08:18:27 UTC: Session 78%, Weekly 12%. Kolejny checkpoint zawiera
wyłącznie dokumentację, nie zmienia testowanych źródeł. Brak niezależnego review
nowej poprawki uniemożliwia READY; kontynuacja w świeżej sesji (limit delegacji).

Checkpoint zastanej pracy `a3d54da8c2d20173b1e2a2ae082195039e5e36fa` został
wypchnięty wyłącznie na origin/feat/long-term-memory i potwierdzony ls-remote.
Rola implementacyjna odtworzyła pierwotny RED (6 failed/7 passed), dopisała
20 receiver-level/budget/Markdown przypadków (RED 14 failed/6 passed), następnie
przeprojektowała kontrakt: pełny decode obiektów/tablic/stringów JSON ze wspólnym
budżetem; malformed object/string fail-closed; ograniczona gramatyka etykiet
Markdown zamiast rozpoznawania prefiksów błędnych kluczy. Szczegóły i ograniczenia:
`review-evidence/privacy_json_contract.md`. GREEN implementatora: 100 passed.

Prowadzący odczytał dokładny diff, nowe testy, helper i guard, następnie wykonał:

```sh
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh privacy-parent-full
bash /opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh privacy-parent-probe docs/review-evidence/privacy_boundary_probe.py
node --check web/app.js && node --test tests/web_*.test.mjs
```

Wyniki rzeczywiste: 298 passed / 1 skipped in 79.66s, exit 0; pierwotny probe
13 passed in 1.51s, exit 0; JS syntax OK, frontend 21 passed/0 failed, exit 0.
Skip nadal dotyczy niewybranego lokalnego importu; żadnych danych produkcyjnych.
Sanity: `git diff --check` exit 0. Szczegółowe logi pytest w scratch pod etykietami
powyżej; trwały skrócony wynik w `review-evidence/privacy_parent_regression.txt`.

Niezależny krytyczny przegląd NOWEJ poprawki nadal NIEZALICZONY: próba uruchomienia
osobnej roli została odrzucona przez runtime `delegation.oneshot_max_children=2`.
Pierwsze dwie role zakończone: read-only audyt checkpointu, implementator.
To ograniczenie tej sesji, nie bloker właściciela ani akceptacja bezpieczeństwa.
Następna sesja musi zacząć od niezależnego adversarial review, nie powtarzać
audytu starego checkpointu. Real HS/OAuth/container/CI nadal niepotwierdzone.

Quota 08:15:37 oraz 08:17:25 UTC: Session 77%, Weekly 12%; resety bez zmian.
Bez reset/fallback/zmian kont. Nie zaczynać szerokiej integracji blisko progu;
mały checkpoint WIP nie oznacza pełnego odbioru.

## Wznowienie 08:10 UTC — checkpoint WIP/BLOCKED

Nowy mandat autonomiczny zastępuje historyczne zakazy checkpoint commit/push
oraz limit dwóch cykli poprawek zapisane poniżej. Nie zastępuje bramek odbioru.
Przed pierwszym checkpointem read-only reviewer przejrzał wszystkie 51 plików
kandydatów (tracked i untracked); brak zidentyfikowanych rzeczywistych danych,
sekretów, baz i cache. Jedyny log to syntetyczny privacy probe FAIL, zachowany
świadomie jako dowód. Prowadzący wykonał dodatkowy skan binariów, private keys,
tokenów GitHub i długich kluczy API: 51 plików, zero trafień. To ograniczony skan,
nie gwarancja braku dowolnego sekretu. Oba `git diff --check` przeszły.

Prowadzący odczytał workflow `.github/workflows/docker.yml`: push do
`feat/long-term-memory` nie uruchamia publikacji (push: main/codex/**).
Brak aktywnych hooks i core.hooksPath. Upstream push DISABLED; lokalny tracking
wskazuje upstream/main, dlatego wszystkie pushe wymagają jawnego origin/refspec.
Lock nadzorcy potwierdzony przez lslocks (proces nadrzędny tej sesji).
Nie uruchomiono świeżej regresji; znane privacy FAIL nadal blokuje odbiór.

Quota 08:06:28 UTC: Session 64%, Weekly 10%; 08:10:26 UTC: 72%/11%.
Resety: 2026-10-25T11:22:00Z i 2026-11-01T06:22:00Z.
Następny krok: receiver-level RED i ograniczony redesign klasyfikacji JSON,
bez kolejnych wyjątków regex; zachować zwykły Markdown.

## Końcowa bramka review: FAIL — eskalacja po dwóch cyklach poprawek

Końcowy niezależny reviewer odtworzył nadal otwartą lukę wyjścia
`k90_memory/privacy.py:86-98`: uszkodzony JSON z prefiksem `{broken,` albo
`{/*comment*/` i escapowanym kluczem `api\\u005fkey`, a także JSON zakodowany
jako string, przepuszcza syntetyczny sekret do obu atrap transportu modelu.
Niezależna próba: **6 failed, 7 passed**. To blokuje zatwierdzenie mimo zielonej
regresji repozytorium. Dowody zachowano poza prunowanym scratch:
`docs/review-evidence/privacy_boundary_probe.py` oraz
`docs/review-evidence/privacy_boundary_probe.log` (wyłącznie syntetyki).

Po dwóch automatycznych cyklach poprawek nie uruchomiono trzeciego.
Następny proponowany krok: osobne zadanie uporządkowania kontraktu filtra,
konserwatywna odmowa malformed object-like input i ograniczona inspekcja
JSON-string encodings, z receiver-level regresjami i zachowaniem Markdown.
Nie uznawać zmian za gotowe, nie scalać ani wdrażać.

Prowadzący ponownie wykonał pełną izolowaną regresję z polecenia fazy 3,
z `--basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-parent-final`
i logiem `pytest-parent-final.log`: **278 passed, 1 skipped in 93.52s**.
Końcowy reviewer niezależnie: **278 passed, 1 skipped in 93.89s**,
frontend **21 passed**. Zielona regresja nie obejmuje sześciu nowych przypadków
z dowodu. Pozostałe wcześniejsze blokery przeszły niezależne próby.
Rzeczywiste HS/OAuth, kontener i CI nadal niepotwierdzone.
Ostatnia quota wg review: Session 48%, Weekly 7%; pauza jest skutkiem
nieudanej bramki review, nie osiągnięcia progu quota.


## Status

**Nieukończony odbiór; bez commita/pusha/scalenia/wdrożenia.**
Repo: `/opt/data/projects/k90`, gałąź `feat/long-term-memory`.
Zastany staged/unstaged kod zachowany, bez reset/stash. Origin to fork
`hermesinski/k90`; upstream push `DISABLED`.

## Faza 1: odzyskanie i regresja offline — wykonane

- Odczytano `AGENTS.md`, `docs/IMPLEMENTATION_PLAN.md`,
  `docs/OPERATIONS_MEMORY_AUTH.md`.
- `.venv/bin/python --version`: Python 3.13.5;
  `.venv/bin/python -m pytest --version`: pytest 9.1.1.
  Istniejący `.venv` działa; niczego nie instalowano.
- `node --version`: v26.12.1.
- `git diff --cached --binary | sha256sum` przed/po fazie:
  `2ab9898846d4f87152fdd6e2eadc3f7693550e9ef6e96d7a368bf9d367490d21`.
  Indeks nietknięty.

Testy nie czytają `.env` ani produkcyjnych danych/tokenów. Uruchomienie z `env -i`,
syntetyczny DB/DATA_DIR/HOME/OAuth, `PYTHON_DOTENV_DISABLED=1`, lokalny backend HS.
Dodatkowy scratch `sitecustomize.py` blokuje sieć poza loopback, `.env` poza
syntetycznym fixture, bezwzględne ścieżki repo `data/` i profile/pamięci Hermesa.
To dodatkowy guard testowy, nie systemowy sandbox ani dowód pełnej izolacji.

Pierwsza próba (`pytest-initial.log`) zakończyła się błędem teardown guardu
(`open` z relatywnym `dir_fd` błędnie uznany za repo `data/`). Poprawiono tylko
scratch guard. Kolejna (`pytest-baseline.log`): **7 failed, 243 passed, 1 skipped**,
73.43 s. Wszystkie 7 wynikały z harnessu: globalne `BACKUP_DIR`, wyłączony sync
nadpisujący testy atrap oraz blokada tworzenia fikcyjnego `.env` w fixture.
Usunięto te konflikty, zachowując blokadę sieci i rzeczywistego `.env`.
Nie modyfikowano kodu aplikacji, aby obejść te błędy.

Dokładne poprawne polecenie (bash, katalog repo):

```sh
set -o pipefail; env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHON_DOTENV_DISABLED=1 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest -q --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-clean 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/pytest-clean.log
```

Wynik: **250 passed, 1 skipped in 73.07s** (exit 0). Skip dotyczy
`tests/test_imported_data.py` bez jawnego `K90_TEST_IMPORT`; nie wybrano produkcji.

```sh
set -o pipefail; node --check web/app.js && node --test tests/web_*.test.mjs 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/node.log
```

Wynik: składnia OK, **21 pass, 0 fail**, exit 0.

## Quota i zasada wznowienia

`/opt/hermes/.venv/bin/hermes usage --json` wykonano o 06:26:29 i 06:29:42 UTC:
Session 5%, reset `2026-10-25T11:22:00+00:00`; Weekly 1%, reset
`2026-11-01T06:22:00+00:00`. Bez zmiany providera/fallbacku/banked reset.
Politykę >=80/90%, unknown i checkpointów dopisano do organizacji
`docs/IMPLEMENTATION_PLAN.md`. Kontrolować przed większym etapem i po długiej partii.

## Faza 2: lokalny odbiór przekrojowy — wykonane

Dodano `tests/test_memory_acceptance.py` (wyłącznie syntetyki):

- FastAPI TestClient, autoryzacja, seed demo, panel/dokument, rzeczywisty wątek
  `ConversationWorker` w trybie preview, HTTP enqueue, zakończenie zadania,
  idempotentne ponowienie i para historii, local recall z separacją właściciela,
  restart lifespan bez powtórzenia zadania i potwierdzenie zatrzymania wątków.
  To HTTP in-process, nie test przeglądarki ani zewnętrznego modelu.
- Prawdziwy backup API SQLite i restore do nowego katalogu bez Markdown:
  osiem tabel (dokumenty/rewizje/events/sources/versions/outbox/settings/FTS)
  identycznych po restore, `integrity_check=ok`, klucz HMAC zachowany po
  ponownej inicjalizacji; rebuild odtwarza sześć dokumentów indeksu o dokładnie
  tych samych identyfikatorach i filtrowanej treści. Zewnętrzny indeks jest atrapą.

Polecenia używały dokładnie prefixu `env -i ... .venv/bin/python` z fazy 1:

```sh
# po prefixie: pierwsza próba miała błędny, zbędny import w nowym teście
-m pytest tests/test_memory_acceptance.py -q --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-acceptance
# wynik: collection error ImportError: pseudonym; usunięto zbędny import
-m pytest tests/test_memory_acceptance.py -q --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-acceptance2
# wynik: 1 failed, 1 passed (5.08 s), błędne oczekiwanie testu wobec istniejącego JSON historii
-m pytest tests/test_memory_acceptance.py -q --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-acceptance3
# wynik: 2 passed (5.26 s), exit 0
```

Nie wykryto błędu aplikacji wymagającego poprawki; powyższe poprawki dotyczą
wyłącznie nowych testów, nie są deklarowane jako RED/GREEN kodu produkcyjnego.
Po zielonym przebiegu dodano jawne asercje `job is not None`; wymagają finalnej regresji.
`git diff --check` i `git diff --cached --check`: exit 0, bez wyjścia.
SHA-256 indeksu nadal identyczny z fazą 1.
Quota 06:30:45 UTC: Session 7%, Weekly 1%; 06:32:56 UTC: Session 9%, Weekly 1%.
Reset timestamps bez zmiany. `command -v docker`: `/usr/bin/docker`;
sama obecność klienta nie dowodzi dostępnego demona.

## Faza 3: finalna regresja i realny localhost — wykonane

Trzeci test w `tests/test_memory_acceptance.py` potwierdza, że fakty wyparte
z krótkiej historii (`HISTORY_MESSAGES=1`) docierają przez recall do odbiornika
modelu wraz z datą/źródłem/rewizją, z redakcją e-maila i bez danych innego
właściciela. Oryginalna historia lokalna pozostaje niezmieniona.
Model jest atrapą; nie stanowi to testu sieci providera.

Dokładne końcowe polecenie:

```sh
set -o pipefail; env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHON_DOTENV_DISABLED=1 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest -q -rs --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-final 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/pytest-final.log
```

**253 passed, 1 skipped in 76.15s**, exit 0. Jedyny skip:
`tests/test_imported_data.py:17: No local import selected`.
Ta regresja obejmuje wszystkie trzy nowe testy odbioru i finalne asercje.
Frontend bez zmian od przejścia 21 testów w fazie 1.

Dodatkowo wykonano prawdziwy serwer Uvicorn na losowym porcie `127.0.0.1`
z syntetycznym seedem, własną pustą bazą i filtrem sieci (bez `dev.py`, bo
nie uruchamiamy jego wczytywania `.env`). Polecenie:

```sh
set -o pipefail; env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHON_DOTENV_DISABLED=1 K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python /opt/data/cache/scratch/k90-verification-20261025/tcp_demo.py 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/tcp-demo.log
```

Wynik smoke (exit 0): `/healthz`, HTML `/`, login, dashboard i dokument **200**;
enqueue **202**; historia **2** wiersze, po ponowieniu nadal **2**; recall **1**
źródło. Model niewywołany (preview). Proces Uvicorn zakończono SIGTERM i odebrano
`wait()` (`returncode=-15`); log potwierdza `Application shutdown complete` oraz
`Finished server process`. Brak pozostawionego procesu tego smoke.
Nie wykonywano wizualnego testu przeglądarki.

Docker sprawdzono bez konfiguracji/prawdziwych credentials:

```sh
env -i PATH=/usr/bin:/bin HOME=/opt/data/cache/scratch/k90-verification-20261025/home DOCKER_CONFIG=/opt/data/cache/scratch/k90-verification-20261025/docker docker info --format '{{.ServerVersion}}'
```

Wynik: `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`.
Klient zwrócił 0 mimo tego komunikatu; to **blokada build/smoke kontenera**, nie PASS.
Nie uruchamiano demona i nie zmieniano ustawień hosta.

Finalne `git diff --check` / `git diff --cached --check`: exit 0.
SHA-256 staged diff pozostaje
`2ab9898846d4f87152fdd6e2eadc3f7693550e9ef6e96d7a368bf9d367490d21`.
Quota przed etapem (06:34:18 UTC) i po nim (06:36:02 UTC): Session **10%**,
Weekly **2%**, reset odpowiednio `2026-10-25T11:22:00+00:00` i
`2026-11-01T06:22:00+00:00`. Nie ma powodu zatrzymania z powodu quota.

## Niezależne powtórzenie przez prowadzącego

Prowadzący odczytał scratch guard i ponownie wykonał polecenie fazy 3,
zmieniając wyłącznie `--basetemp` na
`/opt/data/cache/scratch/k90-verification-20261025/pytest-parent` i log na
`/opt/data/cache/scratch/k90-verification-20261025/pytest-parent.log`.
Wynik: **253 passed, 1 skipped in 75.17s**, ten sam jawny skip importu.
Ponownie `node --check web/app.js` oraz `node --test tests/web_*.test.mjs`:
**21 pass, 0 fail**, składnia OK. Osobny read-only reviewer został uruchomiony;
jego werdykt pozostaje bramką przed commitem.

## Bramki jeszcze niewykonane
- Real HS `k90-test-*`, persistence po restarcie usługi, granica autoryzacji banków:
  brak osobnej bezpiecznej konfiguracji testowej; nie używać produkcyjnego tokenu.
- Real OAuth/refresh/katalog/streaming: wymaga odrębnej zgody i sesji testowej
  właściciela. Atrapy nie potwierdzają rzeczywistej integracji ani rozliczeń.
- Niezależny krytyczny reviewer, ponowna regresja przez prowadzącego,
  kontener/build, PR i odczyt CI. Bez commita/pusha do czasu review.

## Następny bezpieczny krok

**Gotowe do osobnego, niezależnego krytycznego review**, nie do merge/deploy.
Przekazać reviewerowi istniejący staged/unstaged diff oraz wszystkie untracked
moduły/testy; samo `git diff` nie obejmuje untracked. Review priorytetowo:
prywatność na każdej granicy wyjścia, OAuth refresh/import uprawnienia i brak
płatnego fallbacku, wyścigi lease/retry, dokumenty+outbox w jednej transakcji.
Nie uruchamiano kolejnego agenta ani nie dodawano zadań równoległych.

Przed dalszą większą pracą: `/opt/hermes/.venv/bin/hermes usage --json`.
Prowadzący może niezależnie powtórzyć finalne polecenie pytest z fazy 3 oraz
`node --check web/app.js` i `node --test tests/web_*.test.mjs`.
Najpierw potwierdzić obecność scratch guardu; po pruning odtworzyć go z aneksu
poniżej, a nie uruchamiać testów z odziedziczonym środowiskiem produkcji.
Testy przekrojowe są trwale w repo; jednorazowy TCP smoke jest w scratch.
Bez dostępnego demona Docker nie raportować obrazu jako zweryfikowanego.
Prawdziwe HS i OAuth odłożyć do bezpiecznie wyodrębnionego środowiska właściciela.
Po review i ewentualnych poprawkach TDD ponowić pełną regresję; commit/PR dopiero
po akceptacji. Bez pusha do upstreamu, merge ani deploy.

## Pliki tej kontynuacji

- Zmieniono `docs/IMPLEMENTATION_PLAN.md` (polityka quota).
- Dodano `docs/VERIFICATION.md` (ten checkpoint).
- Dodano `tests/test_memory_acceptance.py` (3 testy syntetyczne).
- Nie zmieniono zastanego kodu produkcyjnego ani indeksu Git.
- Scratch poza repo: guard, smoke, syntetyczne dane i logi w
  `/opt/data/cache/scratch/k90-verification-20261025/`.

## Aneks: odtworzenie testowego guardu po pruning scratch

Poniższa treść odpowiada wykonanemu scratch `sitecustomize.py` (pominąć można
nieużywane importy, ale nie reguły). Odtworzyć plik przez narzędzie zapisu plików,
utworzyć puste `home/` i `data/` pod tym samym scratch root, następnie użyć
pełnego polecenia `env -i` z fazy 3. Nie kopiować danych produkcyjnych.
Guard nie jest sandboxem systemowym; względne `open` z `dir_fd` mogą być niejednoznaczne.

```python
import ipaddress
import os
import sys
from pathlib import Path
ROOT = Path('/opt/data/projects/k90')
SAFE = Path('/opt/data/cache/scratch/k90-verification-20261025')
def audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        address = args[1] if event == 'socket.connect' else args[0]
        host = address[0] if isinstance(address, tuple) else address
        if host in {'localhost', None}:
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (ValueError, TypeError):
            pass
        raise RuntimeError('Offline verification blocked non-loopback network')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).absolute()
        if ('.env' in path.parts or path.name.startswith('.env.')) and SAFE not in path.parents:
            raise RuntimeError('Offline verification blocked .env read')
        if os.path.isabs(args[0]) and (path == ROOT / 'data' or ROOT / 'data' in path.parents):
            raise RuntimeError('Offline verification blocked repository data access')
        if '/opt/data/profiles/' in str(path) or '/opt/data/memories/' in str(path):
            raise RuntimeError('Offline verification blocked profile access')
sys.addaudithook(audit)
```

## Faza 4: pięć blokujących ustaleń review — poprawki TDD 2026-10-25

**Poprawki gotowe do drugiego niezależnego review, nie do pełnego odbioru.**
Zakres wyłącznie pięciu odtworzonych ustaleń. Bez commita, stagingu, pusha,
reset/stash, instalacji, wdrożenia ani dostępu do produkcyjnych danych/tokenów.
Nie zmieniano pozostałej zastanej pracy ani konfiguracji Hermesa.

### Zmiany

- `responses_api.py`, `subscription_api.py`: polityka sprawdza oryginalne
  wiadomości przed stratną normalizacją multipart. Istniejący filtr końcowego
  payloadu nadal działa przed transportem, w subskrypcji także przed tokenem/katalogiem.
- `memory_runtime.py`: strukturalne `local_only` przechodzi do `Source.local_only`
  przed ekstrakcją tekstu; bez zmiany oryginału w `agent_events`. Bezpośredni
  restricted multipart query nie dochodzi do recall backendu. Worker i kontekst
  modelu nadal blokują takie źródła.
- `k90_memory/privacy.py`: liczby JSON podlegają tym samym regułom identyfikatorów
  co tekst (także zagnieżdżenia i HS retain); zwykłe pomiary zachowują typ i wartość.
  Zwykły Markdown/proza zaczynające się nawiasem nie są wymaganym JSON-em.
  Poprawny JSON nadal jest parsowany rekurencyjnie; pola `arguments` wymagają
  poprawnego JSON-u i pozostają fail-closed dla błędnej składni/sekretów.
- `subscription_auth.py`: po udanym refresh z nowym ID tokenem kandydat jest
  zapisywany atomowo jako `pending_refresh` w prywatnym `credentials.json`
  **przed JWKS I/O**. Restart ponawia walidację podpisu/identity kandydata,
  nie stary refresh. Kandydat nigdy nie daje dostępu do inference przed walidacją;
  odrzucona identity pozostaje zablokowana. Logout odwołuje najnowszy rotowany token.
  Zachowane istniejące lock, atomic replace/fsync, 0700/0600 i ochrona symlinków.
- Nowy `tests/test_review_blockers.py`: pięć testów, dziewięć przypadków po
  parametryzacji; wyłącznie syntetyki, transporty modelu/JWKS są atrapami.
- Ten checkpoint. Nie poprawiano opcjonalnego README ani idempotencji `run_agent`.

### Ścisłe RED → minimalna poprawka → GREEN

Wszystkie polecenia z katalogu repo. Scratch helper
`/opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh` uruchamia
identyczne `env -i`/guard/zmienne z fazy 3, przyjmuje etykietę logu i argumenty
pytest; dodaje `-q -rs --tb=short` oraz osobny `--basetemp=.../pytest-<etykieta>`.
Logi `<etykieta>.log` w tym samym scratch root. Każdy RED wykonano przed
jakąkolwiek zmianą kodu produkcyjnego dla danego ustalenia, następnie GREEN
przed rozpoczęciem następnego ustalenia.

Dokładne polecenia:

```sh
R=/opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh
bash "$R" fix1-red tests/test_review_blockers.py
bash "$R" fix1-green tests/test_review_blockers.py tests/test_responses_api.py tests/test_subscription_api.py
bash "$R" fix2-red tests/test_review_blockers.py -k multipart_local_only
bash "$R" fix2-green tests/test_review_blockers.py tests/test_app_memory.py tests/test_memory_worker.py
bash "$R" fix3-red tests/test_review_blockers.py -k numeric
bash "$R" fix3-green tests/test_review_blockers.py tests/test_memory_privacy.py tests/test_memory_backend.py
bash "$R" fix4-red tests/test_review_blockers.py -k markdown
bash "$R" fix4-green tests/test_review_blockers.py tests/test_memory_privacy.py tests/test_outbound_policy.py tests/test_responses_api.py tests/test_subscription_api.py
bash "$R" fix5-red tests/test_review_blockers.py -k rotated_refresh
bash "$R" fix5-green tests/test_review_blockers.py tests/test_subscription_auth.py tests/test_subscription_login.py tests/test_subscription_protocol.py tests/test_subscription_api.py
```

| Ustalenie / test | RED (exit 1) | GREEN (exit 0) |
| --- | --- | --- |
| 1 `test_multipart_restrictions_survive_normalization` | 2 failed, 2 passed, 0.71 s; oba adaptery osiągały zabroniony transport po utracie metadanych | 29 passed, 8.06 s |
| 2 `test_multipart_local_only_stays_local_in_worker_and_recall` | 1 failed, 4 deselected, 0.54 s; `Source.local_only=False` | 22 passed, 6.34 s |
| 3 `test_numeric_identifiers_are_redacted_in_nested_payloads_and_hs_retain` | 1 failed, 5 deselected, 0.07 s; numeryczny PESEL bez redakcji | 30 passed, 1.15 s |
| 4 `test_markdown_answer_does_not_poison_next_turn_and_arguments_fail_closed` | 1 failed, 6 deselected, 3.36 s; `PrivacyError` przed drugim wywołaniem modelu | 49 passed, 9.14 s |
| 5 `test_rotated_refresh_survives_jwks_outage_without_unverified_inference` | 2 failed, 7 deselected, 0.94 s; brak utrwalonego `pending_refresh` po awarii JWKS | 33 passed, 5.03 s |

Test 5 używa prawdziwych syntetycznych podpisów RSA/JWT; pokrywa nowy obiekt
TokenStore po awarii, skuteczne wznowienie oraz błędny subject, zakaz inference
w stanie pending, brak ponownego użycia starego refresh, odmowę pliku 0644,
uprawnienia 0700/0600 i logout z najnowszym refresh. Nie testuje prawdziwego OAuth.

### Pełna regresja po wszystkich poprawkach

Dokładne polecenie użyte przez `bash "$R" fixes-full` (niezależne od zachowania helpera):

```sh
set -o pipefail; env -i PATH="$PWD/.venv/bin:/usr/bin:/bin" HOME=/opt/data/cache/scratch/k90-verification-20261025/home TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PYTHON_DOTENV_DISABLED=1 DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/auth K90_MEMORY_BACKEND=local TELEGRAM_ENABLED=false LITELLM_LOCAL_MODEL_COST_MAP=True .venv/bin/python -m pytest -q -rs --tb=short --basetemp=/opt/data/cache/scratch/k90-verification-20261025/pytest-fixes-full 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/fixes-full.log
```

**262 passed, 1 skipped in 76.88s**, exit 0. Jedyny skip nadal
`tests/test_imported_data.py:17: No local import selected`.
Guard odczytano przed testami; produkcyjne dane i sieć poza loopback niedostępne
w tym harnessie. Jest to guard aplikacyjny, nie systemowy sandbox.

```sh
set -o pipefail; node --check web/app.js && node --test tests/web_*.test.mjs 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/fixes-node.log
git diff --check
git diff --cached --check
git diff --cached --binary | sha256sum
```

Składnia JS OK, **21 pass, 0 fail**, exit 0. Oba diff checks: exit 0.
SHA-256 indeksu przed/po poprawkach nadal
`2ab9898846d4f87152fdd6e2eadc3f7693550e9ef6e96d7a368bf9d367490d21`.

Quota (`hermes usage --json`): 06:45:32 UTC **21%/3%**, 06:47:39 **23%/4%**,
06:49:32 **25%/4%**, 06:51:32 przed pełną regresją **26%/4%**,
06:53:40 po regresji **27%/4%** (Session/Weekly). Resety bez zmian:
`2026-10-25T11:22:00+00:00` / `2026-11-01T06:22:00+00:00`.
Bez banked reset, zmiany konta/providera ani płatnego fallbacku.

### Wymagane kolejne bramki

1. **Drugie niezależne krytyczne review tych pięciu poprawek**, obejmujące
   untracked moduły i nowy test; nie traktować niniejszej regresji jako werdyktu review.
2. Ponowna pełna regresja przez prowadzącego po review; bez commita/pusha przed zgodą.
3. Nadal niewykonane: real HS `k90-test-*` i autoryzacja/persistence po restarcie,
   real OAuth/refresh/katalog/streaming w osobnej sesji testowej właściciela,
   Docker build/smoke (wcześniej niedostępny daemon), PR/CI. Nie dotykano produkcji.

**Nie deklarujemy pełnej akceptacji ani gotowości do merge/deploy.**

## Faza 5: drugi i ostatni automatyczny cykl poprawek — 2026-10-25

**Cztery ustalenia poprawione; wymagane finalne niezależne review.**
Repo `/opt/data/projects/k90`, gałąź `feat/long-term-memory`. Zachowano całą
zastaną pracę staged/unstaged/untracked. Bez commita, stage, stash/reset, pusha,
wdrożenia ani instalacji. Nie otwierano produkcyjnej bazy/dokumentów, `.env`,
tokenów aplikacji, poświadczeń Hermesa ani banku `hermes-default`.

### Zakres zmian

- `memory_admin.py`: backfill sprawdza oryginalną strukturę JSON przed spłaszczeniem
  multipart i przekazuje `local_only` do źródła. Idempotencja uwzględnia restrykcję,
  więc ponowny import naprawia wcześniej utworzone nieograniczone źródło o tej samej
  treści, zamiast je pominąć. Worker blokuje retain, recall nie zwraca treści.
- `k90_memory/privacy.py`: niepoprawne/truncated JSON-looking obiekty/tablice oraz
  JSON z trailing text są fail-closed, także przy escaped secret keys. Zwykły
  Markdown `[Plan](https://example.invalid)` nadal przechodzi; `arguments` nadal
  wymaga poprawnego JSON-u. Numery w semantycznych polach identyfikatorów
  (`pesel`, warianty phone/national-ID/SSN) są redagowane niezależnie od długości,
  również wewnątrz zakodowanego JSON-u; zwykłe pomiary zachowują wartość i typ.
- `memory_runtime.py`: `_local_only` rekurencyjnie sprawdza indywidualnie parsowalne
  ciągi JSON przed sklejeniem tekstów multipart. Flaga w pierwszym lub drugim
  fragmencie pozostaje na `Source`; retain i bezpośredni recall nie osiągają backendu.
- `subscription_auth.py`: kandydat refresh jest utrwalany przed kontrolą scope
  oraz ID tokenu. Logout pobiera najnowszy strukturalnie poprawny refresh token
  niezależnie od uprawnień kandydata/poprawności ID tokenu; używa zaufanego
  `client_id` starej sesji. Pending nadal wymaga autoryzacji/weryfikacji przed
  inference, restart nie ponawia zużytego refresh tokenu. Zachowano lock i atomic
  private storage. Brak nowego ID tokenu nie jest traktowany jako nowa tożsamość.
- Dodano `tests/test_review_final_cycle.py`: **16 przypadków**, wyłącznie syntetyki.
  Używa prawdziwego lokalnego SQLite/Worker/TokenStore, atrap tylko granic
  zewnętrznych. Nie zmieniano pozostałych modułów ani wcześniejszych testów.

### RED → GREEN

Odczytano istniejący scratch guard i `run-fixes.sh` przed uruchomieniem.
Wszystkie polecenia używały sanitizowanego `env -i`, blokady zewnętrznej sieci
oraz syntetycznych DB/DATA_DIR/HOME/auth z fazy 4; helper zapisuje osobny log i
`--basetemp`. Guard jest defense-in-depth, nie systemowym sandboxem.
Każdy RED poprzedza zmianę kodu dla danego zachowania; GREEN poprzedza następny
slice. Dokładne polecenia, z katalogu repo:

```sh
R=/opt/data/cache/scratch/k90-verification-20261025/run-fixes.sh
bash "$R" final1-red tests/test_review_final_cycle.py
bash "$R" final1-green tests/test_review_final_cycle.py tests/test_admin_memory.py tests/test_memory_worker.py
bash "$R" final2a-red tests/test_review_final_cycle.py -k malformed_structured
bash "$R" final2a-green tests/test_review_final_cycle.py tests/test_review_blockers.py tests/test_memory_privacy.py tests/test_responses_api.py tests/test_subscription_api.py
bash "$R" final2b-red tests/test_review_final_cycle.py -k individually_encoded
bash "$R" final2b-green tests/test_review_final_cycle.py tests/test_review_blockers.py tests/test_app_memory.py tests/test_memory_worker.py
bash "$R" final3-red tests/test_review_final_cycle.py -k semantic_numeric
bash "$R" final3-green tests/test_review_final_cycle.py tests/test_review_blockers.py tests/test_memory_privacy.py tests/test_memory_backend.py
bash "$R" final4-red tests/test_review_final_cycle.py -k rejected_refresh
bash "$R" final4-green tests/test_review_final_cycle.py tests/test_review_blockers.py tests/test_subscription_auth.py tests/test_subscription_login.py tests/test_subscription_protocol.py tests/test_subscription_api.py
```

| Ustalenie / slice | RED (exit 1) | GREEN (exit 0) |
| --- | --- | --- |
| 1 backfill + naprawa starego źródła | 2 failed, 1.06 s; `local_only=False` | 14 passed, 7.59 s |
| 2a malformed/escaped/trailing JSON w obu transportach | 6 failed, 2 deselected, 0.75 s; osiągnięto zabroniony transport | 56 passed, 10.63 s |
| 2b indywidualne JSON local-only przed sklejeniem | 2 failed, 8 deselected, 0.93 s; `Source.local_only=False` | 36 passed, 10.70 s |
| 3 semantyczny numeric PESEL bez zer wiodących | 2 failed, 10 deselected, 0.08 s; `10112348` bez redakcji | 45 passed, 6.00 s |
| 4 odrzucony refresh, restart i logout | 3 failed, 1 passed, 12 deselected, 0.86 s; brak pending dla narrowed scope, brak revocation dla pustego/None ID tokenu | 49 passed, 7.07 s |

Ważne doprecyzowanie reprodukcji ustalenia 4: literalny syntetyczny `id_token='***'`
**już przechodził** test logout przed tą poprawką (jeden PASS w RED). Odtworzono
problem dla `id_token=''` i `None` oraz narrowed scope. Wszystkie cztery warianty
pozostają w regresji, bez twierdzenia, że `***` był nowo naprawionym przypadkiem.
Po GREEN zaostrzono asercje backfill o obecność źródła i status outbox `blocked`
oraz uzupełniono atrapę backendu o delete/recall; nie zmieniono kodu produkcyjnego.

### Pełna regresja syntetyczna i zachowanie indeksu

```sh
bash "$R" final-cycle-full
# 278 passed, 1 skipped in 75.62s, exit 0
bash "$R" final-cycle-confirm
# 278 passed, 1 skipped in 79.36s, exit 0 (po finalnych asercjach testów)
set -o pipefail; node --check web/app.js && node --test tests/web_*.test.mjs 2>&1 | tee /opt/data/cache/scratch/k90-verification-20261025/final-cycle-node.log
# składnia OK; 21 pass, 0 fail; exit 0
```

Jedyny skip nadal `tests/test_imported_data.py:17: No local import selected`;
nie wybierano rzeczywistych danych. Pełny prefix `env -i` helpera jest identyczny
jak w fazie 4; logi i basetemp dla powyższych etykiet są w tym samym scratch root.
`git diff --check` i `git diff --cached --check`: exit 0. SHA-256 staged diff
przed/po nadal `2ab9898846d4f87152fdd6e2eadc3f7693550e9ef6e96d7a368bf9d367490d21`.

Quota (`hermes usage --json`, Session/Weekly): 07:00:58 UTC **34%/5%**,
07:03:53 **40%/6%**, 07:04:42 **41%/6%**, 07:06:37 przed pełną regresją
**42%/7%**, 07:08:51 po pierwszej pełnej regresji **42%/7%**;
07:12:07 po potwierdzonej regresji i `--collect-only` (**16 tests collected**,
exit 0) **44%/7%**.
Resety bez zmian: `2026-10-25T11:22:00+00:00` /
`2026-11-01T06:22:00+00:00`. Bez resetu bankowanego, zmiany providera lub
płatnego fallbacku.

### Następna bramka — bez kolejnej automatycznej pętli

1. **Finalne niezależne krytyczne review czterech poprawek** (uwzględnić wszystkie
   untracked moduły i testy, nie samo `git diff`), następnie niezależna regresja
   prowadzącego. Ten checkpoint nie zastępuje werdyktu review.
2. Nadal pending: real HS w odrębnym `k90-test-*` (restart/persistence/autoryzacja),
   real OAuth/refresh/katalog/streaming w osobnej sesji testowej właściciela,
   Docker build/smoke (brak demona w poprzednim sprawdzeniu), PR/CI.
3. Bez commita/stage/pusha/deploy. To ostatni automatyczny fix cycle; dalsze
   odtworzone blokery wymagają checkpointu i decyzji prowadzącego/użytkownika,
   nie kolejnych automatycznych cykli.

# Partia historii zdjęć 2026-10-25 — implementacja do niezależnego review

Dowody RED/GREEN, dokładne polecenia i ograniczenia:
[photo-history-implementation.md](review-evidence/photo-history-implementation.md).
Nie jest to niezależny przegląd ani końcowy odbiór; pełne suite i PR prowadzi
koordynator. Baza zawiera zachowaną poprawkę host ID `9e02ab0`.

## Korekta photo-history R1 — 2026-10-25 23:22 UTC

Worktree `/opt/data/projects/k90-photo-history`, branch `fix/meal-photo-history`.
Po niezależnym FAIL źródła `1b031e8653b43cdecde444d716fac5ec751385ae`
zaostrzono schemat historycznych części w `outbound_policy.py`; dodano 15 regresji
rzeczywistego agenta w `tests/test_photo_history.py`. RED 14 failed/1 passed;
sekwencyjny targeted GREEN 178 passed (32.54s), exit 0. Niezmienione probe'y
recenzenta: 4 passed/1 failed, ponieważ ostatni nie obsługuje oczekiwanego teraz
PrivacyError przed providerem. To nie jest niezależny PASS.
Dokładne polecenia, oryginalny FAIL, logi i omyłkowy przebieg z konfliktem basetemp:
`review-evidence/photo-history-r1-correction.md` oraz powiązane artefakty.
Quota końcowa 88% session/48% weekly, bez resetów/fallbacku. Kolejne kroki:
koordynator sprawdza quota, pełną regresję i świeży niezależny review immutable
commita korekty. Brak push/PR, produkcji i testów live; kontroler bez zmian.
