# k90 — architektura projektu

## Frontend WWW

- `webapp.py`, `web_runtime.py`, `web_data.py`: API FastAPI, trwała kolejka wiadomości,
  jeden worker agenta oraz kontrolowany odczyt danych i dokumentów.
- `web/`: statyczny frontend bez CDN i bez wymaganego serwera Node.
- `telegram_adapter.py`: transport Telegrama korzystający z wewnętrznego API backendu.
- `supervisord.conf`: jeden kontener, niezależne procesy backendu i adaptera.
- `dev.py --snapshot <katalog>`: lokalna kopia robocza pobranego backupu; Telegram
  i sync źródeł wyłączone. Domyślnie chat demonstracyjny; `--live-agent` włącza LLM.
- Pobieranie danych z NAS jest ręczne (istniejący backup + SCP/File Station).
  Nie uruchamiać na NAS własnych skryptów tworzących snapshot.
- Procedury, testy i ograniczenia pierwszej wersji: `WEB.md`.
- `server.py` pozostaje starszym trybem Telegram-only. Nie uruchamiać go razem
  z nowym adapterem dla tego samego bota.

Osobisty asystent zdrowotny działający przez Telegram. Odpowiada na wiadomości, pobiera dane z Garmin Connect i zarządza bazą danych zdrowotnych.

## Stack

- **Agent:** Python + LiteLLM (własna pętla tool-use, domyślnie OpenAI GPT)
- **Komunikacja:** Telegram Bot API przez long polling
- **Baza danych:** SQLite (`data/k90.db`) — dane zdrowotne, historia rozmów, podsumowanie pacjenta
- **Dane Garmin:** `fetch_garmin.py` → bezpośredni sync do SQLite
- **Deployment:** Docker Compose (Lenovo M900, Intel/AMD x86-64). CI buduje `linux/amd64`; konfiguracja ARM64 dla Synology jest zachowana, ale wyłączona.

## Struktura projektu

```
k90/
├── agent.py                  # pętla LiteLLM + historia rozmów (SQLite)
├── server.py                 # Telegram long-polling listener + dispatcher
├── summary.py                # podsumowanie pacjenta: generowanie i zarządzanie
├── system_prompt.py          # ładowanie promptu (data/ override lub repo)
├── system_prompt.md          # ogólny prompt bez danych osobowych
├── fetch_garmin.py           # OAuth + pobieranie danych z Garmin Connect → SQLite
├── migrate_csv_to_sqlite.py  # legacy import wszystkich CSV → SQLite
├── tools/
│   ├── health.py             # 7 narzędzi: BP, waga, sen, HRV, Battery, aktywności, metryki
│   ├── lab.py                # wyniki badań laboratoryjnych
│   ├── diet.py               # log_meal, get_recent_meals, delete_meal
│   ├── garmin.py             # sync_garmin_data (direct-to-db)
│   ├── patient.py            # read_patient_file, update_patient_file
│   ├── commands.py           # /status, /debug, /update, /summary, /help bez LLM
│   └── db.py                 # get_conn(), init_db(), rows_to_list()
├── data/                     # gitignored, montowane jako wolumin Docker
└── Dockerfile                # multi-stage: base (deps) + app (kod)
```

## Przepływ wiadomości

```
Telegram → long polling → server.py → agent.py → LiteLLM
                                     ↓            ↓
                              SQLite history   tool calls
                                     ↓            ↓
                              save response   tools/
                                     ↓
                              Telegram ← response
```

## Zarządzanie kontekstem

Każde zapytanie do LLM zawiera:
1. **System prompt** — rola i zasady (z `system_prompt.md`)
2. **Podsumowanie pacjenta** — krótki rekord faktów medycznych (z `patient_summary` w SQLite)
3. **Historia rozmów** — ostatnie N par wiadomości (konfigurowalnie przez `HISTORY_MESSAGES`)
4. **Wiadomość użytkownika** — tekst lub tekst + obraz (Telegram photo/document)

## Narzędzia agenta (16 total)

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
| `update_meal(...)` | Aktualizacja zapisanego posiłku |
| `get_recent_meals(days)` | Historia posiłków |
| `delete_meal(id)` | Usunięcie posiłku |
| `sync_garmin_data()` | Sync danych Garmin → SQLite |
| `read_patient_file(filename)` | Odczyt pliku .md pacjenta |
| `update_patient_file(filename, content)` | Zapis pliku .md pacjenta |
| `refresh_patient_summary()` | Odświeżenie podsumowania pacjenta |

## Komendy slash (bez LLM)

| Komenda | Opis |
|---------|------|
| `/status` | Szybkie podsumowanie: waga, kalorie z ostatnich dni, ostatnia aktywność |
| `/debug` | Liczba zapytań, tokeny i stan summary |
| `/update` | Synchronizacja Garmin bez LLM |
| `/summary` | Podgląd aktualnego patient summary |
| `/help` | Lista dostępnych komend |

## Podsumowanie pacjenta

Singleton w tabeli `patient_summary` (SQLite). Generowane przez `SUMMARY_MODEL` (domyślnie `gpt-5.4`) na podstawie wszystkich plików `.md` z `data/`.

Odświeżane gdy:
- Startup i podsumowanie starsze niż `SUMMARY_MAX_AGE_DAYS` dni
- Po wywołaniu `sync_garmin_data` lub `update_patient_file`
- Na żądanie przez tool `refresh_patient_summary()`

## Historia rozmów

Tabela `conversations` (SQLite). Każda wiadomość jest zapisana ze stabilnym `user_id` ustawianym przez `CONVERSATION_USER_ID`. Do kontekstu trafia ostatnie `HISTORY_MESSAGES` par wiadomości.

## Schemat SQLite

Dane zdrowotne (wypełniane przez `migrate_csv_to_sqlite.py`):
`cisnienie`, `waga`, `sen`, `aktywnosci`, `hrv`, `body_battery`, `metryki_dzienne`, `wyniki_lab`, `posilki`

Dane agenta (tworzone przez `init_db()`):
`conversations`, `patient_summary`

## Zmienne środowiskowe

| Zmienna | Opis | Domyślnie |
|---------|------|-----------|
| `AGENT_MODEL` | Model do konwersacji | `gpt-5.4` |
| `SUMMARY_MODEL` | Model do podsumowania pacjenta | `gpt-5.4` |
| `HISTORY_MESSAGES` | Liczba par wiadomości w kontekście | `10` |
| `SUMMARY_MAX_AGE_DAYS` | Auto-odświeżenie po X dniach | `7` |
| `DB_PATH` | Ścieżka do bazy SQLite | `/data/k90.db` |
| `DATA_DIR` | Katalog z plikami pacjenta | `/data` |
| `TELEGRAM_BOT_TOKEN` | Token bota z `@BotFather` | — |
| `TELEGRAM_ALLOWED_USER_ID` | Whitelisted numeryczny Telegram user ID | — |
| `CONVERSATION_USER_ID` | Stabilny klucz historii rozmowy | `owner` |
| `OPENAI_API_KEY` | Klucz OpenAI | — |
| `ANTHROPIC_API_KEY` | Klucz Anthropic (opcjonalnie) | — |
| `GEMINI_API_KEY` | Klucz Google Gemini (opcjonalnie) | — |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | Dane logowania Garmin | — |
| `LIBRE_ENABLED` | Włącza pobieranie i synchronizację Libre | `true` |

Modele GPT-5.6 działają obecnie przez Chat Completions z `reasoning_effort=none`, aby zachować function calling. Włączenie reasoning dla tych modeli wymaga migracji pętli agenta do Responses API.
