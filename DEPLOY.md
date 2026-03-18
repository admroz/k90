# Deployment na Synology NAS

## Architektura

- Obraz budowany automatycznie przez GitHub Actions (push do `main`) na natywnym runnerze ARM64
- Obraz dostępny na GHCR: `ghcr.io/admroz/k90:latest`
- Dane (`data/` + `.env`) przenoszone raz ręcznie, potem trzymane na Synology
- Lokalnie: proxy przez `SIGNAL_CLI_EXTRA_ARGS`; na Synology: brak proxy

## Wymagania wstępne (jednorazowo)

1. Na Synology: `docker login ghcr.io -u GITHUB_USERNAME -p PAT` (PAT z uprawnieniem `read:packages`)

## Jednorazowa migracja danych na Synology

```bash
# 1. Skopiuj dane i konfigurację
rsync -avz ./data/ synology:/volume1/docker/k90/data/
scp .env synology:/volume1/docker/k90/

# 2. Na Synology — dostosuj .env:
#   DATA_PATH=/volume1/docker/k90/data
#   AGENT_IMAGE=ghcr.io/OWNER/k90:latest
#   SIGNAL_CLI_EXTRA_ARGS=   (pusty lub usuń)

# 3. Uruchom
cd /volume1/docker/k90
docker compose up -d
```

Jeśli masz jeszcze historyczną bazę `kadencja90.db`, zmigruj ją ręcznie poza tym procesem i zachowaj kopię bezpieczeństwa. Aktualna aplikacja używa wyłącznie `k90.db`.

## Build obrazu

Build i push odbywa się automatycznie przez GitHub Actions przy każdym pushu do `main`.
Możesz też uruchomić ręcznie z zakładki Actions → "Build & Push Docker image" → Run workflow.

## Aktualizacja po zmianie kodu

```bash
# Push do main wyzwala build — po zakończeniu (~3-5 min) na Synology:
docker compose pull agent && docker compose up -d agent
```

## Co nie wymaga rebuildu obrazu

- Zmiana `system_prompt.md` — edytuj `data/system_prompt.md` i `docker compose restart agent`
- Zmiana modelu (`AGENT_MODEL`, `SUMMARY_MODEL`) — edytuj `.env` i `docker compose up -d agent`
- Zmiana plików pacjenta (`pacjent.md`, `dieta.md` itp.) — edytuj w `data/`, restart opcjonalny

## Zmienne środowiskowe

| Zmienna | Lokalnie | Synology |
|---------|----------|----------|
| `SIGNAL_CLI_EXTRA_ARGS` | `--http-proxy http://host.docker.internal:9000` | (pusty) |
| `DATA_PATH` | (domyślnie `./data`) | `/volume1/docker/k90/data` |
| `AGENT_IMAGE` | `ghcr.io/admroz/k90:latest` | `ghcr.io/admroz/k90:latest` |
| `DB_PATH` | (domyślnie `./data/k90.db`) | `/data/k90.db` |

## Weryfikacja

```bash
# Lokalnie
docker compose up -d
docker compose logs -f agent

# Sprawdź tabele SQLite
sqlite3 data/k90.db ".tables"

# Sprawdź podsumowanie pacjenta
sqlite3 data/k90.db "SELECT updated_at, trigger FROM patient_summary;"
```
