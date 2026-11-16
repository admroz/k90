# Katalog i sesja — implementacja autora 2026-11-16

Implementacja do niezależnego odbioru. Gałąź `fix/catalog-source-session-20261030`,
baza `74ca891`, sesje 7 dni w poprzednim commicie `d3d7d0c`.
Wyniki końcowe i pozostałe bramki są w sekcji poniżej; wcześniejszy checkpoint
zachowano jako historię RED i projektu, a nie bieżący opis braków implementacji.

## Zaimplementowane zachowanie

- Lokalny resolver wiąże `own_label` z aktualnymi zdjęciami albo jednoznacznym
  świeżym albumem właściciela i zapisanym odczytem nazwy/kodu, także Telegram→WWW.
  Nie zmienia provenance na manual. Nie wysyła historycznych obrazów do modelu.
  Stale/foreign/local-only/deleted/ambiguous/unrelated wymagają wyjaśnienia.
- Naturalna zgoda, korekta i rezygnacja przechodzą przez model/narzędzia na wzór
  `tools/diet.py`: backend wyprowadza owner/request z kontekstu i sprawdza aktualny
  podgląd, kanał, osobny obrót, wersję oraz transakcyjny replay/audit. Stare jawne
  komendy też wymagają pokazanego podglądu. Korekta nie zatwierdza nowej wersji.
- `catalog_creations` wiąże request mutacji ze szkicem niezależnie od źródłowego
  requestu zdjęć. Recovery odczytuje trwały wynik bez ponawiania narzędzi.
  Błąd przed zapisem nie sugeruje już, że zero operacji posiłków dowodzi stanu katalogu.
- Istniejący prompt otrzymał heurystyki opakowanie/etykieta vs talerz/porcja,
  pierwszeństwo jawnego tekstu i wspólne traktowanie zdjęć. To nie klasyfikator.
- Cookie i serwer mają wspólne 604800 s. Dłużej ważny token bearer zwiększa okres
  możliwego użycia po przejęciu; RAM nadal oznacza wylogowanie po restarcie.
  Login/logout, HttpOnly/SameSite/Secure i CSRF zachowane; bez trwałych sesji.

## Rzeczywiste dowody kontynuacji

Harness: `/opt/data/jobs/k90-ui-polish-20261029/run_batch.py`, interpreter
`/opt/data/projects/k90/.venv/bin/python`, cwd `/opt/data/projects/k90-ui-polish`.
Sanitized env, fikcyjne HOME/data/auth/SQLite, dotenv i sync wyłączone,
local memory, audyt non-loopback/private-file. Ancestry writer i procesów testowych
pod guardian 46781. `writer-admission.json` w bieżącym run zawiera dowód WORKSHOP,
lock FREE i świeży quota 11%/24%. Hardcoded stara nazwa gałęzi w metadanych guard
nie jest dowodem testowania starej gałęzi; cwd/PYTHONPATH i Git wskazują obecną.
Tooling niezmieniony.

Ostatni batch przed restartem nie był przerwany:
`catalog-source-clarification-green-20261115`, exit0, 10 passed /15 deselected,
26.55 s. Poprzedni `catalog-complete-focused-20261115`: exit0, 56 passed, 64.02 s.
Nowe testy obejmują oba zgłoszenia przez rzeczywisty adapter/album/HTTP/kolejkę/
agent/tool/SQLite/dostawę, naturalną zgodę i korektę, prywatność, source guards,
replay oraz niepokazany/obcy/przeterminowany podgląd. Provider jest skryptowany.

Pierwsza pełna regresja `catalog-writer-final-python-20261116`: exit1,
882 passed/5 failed/1 skipped,497.24s. Trzy stare fixture w `food_catalog_web`
i `photo_batches` nadal zakładały obcego właściciela lub lokalną zgodę bez modelu.
Zachowano odmowę obcego chatu oraz osobny HTTP read-denial i zastąpiono zgodę
syntetycznymi tool calls przez rzeczywistą pętlę agenta, bez zmian aplikacji.

