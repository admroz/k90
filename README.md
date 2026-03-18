# k90 — Osobisty asystent zdrowotny

Agent AI działający jako osobisty lekarz rodzinny, diabetolog i dietetyk. Komunikuje się przez Signal, ma dostęp do danych z Garmin Connect i bazy danych zdrowotnych, monitoruje trendy i pomaga zarządzać dietą.

## Funkcje

- Odpowiada na wiadomości Signal
- Analizuje dane zdrowotne: ciśnienie, waga, sen, HRV, Body Battery, aktywności
- Pobiera dane z Garmin Connect i importuje do SQLite
- Loguje posiłki, w tym na podstawie zdjęć
- Przechowuje wyniki badań laboratoryjnych i analizuje trendy
- Prowadzi pliki medyczne pacjenta (profil, wywiad, dieta, analiza)
- Generuje i aktualizuje podsumowanie kluczowych danych pacjenta (~500 tokenów)
- Obsługuje komendy slash bez udziału LLM: `/status`, `/debug`, `/help`

## Stack

- **Agent:** Python + LiteLLM (konfigurowalny model przez `.env`)
- **Komunikacja:** Signal (signal-cli-rest-api przez WebSocket)
- **Baza danych:** SQLite (historia rozmów, dane zdrowotne, podsumowanie pacjenta)
- **Dane Garmin:** `fetch_garmin.py` → CSV → `migrate_csv_to_sqlite.py` → SQLite
- **Deployment:** Docker Compose (Synology NAS lub lokalnie)

## Struktura

```
k90/
├── agent.py                  # pętla LiteLLM + historia rozmów z SQLite
├── server.py                 # Signal WebSocket listener
├── summary.py                # generowanie podsumowania pacjenta
├── system_prompt.py          # ładowanie promptu (data/ override lub repo)
├── system_prompt.md          # ogólny prompt systemowy (bez danych osobowych)
├── fetch_garmin.py           # pobieranie danych z Garmin Connect
├── migrate_csv_to_sqlite.py  # import CSV → SQLite
├── tools/
│   ├── health.py             # dane zdrowotne z SQLite
│   ├── lab.py                # wyniki badań laboratoryjnych
│   ├── diet.py               # logowanie posiłków
│   ├── garmin.py             # sync Garmin (fetch + migrate)
│   ├── patient.py            # pliki .md pacjenta
│   ├── commands.py           # komendy slash bez LLM
│   └── db.py                 # połączenie SQLite + init_db()
├── data/                     # dane persystentne — gitignored, wolumin Docker
│   ├── k90.db                # główna baza danych
│   ├── .garmin_tokens/       # tokeny OAuth Garmin
│   ├── signal/               # dane konta Signal
│   ├── pacjent.md            # profil pacjenta
│   ├── wywiad.md             # wywiad medyczny
│   ├── analiza.md            # analiza wyników badań
│   ├── dieta.md              # plan diety
│   ├── tydzien.md            # menu posiłków
│   └── *.csv                 # eksporty Garmin (pośredni format)
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .env                      # klucze API i dane logowania (gitignored)
```

## Konfiguracja

Skopiuj `.env.example` do `.env` i uzupełnij:

```bash
cp .env.example .env
```

Kluczowe zmienne:

```
AGENT_MODEL=claude-haiku-4-5-20251001   # model do konwersacji
SUMMARY_MODEL=claude-sonnet-4-6         # model do podsumowania pacjenta
ANTHROPIC_API_KEY=...
HISTORY_MESSAGES=10                     # ile ostatnich par wiadomości w kontekście
SUMMARY_MAX_AGE_DAYS=7                  # auto-odświeżenie podsumowania po X dniach
SIGNAL_PHONE_NUMBER=+48...
SIGNAL_ALLOWED_SENDER=+48...
GARMIN_EMAIL=...
GARMIN_PASSWORD=...
```

Komendy slash dostępne przez Signal:

- `/status` — szybkie podsumowanie: waga, kalorie z ostatnich dni, ostatnia aktywność
- `/debug` — liczba zapytań, tokeny i orientacyjny koszt
- `/help` — lista dostępnych komend

## Uruchomienie lokalne

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py   # CLI do testowania
```

## Docker

```bash
docker compose up -d
docker compose logs -f agent
```

## Deployment na Synology

Zobacz [DEPLOY.md](DEPLOY.md).

## Dane pacjenta

Cały folder `data/` jest gitignored i montowany jako wolumin Dockera. Przeniesienie na nowy serwer = skopiowanie `data/` i `.env`.

Plik `system_prompt.md` z repo jest ogólny — bez danych osobowych. Możesz nadpisać go plikiem `data/system_prompt.md`, który nie trafi do gita.
