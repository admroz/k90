# k90: spokojne wdrożenie obok istniejącego Hermesa i Hindsight

Instrukcja dla właściciela, nie zapis wykonanych operacji. Agent niczego tutaj
nie wdrażał, nie restartował HS, nie migrował produkcji i nie logował konta k90.
Aktualny odbiór i testowany commit: [STATUS.md](STATUS.md), [acceptance.json](review-evidence/acceptance.json).
Przeczytaj całość przed rozpoczęciem. Nie uruchamiaj wszystkich bloków bezmyślnie.

## 0. Co zostaje na swoim miejscu

- Stack Hermes+HS pozostaje osobny, z tym samym obrazem HS, storage, auth, modelami
  i istniejącymi sieciami. Nie przenosimy HS ani jego danych do k90.
- Stack k90 ma swój kontener `agent`, własne `/data` i prywatny `.env`.
- Jedna dodatkowa zewnętrzna sieć Docker `k90-hs-shared` łączy tylko k90 i usługę
  HS. Alias `k90-hindsight` wskazuje HS; URL to `http://k90-hindsight:8888`.
  To port API WEWNĄTRZ kontenera; jeżeli obecny HS ma inny port/szyfrowanie,
  użyj rzeczywistego portu/HTTPS, bez zmiany konfiguracji HS dla tej instrukcji.
- Bank produkcyjny tylko `k90-owner`; smoke tylko nowy losowy `k90-test-*`.
  Nie używaj `hermes-default`, nie listuj innych banków i nie kopiuj tokenów Hermesa.
- Prywatna sieć i osobny bank NIE dają bank ACL. Każdy klient z dostępem do
  niechronionego API może potencjalnie dostać się do innych banków. Przed prawdziwymi
  danymi właściciel musi zaakceptować zaufaną sieć albo istniejącą granicę proxy/auth.
  Globalny bearer token także nie dowodzi ograniczenia do banku. Jeśli potrzebna
  jest silniejsza izolacja niż zapewnia istniejący endpoint, zostaw backend `local`;
  nie zmieniaj samowolnie wspólnego HS. Usługa HS może wysyłać dane do własnego LLM.

Nie mamy oryginalnego Compose Hermesa ani hostowych ścieżek właściciela. Poniżej
są minimalne fragmenty do WSTAWIENIA, nie pliki zastępujące istniejącą konfigurację.
Nazwy w `<...>` trzeba zastąpić. Nie kopiuj żadnej wartości produkcyjnej do Git/czatu.

Miejsca wykonania:

| Etykieta | Gdzie i jako kto |
| --- | --- |
| HOST | Powłoka na hoście Docker, właściciel z istniejącym dostępem do Dockera; nie kontener Hermesa. Uprawnienia Docker są równoważne root. |
| MAC | Terminal na Macu z przeglądarką, zwykły użytkownik, prywatny venv k90. |
| K90/root | Polecenie HOST `docker compose run/exec --user 0:0`; wykonuje się w kontenerze k90. Obecny Dockerfile nie ustawia USER, więc aplikacja działa jako UID:GID 0:0. |

Nie dodawaj `user: 1000:1000` w ramach tego rollout bez osobnego przygotowania
uprawnień. TokenStore wymaga właściciela zgodnego z UID wykonującym polecenie.
Wszystkie komendy są jednoliniowe; bloki YAML/dotenv to treść plików, nie komendy.

## 1. Prywatne przygotowanie i backup przed zmianami

HOST/właściciel: ustaw własne wartości (katalogi BEZWZGLĘDNE; backup poza data).
`K90_SOURCE_DIR` to checkout badanego źródła, nie katalog danych.

```sh
export K90_STACK_DIR='<ABSOLUTE_K90_STACK_DIRECTORY>' K90_SOURCE_DIR='<ABSOLUTE_REVIEWED_SOURCE_DIRECTORY>' K90_DATA_DIR='<ABSOLUTE_EXISTING_K90_DATA_DIRECTORY>' K90_BACKUP_DIR='<NEW_ABSOLUTE_PRIVATE_BACKUP_DIRECTORY>' HS_CONTAINER='<EXISTING_HS_CONTAINER_NAME>'
```