Dwa błędy niezmienionego `test_profile_report` wystąpiły przed modyfikacją logów
w samych testach. Read-only replay zapisanych logów na parserze z bazy `74ca891`
i bieżącym jest identyczny: queue_wait incomplete, pozostałe spany kompletne,
model_calls2. Parser byte-identical, SHA256
`a3c203e7657b4bd6ccdd40927f8a78846226e879523921725bbc16e49a4938d9`.
UTC zakres kolejki różni się od elapsed o1.163ms/1.567ms przy tolerancji1ms.
To ten sam udokumentowany problem czasowy bazy; nie naprawiano go w tym zadaniu.
Batch `catalog-writer-profiling-baseline-replay-20261116`: exit0.

`catalog-writer-fixture-regression-20261116 -m pytest -q
 tests/test_food_catalog_web.py tests/test_photo_batches.py tests/test_profile_report.py`:
exit0,42 passed,22.66s. `catalog-writer-final-node-path-20261116`: syntax PASS,
37 PASS; pierwsza próba bez absolutnej ścieżki Node miała exit127 i zachowany log.
Ostatni pełny `catalog-writer-final-python-corrected-20261116`: exit1,
886 passed/1 failed/1 skipped,492.86s. Jedyny FAIL:
`test_profile_report.py::test_actual_emissions_missing_span_evidence[whole_child]`.
Także ten konkretny log odtworzono na identycznym parserze bazy i bieżącym:
queue_wait incomplete, model_calls2, UTC40.667ms vs elapsed41.989919ms,
różnica1.322919ms przy tolerancji1ms. Batch
`catalog-writer-final-profiling-baseline-replay-20261116` exit0.
Nie deklarujemy pełnej zielonej regresji. Testy katalogu/sesji przeszły; profilowanie
pozostaje jawnym problemem czasowym istniejącej bazy do oceny koordynatora.
Nie powtarzano całego suite aż do zielonego wyniku.
Kod aplikacji nie zmienił się po pierwszej pełnej regresji. Manifest144 plików
kodu/testów potwierdzony po ostatnim suite. `git diff --check` i przegląd kandydatów
pod kątem sekretów bez wykrytych problemów. Quota końcowa przed commitem27%/26%.
Niezależny review, CI/build/network-isolated container smoke i PR należą do
koordynatora i nie zostały uruchomione przez writera. Produkcja, inference,
wdrożenie i przyczyna produkcyjnego wyjątku pozostają niezweryfikowane.

## Historyczny checkpoint z 2026-11-15

# Katalog i sesja — etap implementatora 2026-11-15

To częściowy checkpoint, nie odbiór ani opis wdrożenia. Sesja serwera i cookie
mają wspólne 7 dni; RAM, logout i zabezpieczenia cookie pozostają bez zmian.

## Dowody i granice

Nowy test `tests/test_catalog_source_session.py` przechodzi przez adapter Telegram,
agregację trzech zdjęć z podpisem, deduplikację części albumu, HTTP, kolejkę,
dispatcher, prawdziwy agent i narzędzia, SQLite oraz dostawę Telegrama.
Provider jest skryptowany, obrazy i dane fikcyjne; test nie dowodzi rozpoznawania
etykiet ani przyczyny zgłoszonego błędu produkcyjnego.

Pierwszy RED: 4 failed / 2 passed. Opis albumu bez szkicu, potem tekst
„zapisz do katalogu” w WWW lub Telegramie: brak produktu, narzędzie odrzuca
`own_label` bez obrazu w bieżącym zdarzeniu. Świeży album z „dodaj do katalogu”
tworzy jeden szkic, pokazuje podgląd i dostarcza odpowiedź. Zasymulowana awaria
po zapisie zachowuje szkic i raportuje go bez ponawiania. Awaria przed pierwszym
narzędziem ujawnia ogólny komunikat o zerze operacji posiłków — osobny RED
raportowania, nie dowód przyczyny produkcyjnego wyjątku.

