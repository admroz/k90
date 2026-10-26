# Pamięć i subskrypcja — uruchomienie, granice i odzyskiwanie

Ten opis dotyczy kodu gałęzi funkcjonalnej, nie dowodzi scalenia ani wdrożenia.
Nie uruchamiać migracji/testów na produkcji bez własnego backupu i przeglądu PR.

## Co jest źródłem prawdy

- `k90.db`: pomiary, posiłki, rozmowy, summary, kolejka WWW, pięć dokumentów pacjenta
  z rewizjami, lokalne źródła pamięci/ich wersje/FTS/outbox i dziennik wejść oraz
  wywołań narzędzi. Nowe wejście zostaje zapisane także po błędzie lub blokadzie LLM.
- Pięć dokumentów: `pacjent.md`, `wywiad.md`, `analiza.md`, `dieta.md`, `tydzien.md`.
  Nazwy zostają w interfejsie narzędzi i panelu, ale treść jest w SQLite.
- Istniejący Markdown jest importowany tylko dla brakującego dokumentu. SQLite
  zawsze wygrywa; późniejsza edycja starego `.md` NIE aktualizuje dokumentu.
  Oryginalne pliki nie są usuwane ani automatycznie aktualizowane.
- Dotychczasowe zdjęcia rozmów są częścią zapisanej wieloczęściowej treści JSON
  w SQLite, nie są automatycznie wysyłane do HS. Do indeksu trafia tylko tekst.
- Nie jest to uniwersalny audyt dowolnej operacji SQL na tabelach pomiarów.
  Wyniki i argumenty nowych narzędzi są lokalnie rejestrowane, nie promowane do faktów HS.
- HS jest odtwarzalnym indeksem. Zwraca odwołania; przed zbudowaniem kontekstu kod
  odczytuje bieżącą lokalną rewizję i sprawdza właściciela. Nie używa wygenerowanego
  tekstu HS jako aktualnego wyniku badania ani potwierdzonego stanu pacjenta.

## Bezpieczne ustawienia domyślne

Compose przekazuje konfigurację aplikacji z `env_file: .env`; dodanie opcji
`K90_*` nie wymaga dopisywania jej do YAML. Uruchamiać z katalogu projektu
(`docker compose up -d`); przy niestandardowym pliku interpolacji pamiętać,
że `--env-file` nie zastępuje service `env_file: .env`.
Jawne nadpisania runtime to `DATA_DIR=/data`, `DB_PATH=/data/k90.db`, wymagane
`WEB_PASSWORD` oraz `TZ` (jawne TZ, następnie APP_TIMEZONE, następnie Europe/Warsaw).
Hasło musi mieć minimum 12 znaków; Compose wymaga niepustej wartości, a aplikacja
sprawdza długość. Nie drukować `docker compose config` z prawdziwymi sekretami.
Przykładowy `.env.example` nie zawiera danych produkcji; skopiować go do prywatnego
`.env` i ustawić własne wartości. Obraz pozostaje wyborem operatora.

```dotenv
K90_MEMORY_BACKEND=local
K90_AGENT_AUTH=api
K90_PRIVACY_REDACT_TERMS=[]
K90_ALLOW_MODEL_IMAGES=false
K90_OUTBOUND_MAX_CHARS=2000000
```

`K90_SUMMARY_AUTH` dziedziczy `K90_AGENT_AUTH`, jeżeli nie został jawnie ustawiony.
Tryb `local` prowadzi źródła/FTS/outbox, ale nie uruchamia klienta HS ani indeksowania
w sieci. `disabled` pomija recall; nie wyłącza trwałego lokalnego zapisu ani filtra.
Nie ma automatycznego importu starych rozmów z produkcyjnej tabeli `conversations`.

Filtr jest stosowany tuż przed wywołaniem Chat Completions, API-key Responses,
subskrypcyjnego Responses, generowaniem summary i retain/recall HS. Obejmuje
przywróconą historię, źródła i wyniki narzędzi. Oryginały nie są zmieniane.
Maskowanie obejmuje rozpoznawane e-maile, PESEL, telefony i lokalnie skonfigurowane
frazy. Sekrety, jawne `local-only`, błędna polityka i niedozwolone załączniki blokują
wyjście. Nie używamy modelu chmurowego do filtrowania surowych danych.