HOST/właściciel: przejdź do istniejącego projektu k90; zachowaj jego Compose
project name i poprzednie używane `-p`/`-f`, jeśli są inne niż domyślne.

```sh
cd "$K90_STACK_DIR"
```

HOST/właściciel: przygotuj prywatny, NOWY backup i zachowaj konfigurację; jeśli
katalog już istnieje, wybierz nowy, zamiast nadpisywać.

```sh
umask 077; mkdir -m 700 -- "$K90_BACKUP_DIR" && cp -p -- .env docker-compose.yml "$K90_BACKUP_DIR/"
```

HOST/właściciel: zanotuj/taguj poprzedni obraz, zanim zmienisz `.env`.

```sh
docker image tag "$(docker inspect --format '{{.Image}}' k90-agent)" k90-rollback:before-memory
```

K90/root, przez HOST: online backup używa API SQLite i jest dodatkiem do
pełnej kopii poniżej (nie kopiowaniem aktywnego samego pliku DB).

```sh
docker compose exec -T --user 0:0 agent python -c 'from tools.db import create_db_backup; create_db_backup(); print("SQLite API backup completed")'
```

HOST/właściciel: zatrzymaj TYLKO k90. HS/Hermes zostają uruchomione.
Nie pozwalaj w tym czasie innemu procesowi pisać do tej bazy ani odbierać tego bota.

```sh
docker compose stop agent
```

HOST/właściciel z sudo do odczytu root-owned danych: pełna zimna kopia `/data`,
w tym ukryte tokeny, dokumenty, prompt, WAL/SHM i prywatna sesja k90.

```sh
sudo tar -C "$K90_DATA_DIR" -czpf "$K90_BACKUP_DIR/k90-data-before-memory.tar.gz" . && sudo chmod 600 "$K90_BACKUP_DIR/k90-data-before-memory.tar.gz"
```

HOST/właściciel z sudo: kontrola archiwum bez wypisywania nazw prywatnych plików.

```sh
sudo tar -tzf "$K90_BACKUP_DIR/k90-data-before-memory.tar.gz" >/dev/null && printf 'Backup archive readable\n'
```

Zachowaj backup poza repo, z szyfrowaniem/retencją właściwą danym zdrowotnym.
Backup HS nadal wykonuj dotychczasową procedurą jego stacka; nie zmieniamy jej.
SQLite obejmuje dokumenty/rewizje/ledger/HMAC, ale nie zastępuje `.env`, plików
Garmin/Libre, promptu i tokenów. Nie odtwarzaj kopii nad nowymi zapisami po rollout.

## 2. Dwie małe zmiany Compose

W istniejącym Compose stacka Hermes+HS dodaj TYLKO poniższe wpisy. Zastąp nazwę
`<EXISTING_HS_SERVICE>` prawdziwą nazwą usługi HS, nie Hermesa i nie bazy Postgres.
Pozostałe services, volumes, auth, images, ports i dotychczasowe networks zachowaj.

```yaml
services:
  <EXISTING_HS_SERVICE>:
    networks:
      default: {} # TYLKO jeśli wcześniej używał implicit default; inaczej zachowaj swoje sieci
      k90_hs_link:
        aliases:
          - k90-hindsight
networks:
  k90_hs_link:
    external: true
    name: k90-hs-shared
```

Jeśli usługa ma już `networks: [foo, bar]`, zamień tę listę na mapę `foo: {}`,
`bar: {}` i dodaj `k90_hs_link` zamiast `default`. Nie dodawaj drugiego klucza
`services`/`networks`; scal we właściwych miejscach. Nie dodawaj nowego wolumenu HS.

W Compose osobnego k90 (`docker-compose.yml` z tej gałęzi) dopisz sieć do `agent`
i top-level `networks`; cała reszta zostaje, zwłaszcza `/data`, port i `env_file`:

