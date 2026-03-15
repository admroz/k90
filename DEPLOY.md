# Deployment na Synology NAS

## Architektura

- Obraz budowany lokalnie i pushowany do GHCR
- Dane (`data/` + `.env`) przenoszone raz ręcznie, potem trzymane na Synology
- Lokalnie: proxy przez `SIGNAL_CLI_EXTRA_ARGS`; na Synology: brak proxy

## Wymagania wstępne (jednorazowo)

1. Repozytorium GitHub z dostępem do GHCR
2. Personal Access Token (PAT) z uprawnieniami `write:packages` i `read:packages`
3. Lokalnie: `docker login ghcr.io -u GITHUB_USERNAME -p PAT`
4. Na Synology: `docker login ghcr.io -u GITHUB_USERNAME -p PAT` (tylko `read:packages`)

## Jednorazowa migracja danych na Synology

```bash
# 1. Skopiuj dane i konfigurację
rsync -avz ./data/ synology:/volume1/docker/k90/data/
scp .env synology:/volume1/docker/k90/

# 2. Migracja bazy (jeśli wcześniej używałeś innej nazwy)
cp data/kadencja90.db data/k90.db

# 3. Na Synology — dostosuj .env:
#   DATA_PATH=/volume1/docker/k90/data
#   AGENT_IMAGE=ghcr.io/OWNER/k90:latest
#   SIGNAL_CLI_EXTRA_ARGS=   (pusty lub usuń)

# 4. Uruchom
cd /volume1/docker/k90
docker compose up -d
```

## Build i push obrazu

```bash
# Pierwsza wersja — buduje od zera (base + app)
docker build -t ghcr.io/OWNER/k90:latest .
docker push ghcr.io/OWNER/k90:latest

# Kolejne wersje — przy zmianie kodu (bez zmiany requirements.txt)
# Docker cache pomija warstwę base, buduje tylko app (~szybko)
docker build -t ghcr.io/OWNER/k90:latest .
docker push ghcr.io/OWNER/k90:latest
```

Zastąp `OWNER` nazwą użytkownika lub organizacji GitHub.

## Aktualizacja po zmianie kodu

```bash
# Lokalnie:
docker build -t ghcr.io/OWNER/k90:latest .
docker push ghcr.io/OWNER/k90:latest

# Na Synology:
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
| `AGENT_IMAGE` | (domyślnie lokalny build) | `ghcr.io/OWNER/k90:latest` |
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