Kontrola źródeł następuje także przed kompozycją promptu: osobno dokumenty summary
(również fallback), prompt/profile, pola rekordów kontekstu i metadane recall.
Nagłówek lub data nie mogą ukryć strukturalnego `local_only`. JSON w kluczach
podlega tym samym limitom co wartości; duplikaty kluczy, także po dekodowaniu
Unicode, i stałe niefinitywne są odrzucane. To nie jest wyszukiwanie dowolnego
JSON-u wewnątrz prozy. Niejednoznaczne lub odrzucone oryginały wejść/backfill
zostają lokalnie z zachowawczym `Source.local_only`; nie zmienia to ich treści.
Taką flagę otrzymują także dokumenty przy zapisie/importowaniu lub snapshot przy
inicjalizacji. Ponowny jawny backfill naprawia flagę starszego źródła o tej samej
treści. Nie naprawia to dowolnych dawniej spłaszczonych danych bez oryginału ani
nie usuwa danych już wysłanych do zewnętrznego indeksu. Testy i ograniczenia:
[privacy_composition_fix.md](review-evidence/privacy_composition_fix.md).

**To heurystyka, nie pełna anonimizacja.** Przed danymi rzeczywistymi właściciel
ustala nazwy, adresy i pozostałe identyfikatory w JSON-owej liście
`K90_PRIVACY_REDACT_TERMS`, np. `["Fikcyjne Nazwisko","ul. Przykładowa 1"]`.
Kontekst zdrowotny jest dozwolony; nie ma automatycznej, kompletnej klasyfikacji
wszystkich szczególnie wrażliwych kategorii. `local-only` pozwala je lokalnie
zablokować. Brak rozpoznania dowolnego nazwiska nie dowodzi braku PII.

NOWE zdjęcia do modelu wymagają osobnego, jawnego `K90_ALLOW_MODEL_IMAGES=true`
ustawionego przez właściciela; domyślnie pozostaje `false`. To zgoda na przesłanie,
NIE anonimizacja obrazu/EXIF. Nie włącza zdjęć w HS.
Właściciel odpowiada za widoczną treść zdjęcia: obraz jest wysyłany BEZ analizy
PII i anonimizacji. Nie ma OCR, rozpoznawania danych w obrazie ani usuwania EXIF.
Tylko tekst podlega podstawowym regułom regex (sekrety, e-mail, telefon, PESEL,
skonfigurowane redakcje); zwykły kontekst posiłków i zdrowia pozostaje dozwolony.
Dokładnie rozpoznane koperty `image_url`/`input_image`, po walidacji base64,
sygnatury PNG/JPEG/WebP, zgodności MIME, rozmiaru i budżetu, zachowują dane
obrazu bajt w bajt: base64 nie przechodzi tekstowego skanowania ani zamian regex.
Limit techniczny jednego obrazu wynosi dokładnie 5 000 000 bajtów po rozkodowaniu base64,
zgodnie z wejściem HTTP/Telegram; suma obrazów w jednym przejściu polityki ma limit
10 000 000 bajtów (również dla wielokrotnych wystąpień tego samego obrazu).
Domyślne `K90_OUTBOUND_MAX_CHARS=2000000` dotyczy tekstu, kluczy i metadanych,
nie poprawnie rozpoznanych URI obrazów. URL zdalny i URI w prozie nadal są tekstem.
Kodowany JSON zachowuje kumulatywną kontrolę tekstu surowego i rozkodowanego;
wyłącznie zwalidowane URI obrazów są odejmowane na każdej warstwie kodowania.
Przed parsowaniem limit pojedynczego surowego JSON wynosi budżet tekstu plus
13 337 432 znaki przy dozwolonych obrazach (15 337 432 domyślnie), a suma długości
parsowanych warstw ma niezależny limit 32 000 000 znaków. Dodatkowy zapas nie
uprawnia do wysłania dużego tekstu ani wadliwego JSON. Pozostają limity 100 000
węzłów i domyślnie 40 poziomów, zgoda oraz ograniczenia local-only/sekretów.
Bez zgody na obrazy zapas parsowania nie jest dostępny; HS pozostaje tekstowy.
Sygnatura to kontrola techniczna, nie pełna walidacja pliku ani jego treści.
URL zdalny, tekst z URI i inne pola nie otrzymują tego wyjątku. Nieznane koperty,
dodatkowe pola w części obrazu i niejednoznaczny JSON pozostają blokowane.
Rozpoznane części `image_url` w krótkiej historii są zawsze zastępowane tekstem
`[Historical image omitted]`, także przy `true`. Bezpieczny tekst, wcześniejsza
analiza asystenta i późniejsze doprecyzowania pozostają w kontekście; domyślna
głębokość `HISTORY_MESSAGES` nie zmienia się. Struktura oryginału i jego pola
tekstowe przechodzą kontrolę sekretów i ograniczeń (także metadanych i kodowanego
JSON) przed pominięciem obrazu; rozpoznane dane obrazu nie są skanowane jak tekst.
Nieznane załączniki i niejednoznaczne zapisy nadal blokują wysyłkę.
Oryginały lokalne nie są zmieniane. Nie analizujemy automatycznie archiwum ani
nie wywołujemy dodatkowego modelu. Stare zdjęcie bez opisu pozostaje bez opisu.
Rozpoznanie posiłku wymaga ustalenia porcji/przygotowania; ta zmiana nie zapisuje
automatycznie posiłków. Ostatni zarejestrowany posiłek sprawdzamy narzędziami SQL.