```yaml
services:
  agent:
    networks:
      - default
      - k90_hs_link
networks:
  k90_hs_link:
    external: true
    name: k90-hs-shared
```

Dla istniejących niestandardowych sieci k90 zachowaj je zamiast `default`.
Istotny fragment bazowego Compose k90, już obecny w gałęzi (nie dubluj go):

```yaml
    image: ${AGENT_IMAGE:-admroz/k90:latest}
    env_file:
      - .env
    environment:
      - WEB_PASSWORD=${WEB_PASSWORD:?Set WEB_PASSWORD to at least 12 characters}
      - TZ=${TZ:-${APP_TIMEZONE:-Europe/Warsaw}}
      - DB_PATH=/data/k90.db
      - DATA_DIR=/data
    volumes:
      - ${DATA_PATH:-./data}:/data
```

`DATA_PATH...:/data` należy TYLKO do volumes, nigdy environment. Nowa opcja `K90_*`
w `.env` nie wymaga dopisywania YAML. `--env-file` CLI i service `env_file` to dwie
różne rzeczy; najprościej używać `.env` przy pliku Compose i tego samego cwd.
Nie uruchamiaj `docker compose config` bez `--quiet` z prawdziwymi sekretami.

## 3. Jedna prywatna konfiguracja k90

Edytuj ISTNIEJĄCY `.env`, zachowując Telegram/Garmin/Libre/CONVERSATION_USER_ID
oraz pozostałe ustawienia. Nie zastępuj go całym `.env.example`. Poniższe wartości
są wzorem; hasło i obraz ustaw samodzielnie. Nie wklejaj sekretów do historii shell.

```dotenv
AGENT_IMAGE=k90-local:memory-reviewed
DATA_PATH=<ABSOLUTE_EXISTING_K90_DATA_DIRECTORY>
WEB_PASSWORD=<YOUR_PRIVATE_PASSWORD_AT_LEAST_12_CHARACTERS>
APP_TIMEZONE=Europe/Warsaw
WEB_BIND_IP=127.0.0.1
WEB_PORT=8000
WEB_COOKIE_SECURE=true
K90_AGENT_AUTH=chatgpt
K90_SUMMARY_AUTH=chatgpt
AGENT_MODEL=gpt-6.1-sol
SUMMARY_MODEL=gpt-6.1-sol
K90_CHATGPT_STATE_DIR=/data/chatgpt-auth
K90_MEMORY_BACKEND=local
K90_PRIVACY_REDACT_TERMS=[]
K90_ALLOW_MODEL_IMAGES=false
```

Modele są przykładami; realny katalog/limity konta sprawdzi właściciel przy
wdrożeniu. Nie zostawiaj pustych model/numeric settings: usuń wpis, aby działał
default aplikacji. Konfiguracja env_file świadomie przekazuje także puste wartości.
Usuń ewentualny stary `TZ`, jeśli ma dziedziczyć `APP_TIMEZONE`. Dostęp HTTPS przez
istniejący reverse proxy lub tunel; bezpieczne cookie wymaga HTTPS. Dla świadomego
lokalnego HTTP ustaw `WEB_COOKIE_SECURE=false`, nie wystawiaj HTTP do Internetu.

HOST/właściciel:

```sh
chmod 600 .env && docker compose config --quiet
```

Na początek `local`: nic nie wyśle do HS. Przed danymi rzeczywistymi uzupełnij
listę `K90_PRIVACY_REDACT_TERMS` własnymi nazwami/adresami. To heurystyka, NIE pełna
anonimizacja. `local-only` blokuje wyjście; obrazy wymagają osobnej świadomej zgody,
która nie usuwa EXIF/PII. Nie wyłączaj filtrów, aby obejść problem konfiguracji.

Dopiero po smoke i decyzji o granicy dostępu zmień/dodaj:

