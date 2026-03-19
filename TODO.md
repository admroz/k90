# TODO — k90

Ten plik jest jedyną utrzymywaną listą zadań projektu: priorytety, backlog, notatki operacyjne i rzeczy zrobione.

## Now

- [ ] Ustawić i zweryfikować poprawną strefę czasową w całej aplikacji.
  Cel: jedna spójna data/godzina w Signal, SQLite, sync Garmin i odpowiedziach agenta.
  Do sprawdzenia: `APP_TIMEZONE`, istniejące rekordy w bazie i czy potrzebny jest jednorazowy fix danych.

- [ ] Poprawić kontekst krótkoterminowy agenta przy rozmowie o jedzeniu i zdrowiu.
  Problem: agent po zgłoszeniu obiadu nie pamięta dobrze śniadania ani bieżących danych z ostatnich dni.
  Kierunek: dołączać do promptu skróty z ostatnich 3-5 dni: posiłki, aktywności, waga, ciśnienie, sen.

- [ ] Dodać bezpieczny wgląd w bazę na produkcji.
  Minimum: `bash` i `sqlite3` w kontenerze lub równoważna ścieżka diagnostyczna.
  Cel: szybkie sprawdzenie `posilki`, `waga`, `sync_status`, `patient_summary` bez ręcznego kopiowania plików.

- [ ] Dodać alternatywny kanał komunikacji przez Telegram.
  Etap 1: Telegram równolegle do Signal.
  Etap 2: ocena czy Signal można uprościć albo całkiem wyłączyć.
  Powód: Signal działa, ale kontener jest ciężki i wymaga numeru telefonu; bot Telegram może uprościć deployment.

## Next

- [ ] Zbudować prosty frontend do podglądu danych live, dostępny tylko z sieci domowej.
  Zakres początkowy: dashboard zdrowotny, lista posiłków, podstawowe operacje na posiłkach.
  Inspiracja: dawne `prywatne/dashboard.html` i `prywatne/dieta.html`, ale na żywych danych z bazy.

- [ ] Dodać bezpieczny live-wgląd w bazę przez osobne narzędzie lub kontener.
  Kierunek: coś w rodzaju `phpMyAdmin` dla SQLite, ale bez wystawiania do Internetu i tylko z sieci domowej.
  To może być osobny kontener administracyjny albo lekki widok w nowym frontendzie.

- [ ] Doprecyzować strategię backupów i snapshotów SQLite.
  Wymagania:
  - backup ma być bezpieczny dla SQLite w trybie WAL,
  - musi być jasne jak odtworzyć backup,
  - musi działać na Synology i lokalnie.
  Preferowany kierunek:
  - snapshot logiczny przez `sqlite3 /data/k90.db ".backup ..."`,
  - opcjonalnie archiwizacja całego `data/` jako drugi poziom backupu,
  - retencja 30 dni,
  - możliwość codziennego rsync na laptopa.

- [ ] Rozszerzyć observability.
  Dodać lepsze logi z głównej pętli agenta, wywołań narzędzi, błędów i liczników syncu.
  Osobno ocenić czy logi warto trzymać w SQLite z retencją i późniejszym podglądem przez frontend.

- [ ] Uporządkować przejście na OpenAI API / Codex w pracy nad projektem i w samym agencie.
  Wyjaśnić decyzję architektoniczną: co zostaje w LiteLLM, a co przechodzi na bezpośrednie API OpenAI.

## Data Model

- [ ] Zaplanować przeniesienie trwałych danych z plików `.md` do SQLite.
  Dotyczy to zwłaszcza danych pacjenta i notatek, które dziś są rozproszone między bazą i plikami.
  Warunek: migracja bez utraty danych i bez pogorszenia edytowalności danych.

- [ ] Przy migracji danych do bazy rozpocząć sensowną rozmowę o embeddings.
  Pytania do rozstrzygnięcia:
  - co embeddingować: pliki pacjenta, historię rozmów, podsumowania, dokumenty,
  - czy embeddings mają wspierać retrieval do promptu czy tylko wyszukiwanie,
  - gdzie je trzymać: SQLite czy osobny store.

- [ ] Dodać komendy i procedury operacyjne do diagnozy produkcji.
  Przykłady: podgląd ostatnich posiłków, ostatniego syncu Garmin, rozmiaru i integralności bazy.

## Frontend

- [ ] Zaprojektować minimalny model zabezpieczenia frontendowego.
  Na start wystarczy dostęp tylko z sieci domowej i proste hasło albo reverse proxy z auth.

- [ ] Udostępnić przez frontend podgląd live danych zdrowotnych i historii posiłków.
  Priorytet wyżej niż chat przez WWW.

- [ ] Dodać możliwość podstawowej edycji posiłków z poziomu frontendowego UI.
  Przykład: lista, szczegóły, usuwanie, korekta opisu i makro.

- [ ] Rozważyć chat z agentem przez frontend.
  To jest niski priorytet; najpierw podgląd i operacje administracyjne.

## Later

- [ ] Obsługa PDF przez Signal lub docelowo także przez inne kanały.
  Trzeba sprawdzić jak `signal-cli-rest-api` zwraca PDF i jak przekazać go do modelu.

- [ ] Lepsze rozpoznawanie typu załącznika.
  Agent powinien rozróżniać: posiłek, dokument medyczny, inne zdjęcie.

- [ ] Rozważyć lepszy model do analizy zdjęć jedzenia.
  Notatka historyczna: Haiku mylił ryż brązowy z makaronem; do porównania np. Sonnet.

- [ ] Raporty tygodniowe i miesięczne.
  Warianty: PDF, wykresy matplotlib, krótkie podsumowania przez Signal lub frontend.

- [ ] Powiadomienia proaktywne.
  Przykład: poranny skrót z wagą, HRV i planem dnia.

- [ ] Kontekst sezonowy / cykliczny.
  Np. dzień po treningu, gorszy sen, okres większej aktywności.

- [ ] Sprawdzić sens przejścia części promptów/systemu na angielski dla oszczędności tokenów.

- [ ] Rozważyć nowy typ danych: FreeStyle Libre 2.

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

### 2026-03-19

- [x] Naprawiony bug synchronizacji Garmin z datą końcową liczoną przy starcie procesu.
  Skutek błędu: agent mógł twierdzić, że zrobił dzisiejszy sync, ale faktycznie pobierał dane tylko do wczoraj.

- [x] Dodany checkpoint WAL po syncu Garmin i po zapisie/usunięciu posiłku.
  Cel: zmniejszyć ryzyko oglądania nieaktualnego `k90.db` po skopiowaniu samego pliku bazy.

- [x] Backlog został uporządkowany do jednego pliku `TODO.md`.

### Wcześniej zrobione

- [x] Dane Garmin są synchronizowane bezpośrednio do SQLite, bez standardowego flow przez CSV.

- [x] Istnieje slash-komenda `/update`, która uruchamia sync Garmin bez udziału LLM.

- [x] Istnieje slash-komenda `/summary` do podglądu aktualnego patient summary.

- [x] Jest auto-sync Garmin przy pierwszej wiadomości danego dnia.

- [x] Agent zapisuje historię rozmów, patient summary i dane zdrowotne w SQLite.

- [x] Agent obsługuje obrazy w Signal i potrafi analizować zdjęcia posiłków.