## Hindsight — osobny bank i oddzielne uprawnienia

Przykład ustawień świadomie podłączonej prywatnej sieci kontenerów:

```dotenv
K90_MEMORY_BACKEND=hindsight
K90_HINDSIGHT_URL=http://hindsight:8888
K90_HINDSIGHT_BANK_ID=k90-owner
K90_HINDSIGHT_ALLOW_INTERNAL_HTTP=true
K90_HINDSIGHT_RECALL_TIMEOUT=3
K90_HINDSIGHT_WRITE_TIMEOUT=30
```

Do połączenia wymagany jest osobno skonfigurowany `K90_HINDSIGHT_TOKEN`, albo jawne
`K90_HINDSIGHT_ALLOW_UNAUTHENTICATED=true` dla świadomie zaakceptowanej prywatnej
usługi. **Drugi wariant nie daje autoryzacji ani izolacji banków.** Aplikacja nie
konfiguruje reverse proxy, sieci ani ACL. Token globalny też nie dowodzi uprawnień
ograniczonych do banku. Przed danymi rzeczywistymi zapewnić własną granicę dostępu
(np. ograniczony proxy i sieci), HTTPS poza świadomie zaufaną siecią i backup HS.
Kod nie tworzy banku produkcyjnego ani nie zmienia konfiguracji banku Hermesa.
Id banku musi zaczynać się od `k90-`; nie kierować aplikacji do `hermes-default`.

Bank/tag jest przestrzenią danych, nie zabezpieczeniem przed innym klientem API.
Właściciele i ID dokumentów są pseudonimizowani HMAC; stabilny klucz znajduje się
w lokalnej tabeli `memory_settings` i jest częścią backupu SQLite. Nie rotować go
bez planu usunięcia starego indeksu i odbudowy.

Zadania outbox działają w osobnym wątku backendu, bez trzymania transakcji SQLite
podczas sieci. Domyślny tick to najwyżej trzy zadania, potem przerwa. Recall ma
oddzielny krótki timeout i limit kontekstu; po zwykłej awarii działa ograniczone
lokalne wyszukiwanie FTS5. To nie jest semantyczny odpowiednik HS. Socket timeout
nie jest ścisłym całkowitym deadline'em przeciw serwerowi powoli wysyłającemu dane.

Dokumenty HS mają ID stabilne dla źródła i rewizji. Stare wersje mają osobne zadania
usunięcia; lokalna hydration natychmiast odrzuca nieaktualne rewizje. Zdalne kasowanie
jest eventual: timeoutowana operacja serwera może jeszcze trwać. Nie obiecujemy
natychmiastowego fizycznego usunięcia każdej zdalnej kopii.

Polecenia poniżej wykonuje właściciel w środowisku aplikacji z właściwym `DB_PATH`:

```sh
python -m memory_admin status
python -m memory_admin --owner owner backfill --after-id 0 --limit 100
python -m memory_admin --owner owner backfill --after-id 0 --limit 100 --apply
python -m memory_admin --owner owner rebuild
python -m memory_admin run-once --limit 3
```

Backfill bez `--apply` tylko liczy wybrany batch. `--apply` jawnie tworzy źródła
oraz zlecenia; działający worker HS może je następnie wysłać po filtrowaniu.
Następny batch wskazuje się przez zwrócony `last_selected_id`. Nie importujemy
innych właścicieli, bajtów zdjęć ani sekretów z konfiguracji. Oryginały rozmów
pozostają lokalnie w SQLite, nawet jeśli polityka zablokuje zlecenie indeksowania.

`rebuild` kolejkuje aktualne źródła, NIE czyści całego banku. Zmiana polityki nie
usuwa automatycznie już wysłanych danych: przed zaostrzeniem zasad należy wybrać
nowy bank albo kontrolowanie wyczyścić wyłącznie bank k90 i wykonać rebuild.
Nie kasować wspólnej usługi HS ani banku innego agenta.

## Opcjonalna subskrypcja ChatGPT

Przykład jawnego wyboru dla obu generatorów:

```dotenv
K90_AGENT_AUTH=chatgpt
K90_SUMMARY_AUTH=chatgpt
AGENT_MODEL=gpt-6.1-sol
SUMMARY_MODEL=gpt-6.1-sol
K90_CHATGPT_STATE_DIR=/data/chatgpt-auth
```

Można wybrać `api` osobno dla summary, ale to świadome pozostawienie osobnego
rozliczenia API. Nie istnieje automatyczny fallback z planu do płatnego API.
Model musi należeć do katalogu udostępnionego konkretnemu kontu. API-key i plan
korzystają z różnych adapterów; sam model lub klucz API nie zmienia rozliczenia.