```dotenv
K90_MEMORY_BACKEND=hindsight
K90_HINDSIGHT_URL=http://k90-hindsight:8888
K90_HINDSIGHT_BANK_ID=k90-owner
K90_HINDSIGHT_ALLOW_INTERNAL_HTTP=true
K90_HINDSIGHT_RECALL_TIMEOUT=3
K90_HINDSIGHT_WRITE_TIMEOUT=30
K90_HINDSIGHT_ALLOW_UNAUTHENTICATED=false
# K90_HINDSIGHT_TOKEN=<PRIVATE_TOKEN_VALID_FOR_THE_K90_ENDPOINT>
```

Token wstaw prywatnie do `.env`, tylko jeśli taki dostęp JUŻ zapewnia HS/proxy.
Jeśli istniejący HS nie wymaga auth i świadomie akceptujesz dostęp na zaufanej sieci,
ustaw `K90_HINDSIGHT_ALLOW_UNAUTHENTICATED=true` i usuń pusty token. Nie dopisuj
wymyślonego klucza, nie kopiuj OAuth/store Hermesa i nie zmieniaj auth/modeli HS.
Ta instrukcja nie ustanawia nowego IAM ani izolacji banków. Gdy to nieakceptowalne,
pozostań przy `local` do osobnej decyzji. `local` zachowuje SQLite/FTS i pełne źródła.

## 4. Obraz badanego źródła — bez publikacji i bez main write

Feature CI testuje obraz, ale go NIE publikuje. Nie zakładaj, że `admroz/k90:latest`
zawiera tę gałąź. HOST/właściciel: ustaw `K90_SOURCE` na dokładny `commit` z manifestu
acceptance.json. W checkout źródeł sprawdź zgodność; nie buduj z prywatnymi plikami.

```sh
export K90_SOURCE='<TESTED_SOURCE_COMMIT_FROM_ACCEPTANCE_JSON>'
```

HOST/właściciel: dopuszczalne są tylko późniejsze różnice `docs/` względem tego
commita; poniższe celowo wymaga dokładnego checkout źródłowego i czystego tracked tree.

```sh
test "$(git -C "$K90_SOURCE_DIR" rev-parse HEAD)" = "$K90_SOURCE" && git -C "$K90_SOURCE_DIR" diff --exit-code && docker build -t k90-local:memory-reviewed "$K90_SOURCE_DIR"
```

Jeżeli checkout jest nowszym dokumentacyjnym HEAD, przygotuj osobny czysty checkout
tego source commita. Nie resetuj istniejącej pracy. Ochrony ignore wykluczają `.env`,
credential files także rekurencyjnie, ale nie wkładaj sekretów do kontekstu budowania.
Na hoście innej architektury niż badane amd64 potrzebny jest osobny odbiór obrazu.

## 5. Sieć bez restartu istniejącego HS

HOST/właściciel: jednorazowo utwórz sieć; jeśli już istnieje, nie twórz ponownie.

```sh
docker network inspect k90-hs-shared >/dev/null 2>&1 || docker network create k90-hs-shared
```

HOST/właściciel: sprawdź podłączenia istniejącego HS (same nazwy sieci/aliasy).

```sh
docker inspect --format '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{$net.Aliases}}{{println}}{{end}}' "$HS_CONTAINER"
```

Jeśli HS jeszcze NIE jest na tej sieci, HOST/właściciel dołącza bieżący kontener
bez jego recreate/restart. Jeśli już jest, sprawdź alias; nie odłączaj aktywnej sieci
w ciemno. Brak wymaganego aliasu rozwiąż w uzgodnionym oknie właściciela.

```sh
docker network connect --alias k90-hindsight k90-hs-shared "$HS_CONTAINER"
```

Powtórz inspect powyżej i potwierdź alias. Patch Compose utrwala topologię na przyszłe
recreate; samo zapisanie YAML nie zmienia działającego HS. NIE uruchamiaj tutaj
`docker compose up`/`restart`/`down` w stacku Hermes+HS — Compose może chcieć
odtworzyć usługę po zmianie sieci. Następny recreate HS to osobna operacja właściciela.
Nie publikuj dodatkowego portu HS na hosta i nie podłączaj całego stacka Hermes.

