# k90 — architektura i praca nad projektem

Ten plik opisuje aktualny kod, nie potwierdza wersji uruchomionej na serwerze.
Konfiguracja i uruchamianie: [README.md](README.md), panel: [WEB.md](WEB.md),
wdrożenie: [DEPLOY.md](DEPLOY.md), zadania: [TODO.md](TODO.md).

**Pamięć i autoryzacja:** założenia w [docs/MEMORY_ARCHITECTURE.md](docs/MEMORY_ARCHITECTURE.md),
aktualne polecenia i granice w [docs/OPERATIONS_MEMORY_AUTH.md](docs/OPERATIONS_MEMORY_AUTH.md),
wyniki i niewykonane bramki w [docs/VERIFICATION.md](docs/VERIFICATION.md).
Obecność implementacji i testy na syntetykach nie dowodzą wdrożenia produkcyjnego,
pełnej anonimizacji ani autoryzacji między bankami Hindsight.

## Stack i procesy

- Python, własna pętla tool-use w `agent.py`; LiteLLM / Chat Completions albo
  `responses_api.py` dla rodziny GPT-6.1 Sol. Model rozmowy i summary wybierane
  niezależnie, domyślnie `gpt-5.4`.
- `subscription_api.py` / `subscription_auth.py` / `subscription_login.py`:
  opcjonalny tryb ChatGPT OAuth, własny magazyn i serializowany refresh;
  `K90_AGENT_AUTH=chatgpt`, summary dziedziczy ten wybór, o ile nie nadpisane.
  Bez automatycznego płatnego API fallbacku. Ustawienie kredytów potwierdza operator.
- `webapp.py`: FastAPI, logowanie hasłem, sesje, kontrola żądań i API WWW.
- `web_runtime.py`: trwała kolejka SQLite, jeden worker i odzyskiwanie stanu.
- `web_data.py` i `web/`: dashboard, wykresy, posiłki, tabele, dokumenty i chat;
  statyczny frontend bez CDN i bez serwera Node w runtime.
- `telegram_adapter.py`: long polling, wyłącznie dozwolony właściciel i prywatny
  chat; przekazywanie wiadomości przez wewnętrzne HTTP do tego samego backendu.
- `container_start.py` generuje wewnętrzny token, `supervisord.conf` nadzoruje
  backend oraz adapter Telegrama jako dwa procesy w jednym kontenerze.
- SQLite oraz dokumenty w katalogu danych; `fetch_garmin.py` i `fetch_libre.py`
  zapisują dane źródeł bezpośrednio do SQLite.
- Docker Compose, obraz AMD64 publikowany do Docker Hub. ARM64 jest zachowane
  w komentarzach workflow, ale wyłączone. Push do `main` nie wdraża kontenera.
- `server.py` to starszy, alternatywny tryb Telegram-only; `agent.py` ma CLI.
  Nie uruchamiać dwóch odbiorców tego samego bota Telegrama.

## Przepływ wiadomości

```text
WWW ───────────────────────────┐
Telegram → telegram_adapter.py ┴→ webapp.py → chat_jobs (SQLite)
                                                 ↓
                                          jeden worker
                                                 ↓
                                  komendy / sync / agent.py
                                                 ↓
                                      model ↔ tools/ ↔ dane
                                                 ↓
                                      conversations + wynik
                                                 ↓
                                      WWW / dostawa Telegram
```

