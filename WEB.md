# Frontend k90 — lokalna weryfikacja i wdrożenie

Pierwsza wersja obejmuje wspólny chat WWW/Telegram, dashboard na danych SQLite,
przeglądarkę tabel oraz odczyt dokumentów Markdown i pamięci pacjenta.
Obraz `admroz/k90:latest` jest budowany dla `linux/amd64` (Lenovo M900).

Frontend jest częścią `main`, a nie wyłącznie eksperymentalnym branchem.
Ten dokument opisuje kod i procedury; nie potwierdza wersji działającej na serwerze.
Plan rozszerzenia pamięci, jeszcze bez implementacji:
[Pamięć k90](docs/MEMORY_ARCHITECTURE.md).

## Uruchomienie na Macu

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python dev.py
```

Otwórz <http://127.0.0.1:8000>. Domyślne lokalne hasło: `k90-local-preview`.
Możesz ustawić własne przez `K90_LOCAL_PASSWORD`. Serwer nasłuchuje wyłącznie
na loopback; w tym trybie lokalne HTTP nie wymaga konfiguracji certyfikatu.

Domyślnie aplikacja używa fikcyjnych danych w `data/local/demo/`. Chat zapisuje
wiadomość i odpowiedź demonstracyjną bez kontaktu z modelem. Telegram oraz
synchronizacja Garmin/Libre są wyłączone.

### Dane pobrane z NAS

Backup tworzysz dotychczasową komendą `/backup`. Pobierasz konkretny plik backupu
i dokumenty `.md` samodzielnie przez SCP lub File Station. Nie kopiuj samego
aktywnego `k90.db`, bo najnowsze zapisy mogą być w WAL. Na Macu nadaj pobranemu
backupowi nazwę `k90.db` i umieść go razem z dokumentami w nowym katalogu `data/`.
Przy błędzie `subsystem request failed` opcja `scp -O` wybiera klasyczny SCP.
Repozytorium nie zawiera skryptu wykonującego zdalne polecenia backupu.

```bash
.venv/bin/python dev.py --snapshot data/local-import.20260920
```

Każde uruchomienie z `--snapshot` tworzy NOWĄ kopię roboczą w
`data/local/snapshot-<data-godzina>/`; pobrany backup pozostaje bez zmian.
Sprawdzana jest integralność kopii, kopiowane są wyłącznie określone dokumenty,
a kolejka i stan transportu z importu są pomijane, żeby nie odtworzyć starych zleceń.
Lokalne rozmowy i edycje agenta trafiają wyłącznie do katalogu roboczego.
Przy następnym uruchomieniu można wskazać ten katalog przez `--snapshot`, aby
zachować jego dane w kolejnej kopii (kolejka jest ponownie czyszczona).

Prawdziwe rozmowy z modelem wymagają świadomego włączenia:

```bash
.venv/bin/python dev.py --snapshot data/local-import.20260920 --live-agent
```

Wtedy klucze/model są odczytywane z lokalnego `.env`, a zapytania mogą być płatne
i zawierać dane pacjenta. Telegram i synchronizacja źródeł nadal są wyłączone;
agent może zmieniać lokalną kopię danych i dokumentów. Nic nie jest wysyłane na NAS.

## Architektura

Jeden kontener, dwa procesy nadzorowane przez Supervisor:

- `backend`: FastAPI, statyczny frontend bez CDN, agent, SQLite i dokumenty.
- `telegram`: odbiera wiadomości i przekazuje je do backendu przez lokalne HTTP;
  dostarcza zapisane odpowiedzi. Uwierzytelnia się losowym tokenem generowanym
  przy starcie kontenera.

Oba kanały korzystają z `CONVERSATION_USER_ID`. Przeglądarka pokazuje obie strony
rozmowy niezależnie od kanału; na Telegram trafiają tylko odpowiedzi na wiadomości
z Telegrama. Starsze rekordy z innym `user_id` nie są automatycznie scalane.

Zlecenia są zapisywane do SQLite i przetwarzane kolejno przez jednego workera.
Identyfikator żądania zapobiega powtórnemu uruchomieniu tego samego zlecenia.
Po restarcie zlecenie rozpoczęte, ale niezakończone, jest oznaczane jako przerwane;
nie jest automatycznie wykonywane ponownie, ponieważ narzędzie mogło już zapisać dane.
Jeżeli odpowiedź została zapisana przed restartem, zostaje odzyskana z historii.

`chat_timeline` rezerwuje trwałe pozycje użytkownika i odpowiedzi przy przyjęciu
zlecenia. Stan queued/running i wynik done/failed/interrupted zmieniają treść
tej samej pozycji, także po odświeżeniu i na innej przeglądarce. Błąd pozostaje
przy swojej wiadomości; nie ma ukrywania w localStorage ani automatycznego retry.
`conversations` i zdarzenia audytowe pozostają zachowane. Korelacja używa wyłącznie
`request_id` wraz z właścicielem i rolą, bez porównywania treści lub zgadywania
na podstawie daty. Historyczne wpisy bez identyfikatora zachowują własną tożsamość.

Migracja jest addytywna. Właściciel starszego zadania pochodzi z jednoznacznych
rekordów o tym samym request_id (rozmowa/zdarzenia); sprzeczne przypisania są
odseparowane. Gdy brak jakichkolwiek takich rekordów, stara jednoosobowa kolejka
dziedziczy skonfigurowany `CONVERSATION_USER_ID`. Repo nie pozwala odtworzyć
wcześniejszej wartości konfiguracji, jeśli operator zmienił ją bez zachowania
śladów. Daty służą początkowemu uporządkowaniu migracji, numery kolejki/rekordów
rozstrzygają remisy. Nowe wpisy mają kolejność przyjęcia zleceń.

`GET /api/messages` zachowuje listę i parametr `before`, ale `id` jest teraz
kursorem projekcji timeline, nie kluczem tabeli conversations. Po aktualizacji
odśwież stronę i pobierz nowe kursory. `GET /api/jobs` pozostaje kompatybilnym,
ograniczonym widokiem statusów; przeglądarka renderuje rozmowę z timeline.
Opcjonalne profilowanie i przełącznik tekstu: [runbook](docs/DEPLOYMENT_RUNBOOK.md#pomiary-etapów).

Niedostępny Telegram nie blokuje startu WWW. Jego błędy i retry dotyczą adaptera;
awaria procesu adaptera powoduje restart tylko tego procesu. Odpowiedzi czekają
w bazie na dostarczenie. Potwierdzane są osobne fragmenty długich odpowiedzi.
Jeśli Telegram przyjął fragment, ale odpowiedź sieciowa lub lokalne potwierdzenie
zaginęły, ponowienie może wysłać ten fragment drugi raz — Telegram nie daje tu
gwarancji exactly-once. Nie uruchamia to ponownie agenta ani narzędzi.

Backend musi działać jako jeden proces Uvicorn (`--workers 1`); blokada pliku
zapobiega uruchomieniu drugiego backendu na tej samej bazie. Cały kontener nadal
współdzieli zasoby i restart wdrożenia. `healthz` sprawdza backend i workera;
Docker sam nie restartuje kontenera tylko dlatego, że healthcheck jest unhealthy.

## Zakres interfejsu

- Przegląd: ostatnie pomiary z datami, wykresy 7/30/90/365 dni, posiłki i status
  synchronizacji. Posiłki domyślnie pokazują dzisiaj, z wyborem daty, przechodzeniem
  do poprzednich dni i sumami kalorii, białka, węglowodanów oraz tłuszczu.
  Wybór dnia jest niezależny od okresu wykresów; braki wartości odżywczych są oznaczone.
  Przycisk „Omów” przygotowuje pytanie dla agenta.
- Bilans dnia: zapisane kalorie minus suma dziennych kalorii spoczynkowych i aktywnych
  Garmin (`bmrKilocalories` + `activeKilocalories`). To estymacja Garmin, bez stałej
  wartości BMR i bez ponownego dodawania kalorii treningów. Brak wartości nie jest
  zerem; bilans wymaga danych Garmin i kompletnych kalorii zapisanych posiłków.
- Regeneracja: sen, HRV, Body Battery, tętno spoczynkowe, stres i oddech.
- Aktywność: treningi, dystans oraz dzienne kalorie aktywne i całkowite spalanie.
  Przycisk „Omów” przygotowuje pytanie; agent odczytuje dzienne spalanie przez
  `get_daily_metrics`, korzystając z tych samych zapisanych wartości Garmin.
- Rozmowa: tekst, JPG/PNG/WebP do 5 MB, starsze wiadomości, stan kolejki i błędy.
  Odpowiedź pojawia się po zakończeniu przetwarzania; token streaming jest poza v1.
- Dane: dozwolone tabele, wyszukiwanie, sortowanie i stronicowanie. Odczyt bez
  wykonywania dowolnego SQL; długie komórki są ograniczone do 4000 znaków.
- Dokumenty: pięć dokumentów pacjenta i `patient_summary`, podgląd oraz źródło.
  Edycja dokumentów i formularze edycji posiłków są poza v1.

Wykresy powstają bez LLM. Glukoza jest agregowana godzinowo, z preferowaniem
odczytu `latest` przy duplikacie czasu. Brak pomiaru nie jest zerem. Widok czyta
aktualną bazę po wejściu/odświeżeniu; synchronizacja źródeł jest osobną operacją
(`/update` lub przycisk). Przycisk „Pobierz Garmin” korzysta z osobnego zadania
w tej samej kolejce: nie wywołuje agenta, Libre ani podsumowania LLM. Stan pobierania
jest dostępny po odświeżeniu strony, a ponowione żądania nie dublują zadania.
Pierwszy odczyt pustej tabeli `kalorie_dzienne` uzupełnia historię od `2022-01-01`.
Partie po 30 dni są od razu zapisywane; po błędzie lub restarcie nowe pobranie wznawia
pracę od ostatniego zapisanego dnia z 7-dniowym buforem. Brak historycznych danych
Garmin pozostaje brakiem, a nie wymyślonym spalaniem. Aktualne wartości wymagają
wcześniejszego przesłania danych z zegarka do Garmin Connect.
Harmonogram synchronizacji niezależny od wiadomości
pozostaje do dalszego ustalenia. Dotychczasowy auto-sync przy rozmowie pozostaje.

## Testy przed wdrożeniem (aktualnie AMD64)

```bash
.venv/bin/python -m pytest -q
node --check web/app.js
node --test tests/web_*.test.mjs
```

Testy używają tymczasowych baz, fikcyjnych danych i atrap usług. Obejmują m.in.
izolację importu, WAL, logowanie, CSRF, limity żądań, niedozwolone ścieżki/SQL,
kolejność wiadomości, idempotencję, restart w trakcie operacji i awarię dostarczania
odpowiedzi przez Telegram podczas działającego chatu WWW.

Dodatkowa weryfikacja pobranego backupu (wszystkie widoki API na tymczasowej
kopii, z porównaniem sum kontrolnych plików źródłowych):

```bash
K90_TEST_IMPORT=data/local-import.20260920 .venv/bin/python -m pytest -q tests/test_imported_data.py
```

Z działającym lokalnym Dockerem można sprawdzić rzeczywisty obraz:

```bash
docker build -t k90:test .
.venv/bin/python scripts/smoke_container.py k90:test
```

Test tworzy jednorazowy kontener bez woluminów użytkownika i bez sieci zewnętrznej.
Sprawdza HTTP, statyczne pliki, chat i restart zabitego procesu Telegrama przy
niezmienionym procesie backendu. Po zakończeniu usuwa tylko utworzony kontener.
GitHub Actions uruchamia testy i ten scenariusz również na branchach `codex/**`
i PR-ach. Publikowanie obrazu `latest` jest możliwe wyłącznie z `main` po testach.

Przed wdrożeniem pozostaje ręcznie ocenić wygląd desktop/mobile, sprawdzić prawdziwy
model na kopii danych i przeprowadzić smoke test obrazu. Testy nie wysyłają
wiadomości do prawdziwego Telegrama ani nie wykonują operacji na serwerze produkcyjnym.

## Konfiguracja serwera

`WEB_PASSWORD` musi mieć co najmniej 12 znaków. Compose publikuje port 8000
domyślnie na `127.0.0.1` serwera; frontend może być dostępny przez lokalny reverse proxy
z HTTPS. DNS/nazwa hosta i certyfikat są osobnym krokiem konfiguracyjnym.
Domyślne `WEB_COOKIE_SECURE=true` wymaga HTTPS. Nie wystawiaj tego portu publicznie.

Dla bezpośredniego HTTP w zaufanym LAN ustaw `WEB_BIND_IP` na adres serwera i
`WEB_COOKIE_SECURE=false`. Mapowanie portu jest już w Compose. Przykład: [DEPLOY.md](DEPLOY.md).

Schemat obsługuje kolumny identyfikacji historii oraz tabele kolejki, timeline i transportu.
Przed aktualizacją starszej instalacji zachowaj backup bazy i dokumentów.
`python server.py` pozostaje alternatywnym, starszym trybem Telegram-only;
nie uruchamiaj go równolegle z nowym adapterem dla tego samego bota.

### Trwałe logi operacyjne

Backend, adapter Telegrama i CLI zapisują JSON do `DATA_DIR/logs` (w kontenerze
`/data/logs`, na istniejącym trwałym wolumenie). `app.log` zawiera przebieg,
ostrzeżenia i błędy; `errors.log` dostaje dodatkową kopię ERROR/CRITICAL.
`profiling.jsonl` powstaje wyłącznie po włączeniu profilowania i nie trafia do
konsoli ani pozostałych plików. Pliki powstają przy pierwszym zapisie.

Limity bieżącego pliku: app 10 MiB, errors 5 MiB, profiling 10 MiB; każdy ma trzy
rotacje `.1`–`.3` (łącznie najwyżej 100 MiB oraz puste pliki blokad). Katalog ma
tryb 0700, pliki 0600. Linux `flock` obejmuje otwarcie, rotację i zapis; oba procesy
otwierają plik ponownie pod blokadą. Nie uruchamiaj zewnętrznego rotatora tych
samych plików. Awaria zapisu nie zmienia wyniku zadania; proces emituje najwyżej
jeden stały alarm o niedostępnym sinku na stderr. Nie ma gwarancji fsync dla każdego
rekordu ani kompletnego ostatniego wiersza po nagłym przerwaniu procesu.

Rekordy mają `component` i czas ISO8601 UTC. Losowy `request_id` łączy etapy zadania
również przy wyłączonym profilowaniu. `scope_id` rozróżnia kolejne wykonania
processing/submission/delivery; `clock_id` identyfikuje zegar profilowania procesu.
Numery rundy i narzędzia oraz diagnostyczny `operation_id` nie są mechanizmem
deduplikacji. Wynik narzędzia ma osobne `tool_outcome`; `mutation_outcome=unknown`
nie pozwala uznać `ok` za dowód commit. `response_outcome` i `delivery_outcome` są
odrębne. Zakończona dostawa Telegrama oznacza przyjęcie fragmentów przez API i
lokalne potwierdzenie, a pomiar WWW jedynie przygotowanie projekcji odpowiedzi.
Nie mierzymy przeczytania odpowiedzi przez użytkownika.

Aplikacja emituje jawne zdarzenia przez własne loggery `k90.app` i `k90.profile`.
Dozwolone są stałe nazwy, poziomy, kategorie i kody, ograniczone liczniki, status
HTTP oraz request ID z udokumentowanego pola SDK lub nagłówka `x-request-id`
protokołu subskrypcji. Nie eksportujemy body, URL, pozostałych nagłówków, rozmów,
pomiarów ani obrazów. Opisy wyjątków i tracebacki nie są formatowane.
Znane loggery SDK/transportu są wyciszone; `uvicorn.error` oraz nieobsłużone
wyjątki procesu/wątku mają wąskie adaptery zapisujące wyłącznie kategorię.
Nie przechwytujemy globalnie Python logging ani dowolnego kodu bibliotek,
niestandardowych handlerów lub `print`. Interaktywny wynik CLI i instrukcje
lokalnego logowania OAuth pozostają wyjściem użytkowym, poza logami operacyjnymi.
Lokalne dane i audyt SQLite pozostają oddzielne. Sam ten format nie rozstrzyga
przyczyny awarii dostawcy.

Przed wdrożeniem właściciel sprawdza dokładny obraz po niezależnym review i CI,
bind `/data`, UID/prawa zapisu, wolne miejsce oraz retencję kopii logów. Backup przez
API SQLite z dokumentami, zdjęciami i lokalnym kluczem pamięci nadal jest wymagany;
logi nie zastępują backupu bazy. Politykę kopiowania i retencji `/data/logs` ustala
osobno. Na syntetykach sprawdzić restart/recreate i rotację obu procesów. Rollback
polega na powrocie do poprzedniego zaakceptowanego obrazu po zachowaniu bieżącego
stanu; nie nadpisuje bazy i nie usuwa audytu ani nowych logów. Publikacja obrazu,
wdrożenie i rzeczywiste testy OAuth/Telegrama pozostają osobnymi krokami właściciela.

Adapter Telegrama tworzy osobny losowy kontekst ingress przed pobraniem obrazu,
walidacją i wysłaniem do backendu. `telegram.submitted` łączy ten kontekst z
`backend_request_id` i `backend_job_id` zwróconymi po enqueue; są to wygenerowany
identyfikator diagnostyczny i numer lokalnego zadania. Ponowiona wiadomość nadal
korzysta z dotychczasowego mechanizmu deduplikacji. Błędy ingress są rejestrowane
przed wyjściem z kontekstu. Transport zachowuje wyłącznie zwalidowaną kategorię,
kod i status HTTP; opis odpowiedzi Telegrama i dane żądania nie są przenoszone do
wyjątku diagnostycznego. Komponenty wykonywane jako skrypty mają stałe nazwy.

Bootstrap konfiguruje standardowe handlery własnych loggerów i skończoną listę
znanych loggerów bibliotek. `Logger.callHandlers` i fabryka rekordów pozostają
standardowe. Pliki obsługuje `RotatingFileHandler` z `flock`: każdy zapis pod
blokadą ponownie otwiera aktualny plik, wykonuje rotację i zamyka uchwyt.
Błąd logowania daje jeden stały alarm stderr na proces i nie blokuje zadania;
pozostałe sinki są nadal próbowane. Nie gwarantujemy kompletnego końca pliku
po awarii procesu ani fsync każdego rekordu. Profilowanie ma osobny sink.
Rozszerzony smoke CI uruchamia dwa procesy zapisujące logi i sprawdza ich limity,
prawa, kopię błędów i izolację profilowania. Następnie porównuje snapshot logów po
restart i recreate z tym samym, unikalnym wolumenem syntetycznym `/data`, który
usuwa przy sprzątaniu. Uruchomienie helpera na hoście nie potwierdza wyniku tego
smoke na rzeczywistym obrazie.


### Ręczna korekta posiłków

W widoku posiłków przyciski Edytuj/Usuń korygują cały wpis bez LLM.
Ilość i jednostka g/ml/szt są opcjonalne i podawane razem; starsze dane pozostają
null, bez zgadywania z opisu. Ilość nie przelicza makr. Puste makra oznaczają brak
danych, zero pozostaje zerem. Formularz dopuszcza pojedynczy przecinek dziesiętny.
W razie konfliktu odczytaj aktualny wpis przed kolejną korektą. Historia rozmowy
i snapshoty katalogowe pozostają oryginalnym dowodem, korekta jest nadpisaniem
wartości posiłku z lokalnym audytem. Syntetyczny test Chromium obejmuje edycję,
reload, konflikt zapisu i potwierdzenie usunięcia.

Kontrakt API: PUT `/api/meals/{id}` wymaga wszystkich pól `description`,
`quantity`, `unit`, `calories`, `protein_g`, `carbs_g`, `fat_g`, `date`, `time`
oraz `expected_revision` (dodatnia liczba całkowita) i `request_id` (1–120 znaków,
ASCII litery/cyfry/dwukropek/podkreślenie/myślnik). DELETE przyjmuje JSON z tymi
dwoma ostatnimi polami. Obowiązuje sesja, `X-K90-Request: 1` i dotychczasowa
kontrola Origin. Liczby to skończone liczby JSON w zakresie 0–1000000 lub null;
bool i tekst, w tym przecinek w JSON string, są odrzucane. Opis: 1–2000 znaków,
nie same spacje. Data: rzeczywista YYYY-MM-DD, czas HH:MM lub null dla nieznanego.
Brak wpisu:404, konflikt rewizji/tokena:409, błędny kontrakt:422. Powtórzenie tej
samej operacji zwraca historyczny wynik z ledgera, bez ponownego zapisu.

Migracja przy inicjalizacji dodaje quantity/unit oraz meal_changes; revision
pochodzi z PR19. Audyt, tombstone i wyniki operacji wymagają zachowania całej bazy
w backupie. Starszy writer po downgrade nie zapewni CAS/audytu: rollback wymaga
zatrzymania writerów i zgodnego zestawu kodu/backup, bez ręcznego kasowania audytu.

## Kilka zdjęć w jednej wiadomości

WWW pozwala wybrać1–4 zdjęcia JPG/PNG/WebP, każde do5 MB i razem do10 MB
(limit żądania14 MB). Podglądy pozwalają usuwać pojedyncze zdjęcia; błąd wysłania
zachowuje wybór. Zdjęcia trafiają łącznie do jednej tury. Dla etykiety produktu
powstaje jedna propozycja i jedna zgoda; sprzeczne dane wymagają wyjaśnienia.

Aktualny adapter Telegrama łączy `media_group_id` w trwałym inboxie backendu,
nie myli `photo[]` (wariantów rozdzielczości) z albumem. Zamyka paczkę po2 s ciszy
lub10 s zbierania, z flush przy pollingu (timeout3 s; sieć może opóźnić wykonanie).
Cisza jest heurystyką kompletności. Spóźniony element wywołuje jeden komunikat
„niekompletny album / wyślij całość ponownie”, bez drugiej analizy. Przekroczenie
limitu odrzuca cały otwarty album. Offset potwierdza się po trwałym zapisie części.
Retencja zamkniętych identyfikatorów7 dni, maks.32 otwarte i1000 zachowanych grup;
pending przeżywa restart, zdjęcia inboxu są usuwane po zamknięciu. Obrazy źródłowe
pozostają lokalnie w kolejce/zdarzeniach zgodnie z istniejącą polityką prywatności.
Starszy tryb `server.py` Telegram-only nadal przyjmuje jeden obraz, bez obsługi albumów.
Dowody i ograniczenia: [product-photo-batches.md](docs/review-evidence/product-photo-batches.md).


## Diagnostyka / Czasy

Po zalogowaniu panel pokazuje ostatnie 50 żądań/zadań znalezionych w ograniczonym
skanie `DATA_DIR/logs/profiling.jsonl` i rotacji `.1`–`.3`: UTC i czas lokalny
przeglądarki, kolejkę, przetwarzanie, wywołania modelu, próby dostawy i tabelę etapów.
Profilowanie włącza `K90_PROFILING_ENABLED=true`. Wyłączenie nie usuwa starszych
pomiarów; stan wyłączenia/braku danych jest jawny. GET `/api/diagnostics/timings`
wymaga tej samej sesji co pozostały panel i nie przyjmuje ścieżki pliku.

Czasy inclusive nakładają się. Exclusive wymaga kompletnych, zgodnych przedziałów
dzieci i odejmuje ich unię. Brak pomiaru jest pustą wartością, nie zerem.
Niepełny/ograniczony odczyt ma ostrzeżenie. Dostawa nie oznacza odbioru odpowiedzi.
Całość kolejka + przetwarzanie wymaga rozłącznych przedziałów tego samego zegara;
obecne granice scope mogą uniemożliwić taki pomiar. Szczegóły ograniczeń i tani,
opcjonalny adapter plików operatora `K90_PROFILE_LEGACY_FILES` opisuje
[raport weryfikacji](docs/review-evidence/owner-profiling-report.md).