HOST/właściciel: uruchom tylko jednorazowy klient k90, bez startu aplikacji,
sprawdź DNS i API health. To GET bez inferencji, ale nie test retain/recall.

```sh
docker compose run --rm --no-deps -T --user 0:0 --entrypoint python agent -c 'import socket,urllib.request; socket.getaddrinfo("k90-hindsight",8888); r=urllib.request.urlopen("http://k90-hindsight:8888/health",timeout=5); assert r.status==200; print("HS DNS and health PASS")'
```

Jeśli endpoint wymaga auth także dla health, użyj jego istniejącego bezpiecznego
health check zamiast wyłączania auth. Nie drukuj tokenów ani całych odpowiedzi.

## 6. OAuth: Mac z przeglądarką → prywatny import do k90

Nie wykonuj `login` wewnątrz headless kontenera. Kod binduje losowy port na
`127.0.0.1` maszyny uruchamiającej CLI, a Mac otwiera callback na swoim localhost.
Przekierowanie portu 8000 aplikacji tego nie naprawia. Nie ma tu device-flow CLI.
Mac-local login i SSH transfer są obsługiwaną przez ten kod ścieżką.

MAC/zwykły użytkownik: przygotuj osobny checkout tego samego źródła, Python >=3.12
(wybierz zainstalowany interpreter, np. `python3.12` lub nowszy) i prywatny venv.
Nie korzystaj z konfiguracji/tokenów Hermesa, Codex ani kontenera HS.

```sh
cd '<MAC_CHECKOUT_OF_TESTED_K90_SOURCE>' && python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
```

MAC/zwykły użytkownik: logowanie otwiera lokalną przeglądarkę. CLI prosi o
potwierdzenie WYŁĄCZONYCH dodatkowych kredytów dla k90; ustawienie sprawdzasz sam
w ChatGPT, kod nie potrafi zweryfikować rozliczeń. Nie nagrywaj terminala/przekierowań.
Adres autoryzacji może być pokazany, jeśli browser-open zawiedzie; to nie token.
Kodu/adresu callback i plików sesji nigdy nie wklejaj do czatu/logów/Git.

```sh
.venv/bin/python -m subscription_login --state-dir "$HOME/.config/k90-chatgpt" login
```

MAC/zwykły użytkownik: bezpieczny lokalny status, bez tokenu/identity/network.

```sh
.venv/bin/python -m subscription_login --state-dir "$HOME/.config/k90-chatgpt" status
```

K90/root przez HOST: utwórz trwały host ID w prywatnym katalogu `/data`.

```sh
docker compose run --rm --no-deps -T --user 0:0 --entrypoint python agent -m subscription_login --state-dir /data/chatgpt-auth init-host
```

HOST/właściciel: wybierz NOWY prywatny staging, poza repo i katalogiem danych.

```sh
export K90_IMPORT_DIR='<NEW_ABSOLUTE_PRIVATE_IMPORT_DIRECTORY>'; umask 077; mkdir -m 700 -- "$K90_IMPORT_DIR"
```

MAC/zwykły użytkownik: prześlij TYLKO credentials.json przez własne SSH, nie cały
store Hermesa, nie rejestrację/host ID. Ścieżka zdalna to dokładnie powyższy staging.

```sh
scp "$HOME/.config/k90-chatgpt/credentials.json" '<SSH_USER>@<DOCKER_HOST>:<ABSOLUTE_PRIVATE_IMPORT_DIRECTORY>/credentials.json'
```

K90/root przez HOST: import wymaga WRITABLE staging (tworzy credentials.lock),
własności root i prywatnych praw. Polecenie zmienia właściciela TYLKO dedykowanego
stagingu, nie katalogu Hermesa. Nie używaj stagingu z symlinkami. Import weryfikuje
podpis JWKS, nonce, tożsamość i expiry; wykonaj go od razu po logowaniu.

