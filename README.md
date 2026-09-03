# k90 — Osobisty asystent zdrowotny

Agent AI działający jako osobisty lekarz rodzinny, diabetolog i dietetyk. Komunikuje się przez Telegram, ma dostęp do danych z Garmin Connect i bazy danych zdrowotnych, monitoruje trendy i pomaga zarządzać dietą. Używa świeżego kontekstu operacyjnego z ostatnich dni przy każdej rozmowie.

## Funkcje

- Odpowiada na prywatne wiadomości Telegram
- Analizuje dane zdrowotne: ciśnienie, waga, sen, HRV, Body Battery, aktywności
- Pobiera dane z Garmin Connect i synchronizuje je bezpośrednio do SQLite
- Loguje posiłki, w tym na podstawie zdjęć
- Przechowuje wyniki badań laboratoryjnych i analizuje trendy
- Prowadzi pliki medyczne pacjenta (profil, wywiad, dieta, analiza)
- Generuje i aktualizuje krótkie patient summary w formie rekordu faktów medycznych
- Obsługuje komendy slash bez udziału LLM: `/status`, `/debug`, `/update`, `/summary`, `/backup`, `/help`

## Stack

- **Agent:** Python + LiteLLM (domyślnie OpenAI GPT przez `.env`)
- **Komunikacja:** Telegram Bot API przez long polling
- **Baza danych:** SQLite (historia rozmów, dane zdrowotne, podsumowanie pacjenta)
- **Dane Garmin:** `fetch_garmin.py` → bezpośredni sync do SQLite
- **Deployment:** Docker Compose (Synology NAS lub lokalnie)

## Struktura

```
k90/
├── agent.py                  # pętla LiteLLM + historia rozmów z SQLite
├── server.py                 # Telegram long-polling listener
├── summary.py                # generowanie podsumowania pacjenta
├── system_prompt.py          # ładowanie promptu (data/ override lub repo)
├── system_prompt.md          # ogólny prompt systemowy (bez danych osobowych)
├── fetch_garmin.py           # pobieranie danych z Garmin Connect → SQLite
├── migrate_csv_to_sqlite.py  # legacy import CSV → SQLite
├── tools/
│   ├── health.py             # dane zdrowotne z SQLite
│   ├── lab.py                # wyniki badań laboratoryjnych
│   ├── diet.py               # logowanie posiłków
│   ├── garmin.py             # sync Garmin direct-to-db
│   ├── patient.py            # pliki .md pacjenta
│   ├── commands.py           # komendy slash bez LLM
│   └── db.py                 # połączenie SQLite + init_db()
├── data/                     # dane persystentne — gitignored, wolumin Docker
│   ├── k90.db                # główna baza danych
│   ├── .garmin_tokens/       # tokeny OAuth Garmin
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
AGENT_MODEL=gpt-5.4                    # model do konwersacji
SUMMARY_MODEL=gpt-5.4                  # model do patient summary
OPENAI_API_KEY=...
HISTORY_MESSAGES=10                    # ile ostatnich par wiadomości w kontekście
SUMMARY_MAX_AGE_DAYS=7                 # auto-odświeżenie podsumowania po X dniach
SUMMARY_MAX_TOKENS=600                 # limit output dla patient summary
TELEGRAM_BOT_TOKEN=...                # token otrzymany od @BotFather
TELEGRAM_ALLOWED_USER_ID=...          # numeryczny Telegram user ID właściciela
CONVERSATION_USER_ID=owner            # stabilny klucz historii rozmowy
GARMIN_EMAIL=...
GARMIN_PASSWORD=...
LIBRE_ENABLED=true                     # false wyłącza pobieranie danych Libre
```

Komendy slash dostępne przez Telegram:

- `/status` — szybkie podsumowanie: waga, kalorie z ostatnich dni, ostatnia aktywność
- `/debug` — liczba zapytań, tokeny i stan summary
- `/update` — synchronizacja Garmin bez LLM
- `/summary` — pokazuje aktualne patient summary
- `/backup` — tworzy snapshot SQLite w `data/backups/`
- `/help` — lista dostępnych komend

## Uruchomienie lokalne

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py  # bot Telegram przez long polling
# albo: python agent.py  # tekstowy tryb CLI bez Telegrama
```

## Docker

```bash
docker compose up -d
docker compose logs -f agent
```

### Pierwsze uruchomienie Telegrama

1. Napisz do `@BotFather`, wywołaj `/newbot` i wpisz otrzymany token jako `TELEGRAM_BOT_TOKEN`.
2. Jeśli nie znasz swojego numerycznego Telegram user ID, uruchom bota bez `TELEGRAM_ALLOWED_USER_ID` i wyślij mu wiadomość. W logu `telegram.reject` pojawi się `user_id`.
3. Ustaw ten numer jako `TELEGRAM_ALLOWED_USER_ID` i zrestartuj usługę `agent`.
4. W prywatnej rozmowie z botem sprawdź kolejno `/help` oraz zwykłą wiadomość wymagającą odpowiedzi modelu.

Bot celowo ignoruje grupy oraz wszystkich użytkowników poza skonfigurowanym właścicielem.
Domyślne `CONVERSATION_USER_ID=owner` rozpoczyna nową historię czatu. Aby kontynuować historię z Signal, ustaw tę zmienną na dotychczasowy `user_id` zapisany w tabeli `conversations`.

Jeśli czujnik Libre nie jest używany, ustaw `LIBRE_ENABLED=false`. Wyłącza to auto-sync, ręczny sync przez `/update` i wywołania syncu przez agenta, ale nie usuwa historycznych pomiarów z SQLite.

## Deployment na Synology

Zobacz [DEPLOY.md](DEPLOY.md).

## Dane pacjenta

Cały folder `data/` jest gitignored i montowany jako wolumin Dockera. Przeniesienie na nowy serwer = skopiowanie `data/` i `.env`.

Plik `system_prompt.md` z repo jest ogólny — bez danych osobowych. Możesz nadpisać go plikiem `data/system_prompt.md`, który nie trafi do gita.