Oba kanały korzystają z `CONVERSATION_USER_ID` (domyślnie `owner`). Odpowiedzi
Telegrama są dostarczane tylko dla jego zleceń. Szczegóły idempotencji, restartu
i ograniczeń dostarczania: [WEB.md](WEB.md#architektura).
Backend wymaga jednego procesu Uvicorn (`--workers 1`) na tę bazę.

## Kontekst i historia

`agent._build_system_message()` dołącza prompt systemowy, datę i godzinę,
`patient_summary` oraz bieżący kontekst z `tools/context.py`. Dalej trafiają
ostatnie `HISTORY_MESSAGES * 2` rekordów rozmowy i bieżąca wiadomość
(tekst lub tekst ze zdjęciem). Domyślnie to 10 par wiadomości.

`conversations` zachowuje kompatybilną historię udanych par wiadomości.
`agent_events` dodatkowo zapisuje oryginalne wejście przed modelem, także po błędzie,
oraz argumenty/wyniki narzędzi i końcową odpowiedź. Nie utrwala reasoning providera.
`memory_runtime.py` dołącza ograniczony recall ze źródeł lokalnych; `k90_memory/`
prowadzi wersje, FTS5 i transakcyjny outbox dla wymiennego adaptera HS.
Domyślnie działa lokalnie, bez sieci HS; starej historii nie importuje automatycznie.
Źródła wracają z rolą/datą/rewizją. Wynik HS musi przejść lokalną weryfikację właściciela
i bieżącej wersji. Pomiary nadal odczytujemy z SQL, nie traktujemy wspomnień jako pomiaru.

`summary.py` buduje siedmioliniowy rekord z dokładnie pięciu dokumentów SQLite:
`pacjent.md`, `wywiad.md`, `analiza.md`, `dieta.md`, `tydzien.md`.
Nie jest to podsumowanie historii rozmów. Zapis jest singletonem
`patient_summary` (`id=1`). Odświeżanie następuje przy starcie, gdy brak summary
lub jest przeterminowane, oraz przez narzędzie i ścieżki obsługi zmian/synchronizacji.
Przycisk WWW „Pobierz Garmin” świadomie pomija summary i model.

Prompt ładuje `system_prompt.py`: plik z `DATA_DIR` może nadpisać wersję repo.
Dane i prompt produkcyjny nie są ustalane na podstawie samego repozytorium.

## Narzędzia i dane

Aktualny rejestr i definicje narzędzi: `tools/__init__.py`.

| Moduł | Odpowiedzialność |
| --- | --- |
| `tools/health.py` | Odczyt ciśnienia, wagi, snu, aktywności, HRV, Body Battery, metryk dziennych i glukozy. |
| `tools/lab.py` | Odczyt wyników laboratoryjnych. |
| `tools/diet.py` | Dodawanie, aktualizacja, odczyt i usuwanie posiłków. |
| `tools/garmin.py` | Kontrola synchronizacji Garmin, statusy i statystyki zmian. |
| `tools/libre.py` | Kontrola synchronizacji Libre i przełącznik `LIBRE_ENABLED`. |
| `tools/patient.py` | Odczyt i pełne nadpisanie pięciu dozwolonych dokumentów pacjenta; nie promptu systemowego. |
| `patient_documents.py` | Canonical dokumenty i rewizje w SQLite; zachowawczy import i jawny eksport Markdown. |
| `summary.py` | Generowanie i odświeżanie podsumowania pacjenta. |
| `tools/context.py` | Bieżący wyciąg danych do promptu, bez wyszukiwania starszych rozmów. |
| `tools/db.py` | Połączenie, inicjalizacja schematu i backup przez API SQLite. |

Tabele danych zdrowotnych obejmują `cisnienie`, `waga`, `sen`, `aktywnosci`,
`hrv`, `body_battery`, `metryki_dzienne`, `kalorie_dzienne`, `wyniki_lab`,
`posilki` i `glukoza_libre`. `init_db()` inicjalizuje schemat także bez importu CSV.
Dodatkowo istnieją `conversations`, `patient_summary`, `usage_stats`, `sync_status`;
`web_runtime.init_runtime()` dodaje `chat_jobs` i `transport_state`.
Nowe tabele obejmują `patient_documents`, `patient_document_revisions`, `agent_events`,
`memory_sources`, `memory_versions`, `memory_fts`, `memory_outbox`, `memory_settings`.
Zmiana dokumentu i zlecenie indeksowania są częścią jednej transakcji. Klucz HMAC
w `memory_settings` jest lokalny i musi przetrwać backup/restore; nie jest kluczem API.

`outbound_policy.py` filtruje wszystkie ścieżki modelowe, w tym summary i wyniki narzędzi.
Nie wyłączać filtra dla naprawienia testu. Obrazy wymagają osobnego jawnego opt-in;
test obrazów musi tę zgodę ustawić lokalnie dla fikcyjnego fixture.

Bilans dnia opiera się na zapisanych posiłkach i `kalorie_dzienne`
(`bmrKilocalories` + `activeKilocalories`), bez ponownego dodawania treningów.
Agent przez `get_daily_metrics` i panel korzystają z tych samych danych.

## Synchronizacja i komendy

- Auto-sync przy rozmowie, gdy danego dnia nie było udanego pobrania źródła;
  błędy nie muszą blokować odpowiedzi. Nie ma niezależnego schedulera.
- Garmin uzupełnia dane od ostatniego zapisu z buforem 7 dni; dla pustych tabel
  od `2022-01-01`. Dzienna energia jest zapisywana partiami po 30 dni.
- Libre pobiera dostępne `graphData` i najnowszy pomiar, nie dowolny zakres historii.
- `POST /api/sync/garmin` kolejkuje zadanie data-only; stan przez
  `GET /api/sync/garmin`. Pomija LLM, Libre i summary.
- `/status`, `/debug`, `/update`, `/summary`, `/backup`, `/help` działają bez
  rozmowy z modelem. `/update` synchronizuje Garmin i włączone Libre; może też
  odświeżyć summary przez model, jeśli wykryto zmiany Garmin.

## Bezpieczny rozwój i weryfikacja

- Autonomiczne zlecenie ma jednego zapisującego. Przed zmianami sprawdzić status
  `docs/STATUS.md` i blokadę `/opt/data/jobs/k90-autonomy/worker.lock` (flock).
  Jeśli jest zajęta, inna sesja ma tylko odczytywać status, nie uruchamiać drugiego
  implementatora. Samo istnienie pliku lock nie oznacza aktywnej blokady.
- Mandat autonomicznej kontynuacji i checkpointów Git: `docs/IMPLEMENTATION_PLAN.md`.

- `dev.py` domyślnie uruchamia demonstracyjny chat na fikcyjnych danych.
  Telegram i sync są wyłączone. `--live-agent` świadomie włącza model.
- `dev.py --snapshot <katalog>` tworzy nową kopię roboczą backupu, sprawdza
  integralność i usuwa stan kolejki/transportu z kopii, aby nie odtworzyć zleceń.
- Backup produkcji pobiera właściciel dotychczasową procedurą. Nie wykonywać
  samowolnie poleceń na serwerze ani nie podłączać testów do działającej bazy.
- Dane pacjenta, `.env`, tokeny i rzeczywiste rozmowy nie mogą trafić do Git.
  Publiczna dokumentacja i testy mają używać danych fikcyjnych.
- Nie kopiować samego aktywnego pliku SQLite jako gwarantowanego backupu;
  uwzględnić WAL, użyć wspieranego backupu i zachować dokumenty.
- Testy Python: `python -m pytest -q`; frontend: `node --check web/app.js`
  i `node --test tests/web_*.test.mjs`. Testy kontenera: [WEB.md](WEB.md).
- Przechodzące testy na atrapach nie potwierdzają działania integracji ani
  wersji produkcyjnej. Zmiany kodu, publikacja obrazu i wdrożenie to osobne etapy.

Szczegółowe zmienne modeli i przykłady konfiguracji: [README.md](README.md#konfiguracja).