```sh
docker compose run --rm --no-deps -T --user 0:0 -v "$K90_IMPORT_DIR:/run/k90-import:rw" --entrypoint sh agent -c 'chown 0:0 /run/k90-import /run/k90-import/credentials.json && chmod 700 /run/k90-import && chmod 600 /run/k90-import/credentials.json && exec python -m subscription_login --state-dir /data/chatgpt-auth import-session /run/k90-import'
```

K90/root przez HOST: potwierdź authenticated=true i zachowanie prywatnych praw.
Status nie dowodzi świeżej inferencji ani poprawnych limitów providerowego konta.

```sh
docker compose run --rm --no-deps -T --user 0:0 --entrypoint python agent -m subscription_login --state-dir /data/chatgpt-auth status
```

HOST/właściciel z sudo: dopiero po udanym imporcie i statusie usuń tymczasowe
pliki, nie trwały `/data/chatgpt-auth`. MAC/zwykły użytkownik usuwa swoją kopię.
NIE rób logout na Macu po przeniesieniu — odwołałby tę samą sesję na serwerze.
Od tej chwili tylko runtime k90 ma odświeżać tę sesję.

```sh
sudo rm -f -- "$K90_IMPORT_DIR/credentials.json" "$K90_IMPORT_DIR/credentials.lock" && sudo rmdir -- "$K90_IMPORT_DIR"
```

```sh
rm -f -- "$HOME/.config/k90-chatgpt/credentials.json" "$HOME/.config/k90-chatgpt/credentials.lock" "$HOME/.config/k90-chatgpt/registration.json" && rmdir -- "$HOME/.config/k90-chatgpt"
```

Druga komenda wyłącznie MAC. Nie używaj usuwania, jeśli import nie powiódł się;
odwołaj wtedy nieprzeniesioną sesję komendą logout na Macu i zaloguj ponownie.
Filesystem 0700/0600/lock/atomic replace nie jest szyfrowaniem ani ochroną przed root.
Nie współdziel store z drugim runtime/laptopem i nie uruchamiaj odświeżania ze starych kopii.

## 7. Krótki HS deployment smoke — tylko właściciel, tylko syntetyki

To owner-deferred check, NIE dowód wykonany przez agenta na tej topologii.
HS może użyć własnego modelu i limitów: właściciel przed startem sprawdza brak
płatnego fallbacku/kredytów. Nie twórz infrastruktury modeli tylko dla tego smoke.
Na czas próby aplikacja k90 nadal zatrzymana, backend w `.env` może pozostać local.
Poniższe one-off nadpisują tylko backend/bank; nie uruchamiają web/worker/SQL.
Jeśli token jest bank-scoped, właściciel musi zapewnić dostęp do nowego test banku
bez osłabiania istniejącego ACL. Wersja API musi wspierać użyte operacje.

HOST/właściciel: wybierz nowy bank; zapisz nazwę, aby dokończyć cleanup po błędzie.

```sh
export K90_SMOKE_BANK="k90-test-deploy-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
```

K90/root przez HOST: utwórz WYŁĄCZNIE ten nowy testowy bank, bez modyfikacji HS auth.

```sh
docker compose run --rm --no-deps -T --user 0:0 -e K90_MEMORY_BACKEND=hindsight -e K90_HINDSIGHT_BANK_ID="$K90_SMOKE_BANK" --entrypoint python agent -c 'from memory_runtime import get_backend; from k90_memory import PrivacyPolicy; b=get_backend(PrivacyPolicy(),worker=True); assert b.bank_id.startswith("k90-test-"); assert b._request("PUT","",{"name":"k90 synthetic deployment smoke","enable_observations":False})["bank_id"]==b.bank_id; print("Test bank created")'
```

K90/root przez HOST: prawdziwy retain/recall adaptera, jeden fikcyjny tekst;
nie czyta SQL, dokumentów ani rozmów właściciela. Operacja może zużyć limit HS.

