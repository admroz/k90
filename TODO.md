# TODO — k90

Ten plik jest jedyną utrzymywaną listą zadań projektu: priorytety, backlog, notatki operacyjne i rzeczy zrobione.

## Now

- [ ] Doprecyzować i przetestować projekt pamięci długoterminowej.
  Uzgodnione założenia i kryteria: [Pamięć k90](docs/MEMORY_ARCHITECTURE.md).
  Hindsight ma być wymienialnym indeksem, nie jedynym magazynem danych.
  Plan nie jest implementacją; brak zgody na automatyczny import produkcyjnej historii.
- [ ] Zaprojektować trwałe źródła i kolejkę indeksowania w SQLite.
  Pełna historia i wersje niezależne od HS, atomowy zapis źródła i zlecenia,
  retry, aktualizacja/usuwanie oraz odbudowa indeksu.
- [ ] Ustalić politykę prywatności przed podłączeniem pamięci do danych rzeczywistych.
  Maskowanie identyfikatorów, blokowanie sekretów i lokalnych treści, kontrola
  wszystkich wyjść do modeli; osobna polityka obrazów i dokumentów.
- [ ] Przygotować adapter HS, automatyczny recall i lokalny fallback FTS5.
  Osobny bank testowy, źródła z datami, limity czasu/kontekstu i testy awarii.

- [ ] Ocenić UI desktop/mobile oraz prawdziwy model na kopii danych przed kolejnym wdrożeniem.
  Frontend jest już częścią `main`; procedury i smoke test kontenera: `WEB.md`.
  Aktualny cel CI to AMD64. Powrót do ARM64 wymaga osobnego włączenia i testów.
  Ta lista nie potwierdza wersji działającej na serwerze.

- [ ] Zaplanować przeniesienie trwałych danych z plików `.md` do SQLite.
  Dotyczy danych pacjenta i notatek; bez utraty danych i pogorszenia edytowalności.
  Nie łączyć koniecznie tej migracji z pierwszym pilotem Hindsight.

- [ ] Rozszerzyć komendy i procedury operacyjne do diagnozy produkcji.
  `/debug` już pokazuje użycie, summary i statusy syncu; dalszy zakres to m.in.
  integralność/rozmiar bazy i wygodny podgląd ostatnich zapisów.

## Next

- [ ] Rozszerzyć observability bez zapisywania wrażliwych treści w logach.
  Obecny kod loguje rundy agenta, nazwy narzędzi i błędy. Rozważyć trwałe logi
  z retencją i podglądem WWW oraz metryki jakości/kosztu/opóźnień pamięci.

- [ ] Dodać runtime'owe przełączniki funkcji i modeli zapisywane w SQLite.
  Obecnie modele i przełączniki pochodzą z konfiguracji środowiskowej.
  Cel: komendy administracyjne i feature flags bez odtwarzania kontenera.

- [ ] Ocenić sens migracji GPT-5.6 do Responses API.
  Rodzina Sol już używa `responses_api.py`; GPT-5.6 pozostaje przy
  LiteLLM / Chat Completions z `reasoning_effort=none`.

## Data Model

- [ ] Doprecyzować zakres indeksowania i wersjonowania zgodnie z planem pamięci.
  Rozmowy i kontekst decyzji są priorytetem; pomiary pozostają w SQLite.
  Ustalić retencję, korekty i usuwanie, schemat załączników oraz eksport źródeł.

## Frontend

- [x] Wspólny chat WWW/Telegram, dashboard, posiłki z wyborem dnia, regeneracja,
  aktywność, podgląd dozwolonych tabel i dokumentów są zaimplementowane na `main`.
- [x] Podstawowe logowanie hasłem, sesje, kontrola źródła żądań, limity i nagłówki
  bezpieczeństwa są zaimplementowane; panel jest przeznaczony do dostępu prywatnego.
  Nie jest to deklaracja pełnego audytu bezpieczeństwa ani konfiguracji serwera.
- [ ] Dodać formularze edycji posiłków i dokumentów (obecnie podgląd; zapis przez agenta).
- [ ] Dodać podgląd pamięci ze źródłami, korektami i możliwością usunięcia.
- [ ] Rozważyć dodatkowe narzędzie administracyjne bazy tylko jeśli istniejący
  odczyt tabel w WWW i komendy nie wystarczą; bez domyślnego dostępu do dowolnego SQL.

## Later

- [ ] Dodać bezpieczny wgląd w bazę na produkcji.
  Minimum: `bash` i `sqlite3` w kontenerze lub równoważna ścieżka diagnostyczna.
  Cel: szybkie sprawdzenie `posilki`, `waga`, `sync_status`, `patient_summary` bez ręcznego kopiowania plików.

- [ ] Obsługa PDF przez Telegram.
  Trzeba pobrać dokument przez Bot API i ustalić sposób przekazania go do modelu.

- [ ] Lepsze rozpoznawanie typu załącznika.
  Agent powinien rozróżniać: posiłek, dokument medyczny, inne zdjęcie.

- [ ] Rozważyć lepszy model do analizy zdjęć jedzenia.
  Notatka historyczna: Haiku mylił ryż brązowy z makaronem; do porównania np. Sonnet.

- [ ] Raporty tygodniowe i miesięczne.
  Warianty: PDF, wykresy matplotlib, krótkie podsumowania przez Telegram lub frontend.