Test sesji był RED przy cookie 43200 s. Po zmianie: 24 PASS (granica 604800 s
przez HTTP z ręcznie wysłanym także wygasłym cookie, logout, Secure oraz istniejące
rozmowy katalogowe). Trzy RED katalogu pozostają celowo niezamknięte w WIP.

## Następny pionowy etap — projekt, jeszcze bez implementacji

Wzorzec: `tools/diet.py`, `_mutate` / `_perform`: model interpretuje zwykły język,
backend wyprowadza właściciela i request z kontekstu, waliduje, wiąże fingerprint,
wykonuje transakcję i zwraca rzeczywisty wynik. Nie rozszerzać regexów
`product_review.intent`; obecne przechwytywanie przed modelem i unieważnianie
`direct` w `agent.run_agent` trzeba zastąpić spójną ścieżką narzędzi.

1. Zachować lokalnie odczytane pola i powiązanie z faktycznym zdarzeniem źródłowym
   przed powstaniem szkicu. Rozwiązywać jednoznaczne, świeże źródło właściciela
   także między kanałami; odrzucać foreign/local-only/stale, pytać przy wielu
   źródłach lub niezwiązanej rozmowie. Samo „ostatnie zdjęcie” jest niewystarczające.
   Historyczne obrazy nie mogą wracać do zewnętrznego modelu. Nie zmieniać
   `own_label` na `manual` ani pozwalać modelowi wybierać dowolnego event ID.
2. Udostępnić modelowi operacje kontroli/zmiany/zatwierdzenia/anulowania na wzór
   posiłków. Backend wiąże zgodę z podglądem aktualnej wersji faktycznie zapisanym
   w tym kanale, właścicielem i odrębnym późniejszym zdarzeniem użytkownika.
   Model nie może zatwierdzić nowej lub niewidzianej wersji w tym samym obrocie.
   Korekta i zgoda razem tworzą nowy podgląd. Idempotencja i audit w transakcji.
3. Oddzielić request tworzenia od źródłowego eventu zdjęć. Obecne
   `known_outcome` łączy produkt ze źródłowym requestem; po opóźnionym zapisie
   to nie będzie request mutacji. Trwały wynik katalogowy musi wiązać oba,
   obejmować tworzenie/zmianę/zgodę i służyć recovery bez ponowienia narzędzi.
   Przed pierwszym narzędziem nie znać zamiaru z samego wyniku modelu: raportować
   bezpieczny zakres wiedzy o zapisie, nie sugerować, że ledger posiłków dowodzi
   braku operacji katalogowych. Bez nowej bramki słów kluczowych.
4. Dodać do istniejącego promptu heurystykę etykieta/makra/kod/opakowanie → zwykle
   katalog, talerz/porcja → zwykle posiłek; tekst jawny ma pierwszeństwo, wszystkie
   zdjęcia rozpatruj łącznie, opakowanie nie dowodzi spożycia. Niejasność wymaga
   pytania. Przetestować także opakowanie z jawnym spożyciem i talerz z poleceniem
   katalogowym; to wskazówki dla modelu, nie sztywne routowanie.

Następne testy: delayed RED→GREEN, brak ponownego wysyłania obrazów, foreign,
niejednoznaczność, przeterminowanie, replay, naturalna zgoda/korekta przez model
i narzędzia oraz odmowa zgody na niewidzianą wersję w innym kanale.
Nie wyłączać obecnych testów właściciela, wersji, prywatności ani UI.

Nie udało się odtworzyć produkcyjnego wyjątku świeżego albumu. Jedyny proponowany
pakiet diagnostyczny: identyfikator korelacji żądania/zadania, etap awarii,
klasa/kod wyjątku oraz nazwy plików/funkcji i numery linii stosu (bez treści linii).
Bez promptów, zdjęć, tokenów, treści bazy i bez ponawiania próby przez właściciela.
Nie pobierano diagnostyki produkcyjnej.

Pozostają implementacja katalogu, pełna regresja na końcowym SHA, niezależny
review, CI/build/smoke bez publikacji i ewentualny PR. Żadnej z tych bramek nie
uznajemy tutaj za zaliczoną.