```sh
docker compose run --rm --no-deps -T --user 0:0 -e K90_MEMORY_BACKEND=hindsight -e K90_HINDSIGHT_BANK_ID="$K90_SMOKE_BANK" --entrypoint python agent -c 'from memory_runtime import get_backend; from k90_memory import PrivacyPolicy,MemoryDocument,SourceRef; b=get_backend(PrivacyPolicy(),worker=True); assert b.bank_id.startswith("k90-test-"); b.retain(MemoryDocument("k90-smoke-doc-r1","k90-smoke-source",1,"owner:synthetic-smoke","user","The synthetic participant prefers morning walks in the cedar garden.","2026-01-01T12:00:00Z")); assert SourceRef("k90-smoke-source",1) in b.recall("owner:synthetic-smoke","When does the synthetic participant prefer walks?",5); print("Synthetic HS retain/recall PASS")'
```

K90/root przez HOST: cleanup TEGO test banku także po błędzie poprzedniej próby.
Nigdy nie podstawiaj tu `k90-owner` ani banku Hermesa. Sprawdź usunięcie w swoim
HS admin/proxy (odczyt dokumentów tego banku ma zwrócić 404); nie listuj wszystkich banków.

```sh
docker compose run --rm --no-deps -T --user 0:0 -e K90_MEMORY_BACKEND=hindsight -e K90_HINDSIGHT_BANK_ID="$K90_SMOKE_BANK" --entrypoint python agent -c 'from memory_runtime import get_backend; from k90_memory import PrivacyPolicy; b=get_backend(PrivacyPolicy(),worker=True); assert b.bank_id.startswith("k90-test-"); assert b._request("DELETE","")["success"] is True; print("Test-bank delete acknowledged; verify exact-bank 404")'
```

Jeśli recall zawiedzie, nie wpisuj PASS: sprawdź wersję API, zasoby/limit modeli,
uprawnienia i logi prywatnie. Nie restartuj wspólnego HS. Zachowaj `local` dla k90.
Nie traktuj tej próby jako ACL/restart-persistence ani testu modelowej jakości.

Właściciel tworzy produkcyjny PUSTY `k90-owner` przez istniejący admin/proxy HS,
z własną zatwierdzoną polityką/auth. Adapter k90 nie tworzy banków automatycznie.
Dopiero wtedy ustaw końcowe opcje hindsight z sekcji 3. Nie importuj całej starej
historii; ewentualny backfill jest osobną świadomą operacją z OPERATIONS_MEMORY_AUTH.

## 8. Rollout k90 i minimalna kontrola

HOST/właściciel: sprawdź konfigurację i odtwórz TYLKO agent z wybranym obrazem,
na tym samym trwałym `/data`. Nie uruchamiaj drugiego odbiorcy tego samego bota.

```sh
docker compose config --quiet && docker compose up -d --no-deps agent
```

K90/root przez HOST: health; bez danych pacjenta i bez modelu.

```sh
docker compose exec -T --user 0:0 agent python -c 'import urllib.request; assert urllib.request.urlopen("http://127.0.0.1:8000/healthz",timeout=5).status==200; print("k90 health PASS")'
```

K90/root przez HOST: trwałość auth/status po recreate i lokalny stan pamięci.

```sh
docker compose exec -T --user 0:0 agent python -m subscription_login --state-dir /data/chatgpt-auth status
```

```sh
docker compose exec -T --user 0:0 agent python -m memory_admin status
```

W panelu zaloguj się i sprawdź zachowanie pięciu dokumentów oraz daty/rewizje bez
kopiowania ich do raportu. `/help` na Telegramie nie wywołuje modelu. `healthz` nie
potwierdza HS ani provider inference. Nie oceniaj samego `claimed_jobs` jako ack.
`memory_admin status` powinien pokazywać przejście odpowiednich outbox do done;
retry oznacza problem HS, blocked oznacza działanie polityki. `local` nie drenuje HS.

Pierwsze live logowanie/katalog/refresh/inference finalnego adaptera i owner-network
HS są osobnym odbiorem właściciela. Testy tekst/tool/obraz wykonuj na pustych,
fikcyjnych danych przed rzeczywistymi; zwykły syntetyczny prompt w produkcji może
nadal dołączyć prawdziwy profil/historię. Nie uruchamiaj drugiego runtime z tą samą
sesją OAuth. Zdjęcie wymaga jawnej zgody; nie włączaj jej dla danych rzeczywistych
przez sam fakt zielonego testu. Brak API fallbacku nie jest dowodem braku kredytów konta.

