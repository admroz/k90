# k90 — Osobisty asystent zdrowotny

Osobisty asystent AI do rozmów o zdrowiu i diecie. Udostępnia wspólną rozmowę
przez Telegram i panel WWW, korzysta z Garmin Connect, LibreLinkUp i lokalnej
bazy danych. Przy każdej rozmowie buduje kontekst z zapisanych pomiarów,
posiłków i dokumentów. Nie zastępuje opieki medycznej.

## Funkcje

- Odpowiada na prywatne wiadomości Telegram
- Panel WWW: wspólny chat, dashboard, posiłki z wyborem dnia, regeneracja,
  aktywność oraz podgląd tabel i dokumentów
- Analizuje dane zdrowotne: ciśnienie, waga, sen, HRV, Body Battery, aktywności
- Pobiera dane z Garmin Connect i synchronizuje je bezpośrednio do SQLite
- Pobiera dostępne odczyty glukozy z LibreLinkUp (opcjonalnie)
- Loguje posiłki, w tym na podstawie zdjęć
- Przechowuje wyniki badań laboratoryjnych i analizuje trendy
- Prowadzi pliki medyczne pacjenta (profil, wywiad, dieta, analiza)
- Generuje i aktualizuje krótkie patient summary w formie rekordu faktów medycznych
- Obsługuje komendy slash poza pętlą rozmowy: `/status`, `/debug`, `/update`,
  `/summary`, `/backup`, `/help`; `/update` może wywołać model do odświeżenia summary

## Stack

- **Agent:** Python, własna pętla narzędzi; LiteLLM / Chat Completions lub
  bezpośrednie OpenAI Responses API dla rodziny GPT-6.1 Sol
- **Backend:** FastAPI i trwała kolejka SQLite, jeden worker agenta
- **Komunikacja:** statyczny frontend WWW oraz Telegram Bot API przez long polling
- **Baza danych:** SQLite (historia, dane zdrowotne, summary, kolejka i stan transportu)
- **Źródła:** `fetch_garmin.py` i `fetch_libre.py` → bezpośredni sync do SQLite
- **Procesy:** backend WWW i adapter Telegrama w jednym kontenerze pod Supervisorem
- **Deployment:** Docker Compose (Lenovo M900 / Intel/AMD x86-64; build ARM64 wyłączony)

## Struktura

```
k90/
├── agent.py                  # pętla modelu/narzędzi + historia rozmów z SQLite
├── responses_api.py          # adapter OpenAI Responses dla rodziny Sol
├── webapp.py                 # FastAPI: logowanie, chat, dashboard i dane
├── web_runtime.py            # trwała kolejka i jeden worker agenta
├── web_data.py               # odczyty danych do panelu WWW
├── web/                      # statyczny frontend bez CDN
├── telegram_adapter.py       # Telegram → wewnętrzne API backendu
├── server.py                 # starszy, alternatywny tryb Telegram-only
├── dev.py                    # lokalny podgląd na fikcyjnych danych lub kopii backupu
├── summary.py                # generowanie podsumowania pacjenta
├── system_prompt.py          # ładowanie promptu (data/ override lub repo)
├── system_prompt.md          # ogólny prompt systemowy (bez danych osobowych)
├── fetch_garmin.py           # pobieranie danych z Garmin Connect → SQLite
├── fetch_libre.py            # pobieranie glukozy z LibreLinkUp → SQLite
├── migrate_csv_to_sqlite.py  # legacy import CSV → SQLite
├── tools/
│   ├── health.py             # dane zdrowotne z SQLite
│   ├── lab.py                # wyniki badań laboratoryjnych
│   ├── diet.py               # logowanie posiłków
│   ├── garmin.py             # sync Garmin direct-to-db
│   ├── libre.py              # sync Libre i kontrola włączenia źródła
│   ├── context.py            # wyciąg bieżących danych do kontekstu rozmowy
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
│   └── *.csv                 # opcjonalne historyczne eksporty/importy
├── docs/MEMORY_ARCHITECTURE.md # plan pamięci długoterminowej (niezaimplementowany)
├── supervisord.conf          # osobne procesy backendu i Telegrama
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .env                      # klucze API i dane logowania (gitignored)
```