Logowanie wykonuje się na komputerze z przeglądarką (np. Mac), nie przez `hsh`:

```sh
python -m subscription_login --state-dir "$HOME/.config/k90-chatgpt" login
python -m subscription_login --state-dir "$HOME/.config/k90-chatgpt" status
```

W tym środowisku potrzebne są zależności repozytorium; można użyć odrębnego venv.
Jeśli `python3` wskazuje systemowy stary Python, wybrać jawnie właściwy interpreter.
**Wyłączyć dodatkowe kredyty dla aplikacji `k90` w ustawieniach użycia ChatGPT.**
CLI prosi o potwierdzenie; nie weryfikuje ustawienia ani rachunku przez API.
Brak API-key fallbacku sam w sobie nie gwarantuje niewykorzystania kredytów konta.

Dla self-hosted kontenera:

1. Na docelowym runtime utworzyć własny host ID: `python -m subscription_login --state-dir /data/chatgpt-auth init-host`.
2. Wykonać lokalne logowanie na Macu powyższą komendą, na właściwe konto/workspace.
3. Przesłać chroniony katalog sesji przez SSH do prywatnego katalogu tymczasowego
   na serwerze. Nie przez czat, repozytorium, logi ani publiczny upload. Wymagane
   prawa właściciela, katalog `0700`, pliki `0600`; kod odrzuca symlink tokenów.
4. W kontenerze, jako użytkownik aplikacji: `python -m subscription_login --state-dir /data/chatgpt-auth import-session /sciezka/do/prywatnego-importu`.
   Import ponownie weryfikuje podpis i tożsamość; nie podmienia host ID runtime.
5. Po potwierdzeniu importu zabezpieczyć/usunąć pozostałe kopie tokenów i nie
   używać już sesji laptopa. **Nie robić logout na laptopie po przeniesieniu** —
   unieważniłby tę samą sesję na serwerze. Odtąd refresh ma jednego właściciela.
6. Sprawdzić `status`, jawne ustawienia obu generatorów oraz kontrolowany test na
   fikcyjnych danych, zanim podłączy się produkcyjne dane.

Odświeżenia rotujących tokenów są serializowane POSIX flock; aktualna sesja jest
odczytywana spod blokady, a nowe tokeny atomowo zapisywane `0600`. Jest to ochrona
systemu plików, nie szyfrowanie i nie ochrona przed rootem/tym samym UID.
Wymiana/import poświadczeń wymaga właściciela; nie pobieramy tokenów Codex,
Hermesa ani Hindsight. Nie logujemy surowych wyjątków providera.

```sh
python -m subscription_login --state-dir /data/chatgpt-auth logout
```

Logout próbuje unieważnić sesję odnawialną, usuwa lokalne tokeny i zachowuje host ID
oraz rejestrację. Jeżeli zdalne unieważnienie nie zostało potwierdzone, odłączyć
aplikację `k90` w ustawieniach ChatGPT. Nie udostępniać raportów z plików poświadczeń.

## Backup, rollback i ograniczenia odbioru

- `/backup` używa API SQLite. Obejmuje pięć dokumentów, ich wersje, historię,
  lokalny ledger/FTS/outbox i stabilny klucz pseudonimów po inicjalizacji tej wersji.
- `.env`, konfigurację, niestandardowy `data/system_prompt.md`, tokeny Garmin/Libre
  i osobną sesję ChatGPT zabezpiecza właściciel osobno. Backup bazy nie jest
  kompletnym backupem całej aplikacji ani zewnętrznej bazy Hindsight.
- Nie kopiować samego aktywnego `k90.db` pomijając WAL. Zachować spójny snapshot.
- Do jawnego eksportu aktualnej treści: `python -m patient_documents /nowy/prywatny/katalog`.
  Eksport tworzy pięć plików Markdown, nie wszystkie rewizje ani pełny backup.
- Przed downgrade'em do wersji czytającej `.md` wykonać eksport aktualnej treści
  i odtworzyć pliki pod kontrolą właściciela. Stare zachowane `.md` są nieaktualne
  po zmianach w SQLite; sam powrót do starego obrazu nie odtworzy bieżących dokumentów.
- Nie usuwać dodatkowych tabel bazy przy wyłączaniu HS. `local` lub `disabled`
  nie kasuje lokalnych źródeł ani danych zdrowotnych. Na czas wdrożenia zachować
  poprzedni obraz i oryginalny backup; nie odtwarzać starej bazy nad nowymi zapisami.

Wyniki testów i niewykonane bramki są w [VERIFICATION.md](VERIFICATION.md).
Założenia projektu: [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md).