## 9. Wyłączenie HS, logout i rollback

Najmniejsza reakcja na problem HS: w `.env` ustaw `K90_MEMORY_BACKEND=local`,
a potem HOST/właściciel odtwórz TYLKO agent. Zostają lokalne źródła, FTS i outbox;
nie kasuj tabel i nie odtwarzaj bazy. Usługi Hermesa/HS pozostają nietknięte.

```sh
docker compose up -d --no-deps agent
```

K90/root przez HOST: logout tylko gdy rzeczywiście chcesz odwołać sesję k90,
nie podczas rutynowego restartu/rollback. Koordynuj z właścicielem i zatrzymaj
rozmowy/refresh na czas operacji. Nie przenoś z powrotem starej kopii refresh tokenu.

```sh
docker compose exec -T --user 0:0 agent python -m subscription_login --state-dir /data/chatgpt-auth logout
```

Wynik `renewable_session_revoked=false`/exit 1: odłącz k90 w ChatGPT ręcznie.
Host ID zostaje. Ponowne użycie wymaga świeżego logowania i importu.

Pełny rollback do starego obrazu czytającego `.md` nie jest tylko podmianą tagu:
canonical dokumenty tej wersji są w SQLite, stare pliki mogą być nieaktualne.
K90/root przez HOST: przed zatrzymaniem wyeksportuj aktualne pięć dokumentów do
NOWEGO prywatnego katalogu pod `/data` i zachowaj również nowy backup bazy.

```sh
docker compose exec -T --user 0:0 agent python -m patient_documents /data/rollback-export-current
```

```sh
docker compose exec -T --user 0:0 agent python -c 'from tools.db import create_db_backup; create_db_backup(); print("Pre-rollback SQLite backup completed")'
```

HOST/właściciel: zatrzymaj k90 i zachowaj osobną zimną kopię bieżącego `/data`
przed jakimkolwiek restore. Wybierz nowy katalog backupu, jak w sekcji 1.

```sh
docker compose stop agent
```

Właściciel wybiera: powrót do poprzedniego obrazu na kompatybilnej aktualnej bazie
po przeglądzie zgodności albo odtworzenie zimnego backupu sprzed rollout do NOWEGO
katalogu danych. Ten drugi wariant traci nowe zapisy od backupu; nie wykonuj go
bez decyzji i zachowania bieżącej kopii. Przenieś jawnie wyeksportowane aktualne
Markdown do miejsca czytanego przez starą wersję tylko po kontroli właściciela.
Nie kasuj nowych tabel dla uzyskania kompatybilności i nie nadpisuj aktywnej bazy.

W `.env` ustaw `AGENT_IMAGE=k90-rollback:before-memory` i wybrane świadomie
`DATA_PATH`/tryb auth zgodny ze starą wersją; zachowaj kopię nowej konfiguracji.
Nie przywracaj starych rotowanych OAuth tokenów z archiwum jako aktywnej sesji.
HOST/właściciel:

```sh
docker compose config --quiet && docker compose up -d --no-deps agent
```

Powtórz health/panel/help. Nie wykonuj `docker compose down -v`, globalnego prune,
restartu HS ani restore jego storage. Dodatkowa sieć może zostać; jej ewentualne
odłączenie/usunięcie jest osobnym zadaniem po sprawdzeniu konsumentów i trwałego YAML.

## Granice dowodów

Przygotowanie personal self-hosted nie jest akceptacją produkcyjnej topologii,
prawdziwego OAuth/provider behavior, bank ACL, szyfrowania backupu ani pełnej
anonimizacji. CI używa syntetyków i network-none dla runtime; nie uwierzytelnia
konta i nie deployuje. Szczegóły rzeczywiście wykonanych prób: VERIFICATION.md.
