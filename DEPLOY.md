# Deployment na Lenovo M900 (Intel x86-64)

## Architektura

- Obraz `linux/amd64` budowany automatycznie przez GitHub Actions (push do `main`) na natywnym runnerze `ubuntu-24.04`
- Obraz publikowany przez GitHub Actions na Docker Hub: `admroz/k90:latest`
- Dane (`data/` + `.env`) przenoszone raz ręcznie, potem trzymane na Lenovo
- Jeden kontener z backendem WWW i adapterem Telegrama, nadzorowanymi osobno przez Supervisor.
- Frontend tylko w LAN: port HTTP domyślnie na loopback serwera, HTTPS przez reverse proxy.
- Nowa konfiguracja wymaga `WEB_PASSWORD` (minimum 12 znaków). Przygotowanie i testy: [WEB.md](WEB.md).

Dokument opisuje docelową konfigurację z repozytorium, nie jest raportem stanu
serwera. Frontend i adapter są już częścią `main`. Plan integracji Hindsight
opisany w [Pamięć k90](docs/MEMORY_ARCHITECTURE.md) nie jest jeszcze wdrożony
w kodzie ani skonfigurowany w tym Compose.

Konfiguracja ARM64 dla Synology pozostaje zakomentowana w macierzach `test` i `build`
w `.github/workflows/docker.yml`. Aby ją przywrócić, odkomentuj oba wpisy. ARM otrzyma
osobny cache oraz tagi `latest-arm64` i `sha-<commit>-arm64`, bez nadpisywania obrazu Intela.
Na Synology należy wówczas ustawić `AGENT_IMAGE=admroz/k90:latest-arm64`.

## Przeniesienie z Synology na Lenovo

1. Na Lenovo przygotuj Docker Engine z Compose oraz katalog aplikacji, np. `~/k90/`, z `docker-compose.yml` z repozytorium.
2. Zatrzymaj dotychczasowy kontener k90 na Synology, a potem skopiuj całe `data/` i `.env` do katalogu aplikacji na Lenovo. Zachowaj kopię źródłową. Uwzględnij ukryte katalogi tokenów i istniejące pliki SQLite `-wal`/`-shm`; nie kopiuj samego aktywnego `k90.db`.
3. W `.env` zmień `DATA_PATH` na `./data` (lub bezwzględną ścieżkę na Lenovo) i ustaw `AGENT_IMAGE=admroz/k90:latest`. Zachowaj `CONVERSATION_USER_ID`, token Telegrama i pozostałe dane dostępu.
4. Po publikacji obrazu AMD64 uruchom na Lenovo:

```bash
docker compose pull agent
docker compose up -d --remove-orphans
docker compose logs --tail=100 agent
docker image inspect admroz/k90:latest --format '{{.Os}}/{{.Architecture}}'
```

Oczekiwana architektura obrazu to `linux/amd64`. Sprawdź `/help` i zwykłą rozmowę na Telegramie.
Nie uruchamiaj obu instancji z tym samym botem. Sam push do `main` publikuje obraz;
nie aktualizuje działającego kontenera na żadnym serwerze.

## Wymagania wstępne (jednorazowo)

1. Publiczny obraz `admroz/k90:latest` nie wymaga logowania do rejestru na Lenovo.

## Frontend w LAN

Mapowanie portu jest już w Compose. Dla bezpośredniego HTTP w zaufanym LAN ustaw
w `.env` poniższe wartości (adres zastąp adresem Lenovo):

```dotenv
WEB_BIND_IP=192.168.0.100
WEB_PORT=8000
WEB_COOKIE_SECURE=false
WEB_PASSWORD=tu-ustaw-wlasne-dlugie-haslo
```

Po `docker compose up -d agent` frontend będzie dostępny pod
`http://192.168.0.100:8000`. Hasło musi mieć co najmniej 12 znaków.
Przy dostępie przez HTTPS zostaw `WEB_COOKIE_SECURE=true` i skonfiguruj reverse proxy.

## Historyczna konfiguracja Synology (ARM64)

Poniższy wariant wymaga ponownego włączenia builda ARM64 i użycia tagu `latest-arm64`.

```bash
# 1. Skopiuj dane i konfigurację
rsync -avz ./data/ synology:/volume1/docker/k90/data/
scp .env synology:/volume1/docker/k90/

# 2. Na Synology — dostosuj .env:
#   DATA_PATH=/volume1/docker/k90/data
#   AGENT_IMAGE=admroz/k90:latest-arm64
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
Publikacja jest dozwolona wyłącznie dla `main`; PR-y uruchamiają same testy.

## Aktualizacja po zmianie kodu

```bash
# Push do main wyzwala build — po jego zakończeniu na Lenovo:
docker compose pull agent && docker compose up -d --remove-orphans
```

## Co nie wymaga rebuildu obrazu

- Zmiana `system_prompt.md` — edytuj `data/system_prompt.md` i `docker compose restart agent`
- Zmiana modelu (`AGENT_MODEL`, `SUMMARY_MODEL`) lub `OPENAI_API_KEY` — edytuj `.env` i `docker compose up -d agent`
- Zmiana tokenu lub whitelisty Telegrama — edytuj `.env` i `docker compose up -d agent`
- Zmiana plików pacjenta (`pacjent.md`, `dieta.md` itp.) — edytuj w `data/`, restart opcjonalny

## Zmienne środowiskowe

| Zmienna | Lokalnie | Lenovo |
|---------|----------|----------|
| `DATA_PATH` | (domyślnie `./data`) | `./data` lub ścieżka na Lenovo |
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