## Architektura i pamięć

```text
WWW ──────────────────────┐
Telegram → adapter HTTP ──┴→ FastAPI → kolejka SQLite → worker → agent
                                                              ↕
                                                   model i narzędzia
                                                              ↕
                                                   SQLite + dokumenty
```

Oba kanały używają jednej historii `CONVERSATION_USER_ID`. Agent dostaje
domyślnie ostatnie 10 par wiadomości, siedmioliniowe summary z pięciu plików
pacjenta oraz bieżący wyciąg danych. Starsza historia pozostaje w SQLite,
ale obecnie nie jest semantycznie wyszukiwana. Summary nie powstaje z rozmów.

**Plan rozwoju:** Hindsight jako opcjonalny, wymienialny indeks kontekstu rozmów,
przy zachowaniu pełnych źródeł lokalnie, z filtrem prywatności i lokalnym fallbackiem.
To kierunek rozwoju, nie działająca integracja. Założenia i kryteria odbioru:
[Pamięć k90](docs/MEMORY_ARCHITECTURE.md). Bieżąca architektura: [AGENTS.md](AGENTS.md),
zadania: [TODO.md](TODO.md).

Synchronizacja Garmin/Libre działa na żądanie oraz przy rozmowie, gdy brakuje
udanego pobrania danego dnia. Przycisk WWW „Pobierz Garmin” pomija model, Libre
i summary. Nie ma niezależnego harmonogramu ciągłego monitoringu; data ostatniego
pomiaru może być starsza niż data zbudowania kontekstu.

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

GPT-6.1 Sol automatycznie korzysta z Responses API, z obsługą narzędzi i zdjęć.
Właściciel włącza przesyłanie NOWYCH zdjęć posiłków przez
`K90_ALLOW_MODEL_IMAGES=true` (domyślnie `false`). Historyczne zdjęcia nigdy nie są
ponownie przesyłane: kontekst zachowuje tekst i analizę asystenta oraz znacznik
pominięcia obrazu. Zgoda nie obejmuje obrazów w HS ani anonimizacji obrazu/EXIF;
szczegóły: [polityka zdjęć](docs/OPERATIONS_MEMORY_AUTH.md).
Starsze modele oraz pozostali dostawcy zachowują dotychczasową obsługę przez
LiteLLM / Chat Completions; GPT-5.6 nadal używa `reasoning_effort=none`.
Model rozmowy i podsumowania wybierasz niezależnie, np.:

```dotenv
AGENT_MODEL=gpt-6.1-sol
SUMMARY_MODEL=gpt-5.4
AGENT_REASONING_EFFORT=low
AGENT_MAX_OUTPUT_TOKENS=8192
```

Obsługiwany jest także zapis `openai/gpt-6.1-sol`. Dla Sol dostępne poziomy
reasoning to `low` (domyślny w k90), `medium`, `high`, `xhigh` i `max`.
`AGENT_MAX_OUTPUT_TOKENS` obejmuje reasoning i tekst łącznie. Przerwana odpowiedź
nie wykonuje zawartych w niej wywołań narzędzi ani nie zapisuje częściowej rozmowy.
Wywołania narzędzi z wcześniejszych, zakończonych rund mogą już być wykonane.

Możesz też ustawić `SUMMARY_MODEL=gpt-6.1-sol`; wtedy obowiązują osobne
`SUMMARY_REASONING_EFFORT=low` i `SUMMARY_MAX_OUTPUT_TOKENS=4096`. Dotychczasowy
`SUMMARY_MAX_TOKENS=600` dotyczy podsumowań przez Chat Completions.
Zmiany modeli wymagają `docker compose up -d agent`; powrót do starszego modelu
polega na zmianie odpowiedniej zmiennej. Jedna instancja używa jednego modelu
rozmowy i jednego modelu podsumowania, wspólnie dla WWW i Telegrama.

