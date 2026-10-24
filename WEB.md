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

Schemat obsługuje dwie opcjonalne kolumny historii oraz tabele kolejki i transportu.
Przed aktualizacją starszej instalacji zachowaj backup bazy i dokumentów.
`python server.py` pozostaje alternatywnym, starszym trybem Telegram-only;
nie uruchamiaj go równolegle z nowym adapterem dla tego samego bota.
