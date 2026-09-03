# Deployment na Synology NAS

## Architektura

- Obraz budowany automatycznie przez GitHub Actions (push do `main`) na natywnym runnerze ARM64
- Obraz publikowany przez GitHub Actions na Docker Hub: `admroz/k90:latest`
- Dane (`data/` + `.env`) przenoszone raz ręcznie, potem trzymane na Synology
- Komunikacja przez Telegram Bot API w trybie long polling; bez publicznego portu i dodatkowego kontenera

## Wymagania wstępne (jednorazowo)

1. Publiczny obraz `admroz/k90:latest` nie wymaga logowania do rejestru na Synology.

## Jednorazowa migracja danych na Synology

```bash
# 1. Skopiuj dane i konfigurację
rsync -avz ./data/ synology:/volume1/docker/k90/data/
scp .env synology:/volume1/docker/k90/

# 2. Na Synology — dostosuj .env:
#   DATA_PATH=/volume1/docker/k90/data
#   AGENT_IMAGE=admroz/k90:latest
#   TELEGRAM_BOT_TOKEN=token_z_BotFather
#   TELEGRAM_ALLOWED_USER_ID=numeryczny_id_wlasciciela

# 3. Uruchom
cd /volume1/docker/k90
docker compose up -d --remove-orphans
```

Jeśli masz jeszcze historyczną bazę `kadencja90.db`, zmigruj ją ręcznie poza tym procesem i zachowaj kopię bezpieczeństwa. Aktualna aplikacja używa wyłącznie `k90.db`.

## Build obrazu

Build i push odbywa się automatycznie przez GitHub Actions przy każdym pushu do `main`.
Możesz też uruchomić ręcznie z zakładki Actions → "Build & Push Docker image" → Run workflow.

## Aktualizacja po zmianie kodu

```bash
# Push do main wyzwala build — po zakończeniu (~3-5 min) na Synology:
docker compose pull agent && docker compose up -d --remove-orphans
```

## Co nie wymaga rebuildu obrazu

- Zmiana `system_prompt.md` — edytuj `data/system_prompt.md` i `docker compose restart agent`
- Zmiana modelu (`AGENT_MODEL`, `SUMMARY_MODEL`) lub `OPENAI_API_KEY` — edytuj `.env` i `docker compose up -d agent`
- Zmiana tokenu lub whitelisty Telegrama — edytuj `.env` i `docker compose up -d agent`
- Zmiana plików pacjenta (`pacjent.md`, `dieta.md` itp.) — edytuj w `data/`, restart opcjonalny

## Zmienne środowiskowe

| Zmienna | Lokalnie | Synology |
|---------|----------|----------|
| `DATA_PATH` | (domyślnie `./data`) | `/volume1/docker/k90/data` |
| `AGENT_IMAGE` | `admroz/k90:latest` | `admroz/k90:latest` |
| `DB_PATH` | (domyślnie `./data/k90.db`) | `/data/k90.db` |
| `TELEGRAM_BOT_TOKEN` | token z `@BotFather` | token z `@BotFather` |
| `TELEGRAM_ALLOWED_USER_ID` | ID właściciela | ID właściciela |
| `LIBRE_ENABLED` | `true` lub `false` | `true` lub `false` |

## Weryfikacja

```bash
# Lokalnie
docker compose up -d
docker compose logs -f agent

# Oczekiwany wpis po starcie:
# telegram.connected bot=@nazwa_bota

# Test transportu bez LLM: wyślij /help
# Test transportu z LLM: wyślij zwykłą wiadomość

# Sprawdź tabele SQLite
sqlite3 data/k90.db ".tables"

# Sprawdź podsumowanie pacjenta
sqlite3 data/k90.db "SELECT updated_at, trigger FROM patient_summary;"
```
