# k90 — architektura projektu

Osobisty asystent zdrowotny działający przez Signal. Odpowiada na wiadomości, pobiera dane z Garmin Connect i zarządza bazą danych zdrowotnych.

## Stack

- **Agent:** Python + LiteLLM (własna pętla tool-use, ~100 linii)
- **Komunikacja:** Signal (signal-cli-rest-api przez WebSocket)
- **Baza danych:** SQLite (`data/k90.db`) — dane zdrowotne, historia rozmów, podsumowanie pacjenta
- **Dane Garmin:** `fetch_garmin.py` → CSV → `migrate_csv_to_sqlite.py` → SQLite
- **Deployment:** Docker Compose (Synology DS223 lub lokalnie)

## Struktura projektu

```
k90/
├── agent.py                  # pętla LiteLLM + historia rozmów (SQLite)
├── server.py                 # Signal WebSocket listener + dispatcher
├── summary.py                # podsumowanie pacjenta: generowanie i zarządzanie
├── system_prompt.py          # ładowanie promptu (data/ override lub repo)
├── system_prompt.md          # ogólny prompt bez danych osobowych
├── fetch_garmin.py           # OAuth + pobieranie danych z Garmin Connect → CSV
├── migrate_csv_to_sqlite.py  # import wszystkich CSV → SQLite
├── tools/
│   ├── health.py             # 7 narzędzi: BP, waga, sen, HRV, Battery, aktywności, metryki
│   ├── lab.py                # wyniki badań laboratoryjnych
│   ├── diet.py               # log_meal, get_recent_meals, delete_meal
│   ├── garmin.py             # sync_garmin_data (orchestracja fetch + migrate)
│   ├── patient.py            # read_patient_file, update_patient_file
│   └── db.py                 # get_conn(), init_db(), rows_to_list()
├── data/                     # gitignored, montowane jako wolumin Docker
└── Dockerfile                # multi-stage: base (deps) + app (kod)
```

## Przepływ wiadomości

```
Signal → WebSocket → server.py → agent.py → LiteLLM
                                     ↓            ↓
                              SQLite history   tool calls
                                     ↓            ↓
                              save response   tools/
                                     ↓
                              Signal ← response
```

## Zarządzanie kontekstem

Każde zapytanie do LLM zawiera:
1. **System prompt** — rola i zasady (z `system_prompt.md`)
2. **Podsumowanie pacjenta** — ~500 tokenów kluczowych danych medycznych (z `patient_summary` w SQLite)
3. **Historia rozmów** — ostatnie N wiadomości (konfigurowalnie przez `HISTORY_MESSAGES`)
4. **Wiadomość użytkownika** — tekst lub tekst + obraz (Signal attachment)

## Narzędzia agenta (15 total)

| Narzędzie | Opis |
|-----------|------|
| `get_blood_pressure(days)` | Pomiary ciśnienia |
| `get_weight_trend(days)` | Historia wagi + BMI |
| `get_sleep_stats(days)` | Fazy snu, score, SpO2 |
| `get_activities(days, type)` | Aktywności fizyczne |
| `get_hrv(days)` | Heart rate variability |
| `get_body_battery(days)` | Garmin Body Battery |
| `get_daily_metrics(days)` | RHR, stres, oddech |
| `get_lab_results(category, test)` | Wyniki badań lab |
| `log_meal(...)` | Zapis posiłku |
| `get_recent_meals(days)` | Historia posiłków |
| `delete_meal(id)` | Usunięcie posiłku |
| `sync_garmin_data()` | Sync danych Garmin → SQLite |
| `read_patient_file(filename)` | Odczyt pliku .md pacjenta |
| `update_patient_file(filename, content)` | Zapis pliku .md pacjenta |
| `refresh_patient_summary()` | Odświeżenie podsumowania pacjenta |

## Podsumowanie pacjenta

Singleton w tabeli `patient_summary` (SQLite). Generowane przez `SUMMARY_MODEL` (domyślnie sonnet) na podstawie wszystkich plików `.md` z `data/`.

Odświeżane gdy:
- Startup i podsumowanie starsze niż `SUMMARY_MAX_AGE_DAYS` dni
- Po wywołaniu `sync_garmin_data` lub `update_patient_file`
- Na żądanie przez tool `refresh_patient_summary()`

## Historia rozmów

Tabela `conversations` (SQLite). Każda wiadomość zapisana z `user_id` (numer telefonu z Signal). Do kontekstu trafia ostatnie `HISTORY_MESSAGES` par wiadomości.

## Schemat SQLite

Dane zdrowotne (wypełniane przez `migrate_csv_to_sqlite.py`):
`cisnienie`, `waga`, `sen`, `aktywnosci`, `hrv`, `body_battery`, `metryki_dzienne`, `wyniki_lab`, `posilki`

Dane agenta (tworzone przez `init_db()`):
`conversations`, `patient_summary`

## Zmienne środowiskowe

| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `AGENT_MODEL` | Model do konwersacji | `claude-haiku-4-5-20251001` |
| `SUMMARY_MODEL` | Model do podsumowania pacjenta | `claude-sonnet-4-6` |
| `HISTORY_MESSAGES` | Liczba wiadomości w kontekście | `10` |
| `SUMMARY_MAX_AGE_DAYS` | Auto-odświeżenie po X dniach | `7` |
| `DB_PATH` | Ścieżka do bazy SQLite | `/data/k90.db` |
| `DATA_DIR` | Katalog z plikami pacjenta | `/data` |
| `SIGNAL_PHONE_NUMBER` | Numer bota Signal | — |
| `SIGNAL_ALLOWED_SENDER` | Whitelisted numer użytkownika | — |
| `ANTHROPIC_API_KEY` | Klucz Anthropic | — |
| `GEMINI_API_KEY` | Klucz Google Gemini (opcjonalnie) | — |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | Dane logowania Garmin | — |