Historia pozostaje w SQLite. Responses działa z `store=false`; zaszyfrowane
elementy reasoning są przekazywane pomiędzy wywołaniami narzędzi w ramach jednego
zapytania i nie są zapisywane do historii. Dostępność modelu zależy od konta API.
Zasady API: [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
i [migracja do Responses](https://developers.openai.com/api/docs/guides/migrate-to-responses).

Komendy slash dostępne przez Telegram i wspólny backend WWW:

- `/status` — szybkie podsumowanie: waga, kalorie z ostatnich dni, ostatnia aktywność
- `/debug` — liczba zapytań, tokeny i stan summary
- `/update` — synchronizacja Garmin i włączonego Libre; zmiany Garmin mogą
  uruchomić odświeżenie summary przez model
- `/summary` — pokazuje aktualne patient summary
- `/backup` — tworzy snapshot SQLite w `data/backups/`
- `/help` — lista dostępnych komend

## Uruchomienie lokalne

Frontend WWW można uruchomić lokalnie bez Dockera i bez Telegrama:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python dev.py
# Lub na osobnej kopii backupu pobranego z NAS:
.venv/bin/python dev.py --snapshot data/local-import.20260920
```

Adres: <http://127.0.0.1:8000>, lokalne hasło: `k90-local-preview`.
Domyślnie chat jest demonstracyjny; `--live-agent` włącza model z `.env`.
Szczegóły izolacji danych, architektury i testów: [WEB.md](WEB.md).

Starszy tryb Telegram-only i CLI:

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

Nowy obraz uruchamia backend WWW i adapter Telegrama w jednym kontenerze.
Wymaga także `WEB_PASSWORD` (minimum 12 znaków); szczegóły HTTPS/LAN w [WEB.md](WEB.md).

1. Napisz do `@BotFather`, wywołaj `/newbot` i wpisz otrzymany token jako `TELEGRAM_BOT_TOKEN`.
2. Jeśli nie znasz swojego numerycznego Telegram user ID, uruchom bota bez `TELEGRAM_ALLOWED_USER_ID` i wyślij mu wiadomość. W logu `telegram.reject` pojawi się `user_id`.
3. Ustaw ten numer jako `TELEGRAM_ALLOWED_USER_ID` i zrestartuj usługę `agent`.
4. W prywatnej rozmowie z botem sprawdź kolejno `/help` oraz zwykłą wiadomość wymagającą odpowiedzi modelu.

Bot celowo ignoruje grupy oraz wszystkich użytkowników poza skonfigurowanym właścicielem.
Domyślne `CONVERSATION_USER_ID=owner` rozpoczyna nową historię czatu. Aby kontynuować historię z Signal, ustaw tę zmienną na dotychczasowy `user_id` zapisany w tabeli `conversations`.

Jeśli czujnik Libre nie jest używany, ustaw `LIBRE_ENABLED=false`. Wyłącza to auto-sync, ręczny sync przez `/update` i wywołania syncu przez agenta, ale nie usuwa historycznych pomiarów z SQLite.

## Deployment na Lenovo / Docker

Zobacz [DEPLOY.md](DEPLOY.md).

## Dane pacjenta

Folder `data/` jest gitignored i montowany jako wolumin Dockera. Przeniesienie
na nowy serwer wymaga spójnego backupu bazy SQLite, dokumentów i konfiguracji.
Nie kopiuj samego aktywnego `k90.db`: najnowsze zapisy mogą pozostawać w WAL.
Komenda `/backup` tworzy snapshot bazy; dokumenty i `.env` trzeba zabezpieczyć
oddzielnie. Pełna procedura: [DEPLOY.md](DEPLOY.md).

Plik `system_prompt.md` z repo jest ogólny — bez danych osobowych. Możesz nadpisać go plikiem `data/system_prompt.md`, który nie trafi do gita.