- [ ] Powiadomienia proaktywne.
  Przykład: poranny skrót z wagą, HRV i planem dnia.

- [ ] Kontekst sezonowy / cykliczny.
  Np. dzień po treningu, gorszy sen, okres większej aktywności.

- [ ] Sprawdzić sens przejścia części promptów/systemu na angielski dla oszczędności tokenów.

- [ ] Rozważyć zagęszczenie danych Libre przez polling `glucoseMeasurement` co 1 minutę.
  Cel: mieć gęstszy bieżący przebieg niż `graphData` co 15 minut.
  Ograniczenia:
  - nie odtwarza historii wstecz,
  - nie wypełnia luk z downtime kontenera,
  - nie powinno zastępować bazowej historii z `graphData`.

- [ ] Zautomatyzować cykliczne backupy SQLite przez cron lub zewnętrzny scheduler.
  Założenie: używać tej samej ścieżki backupu co komenda `/backup`, a nie osobnej implementacji.

## Operational Notes

- Baza produkcyjna to SQLite i część zapisów może przechodzić przez WAL.
  W praktyce oznacza to, że kopiowanie samego `k90.db` nie zawsze daje aktualny stan.

- Snapshot bazy powinien być robiony świadomie.
  Preferować `sqlite3 .backup` albo checkpoint + kopiowanie kompletu `k90.db`, `k90.db-wal`, `k90.db-shm`.

- Jeśli logi trafią do SQLite, muszą mieć retencję i ograniczony poziom szczegółowości.
  Inaczej baza zacznie puchnąć bez realnej wartości operacyjnej.

- Po zmianach w kodzie produkcyjnym warto mieć krótką checklistę:
  - deploy / restart kontenera,
  - test `/update`,
  - test zapisu posiłku,
  - podgląd `sync_status` i `posilki`.

## Done

### 2026-09-03

- [x] Zastąpiony Signal przez Telegram Bot API z long pollingiem.
  Efekt: jeden kontener aplikacji, brak osobnego numeru telefonu, webhooka i publicznego portu.
  Transport obsługuje tekst, komendy slash, zdjęcia, whitelistę właściciela i dzielenie długich odpowiedzi.

- [x] Błąd odświeżania patient summary przy starcie nie blokuje już uruchomienia transportu wiadomości.

- [x] Dodany przełącznik `LIBRE_ENABLED`; wyłącza wszystkie ścieżki pobierania Libre bez usuwania danych historycznych.

- [x] Nieoczekiwany wyjątek synchronizacji Garmin lub Libre nie przerywa już obsługi wiadomości agenta.

### 2026-03-19

- [x] Dodany ręczny backup SQLite przez komendę `/backup`.
  Zakres:
  - snapshot zapisuje się do katalogu `backups/`,
  - nazwa pliku używa czasu `Europe/Warsaw`,
  - działa retencja backupów,
  - mechanizm jest wspólny pod przyszły cron / scheduler.

- [x] Ustawiona i zweryfikowana poprawna strefa czasowa w całej aplikacji.
  Efekt: jedna spójna data/godzina w komunikatorze, SQLite, sync Garmin i odpowiedziach agenta.

- [x] Poprawiony kontekst krótkoterminowy agenta przy rozmowie o jedzeniu i zdrowiu.
  Efekt: agent dostaje skrót z ostatnich dni zamiast polegać wyłącznie na gołej historii rozmowy.

- [x] Naprawiony bug synchronizacji Garmin z datą końcową liczoną przy starcie procesu.
  Skutek błędu: agent mógł twierdzić, że zrobił dzisiejszy sync, ale faktycznie pobierał dane tylko do wczoraj.

- [x] Dodany checkpoint WAL po syncu Garmin i po zapisie/usunięciu posiłku.
  Cel: zmniejszyć ryzyko oglądania nieaktualnego `k90.db` po skopiowaniu samego pliku bazy.

- [x] Backlog został uporządkowany do jednego pliku `TODO.md`.

- [x] Włączony FreeStyle Libre 2 do modelu danych i syncu aplikacji.
  Zakres v1:
  - osobna tabela SQLite dla glukozy,
  - importer/sync z LibreLinkUp,
  - podstawowy odczyt historii i korelacja z posiłkami.

- [x] Zrobiony PoC FreeStyle Libre 2 w katalogu `libre/`.
  Wynik:
  - automat przez LibreLinkUp działa,
  - historia jest dostępna przez `graphData` co ok. 15 minut,
  - najświeższy odczyt jest dostępny osobno jako `glucoseMeasurement`,
  - biblioteka `libre-linkup-py` wymagała lokalnego obejścia błędu dla kraju `PL`.
  Notatka: katalog `libre/` jest tymczasowy i może zostać usunięty po przeniesieniu finalnej integracji do głównego kodu.

### Wcześniej zrobione

- [x] Dane Garmin są synchronizowane bezpośrednio do SQLite, bez standardowego flow przez CSV.

- [x] Istnieje slash-komenda `/update`, która uruchamia sync Garmin bez udziału LLM.

- [x] Istnieje slash-komenda `/summary` do podglądu aktualnego patient summary.

- [x] Jest auto-sync Garmin przy pierwszej wiadomości danego dnia.

- [x] Agent zapisuje historię rozmów, patient summary i dane zdrowotne w SQLite.

- [x] Agent obsługuje obrazy z komunikatora i potrafi analizować zdjęcia posiłków.
