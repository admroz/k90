# Plan wykonawczy: pamięć, dokumenty SQLite i opcjonalna subskrypcja

## Zlecenie i granice

Użytkownik zlecił implementację i testowanie uzgodnionego planu pamięci oraz dodanie
opcjonalnego trybu subskrypcyjnego. Pozostajemy we własnym forku `hermesinski/k90`;
upstream `admroz/k90` jest tylko do odczytu. PR na końcu, bez samodzielnego scalania
ani wdrażania. Dokument ten jest listą odbioru, nie deklaracją ukończenia.

Nie czytamy produkcyjnej bazy, dokumentów, rozmów ani tokenów. Dane testowe są
syntetyczne. Nie zmieniamy konfiguracji działającego k90, Hermesa ani banku
`hermes-default`. Prawdziwe testy Hindsight wolno wykonywać wyłącznie w nowym
banku `k90-test-*`. Bank jest przestrzenią danych, nie dowodem autoryzacji.
Nie dodajemy płatnego fallbacku ani wspólnego magazynu OAuth.

## Kolejność i odbiór

Aktualizacja zakresu 2026-10-25: OWNER_ACCEPTANCE.md ma pierwszeństwo nad
historycznymi bramkami poniżej. Live OAuth/inference jest odroczone do wdrożenia,
nie blokuje przygotowania. CI/container i izolowany HS mają działać na standardowym
GitHub-hosted Linux we własnym forku, bez sekretów i publikacji. Brak bank ACL
w wybranej wersji należy zweryfikować i opisać jako ograniczenie zaufanej sieci.
Nie żądać lokalnego demona Docker. Bieżący postęp: STATUS.md.
Późniejszy dopisek właściciela „Later owner clarification” w OWNER_ACCEPTANCE
odracza rozbudowane HS testy do wdrożenia; ma pierwszeństwo również nad powyższym
wymogiem izolowanego HS CI. Zachować testy adaptera/prywatności i krótki deployment
smoke, nie budować dodatkowej infrastruktury HS/IAM.

1. **Dokumenty pacjenta w SQLite**: pięć dotychczasowych dokumentów, aktualna treść,
   trwałe wersje i daty, bez utraty interfejsu panelu/narzędzi. Jednorazowy,
   idempotentny import Markdown; bez usuwania oryginałów i bez dual-write jako
   dwóch źródeł prawdy. Jawny eksport. Backup SQLite obejmuje dokumenty i wersje.
2. **Pamięć lokalna**: stabilne źródła i wersje, źródłowa historia niezależna od HS,
   FTS5, transakcyjny outbox, retry po awarii/restartach, korekty i usunięcia.
   Odtworzenie indeksu wyłącznie z lokalnych źródeł. Brak automatycznego importu
   całej starej historii produkcyjnej.
3. **Polityka wyjścia**: lokalne maskowanie identyfikatorów, blokowanie sekretów
   i treści local-only, konfigurowalne reguły, fail-closed po błędzie. Jedna granica
   przed HS retain/recall i każdym wywołaniem modelu, także summary, historia,
   przywrócone źródła i wyniki narzędzi. Brak obietnicy pełnej anonimizacji.
   Obrazy wymagają odrębnej, jawnej zgody; nie indeksujemy ich domyślnie w HS.
4. **Hindsight**: wymienny adapter, własny bank, bounded recall przed odpowiedzią,
   daty i odwołania do lokalnych źródeł, ograniczony kontekst, fallback po awarii.
   Świeżość/rewizję i właściciela weryfikujemy lokalnie; sugestie asystenta nie są
   promowane do deklaracji użytkownika. Osobne ustawienia i granice uprawnień.
5. **Subskrypcja**: jawny wybór API/ChatGPT dla rozmowy i summary, własne OAuth PKCE,
   bezpieczne odświeżanie i zapis sesji, modele z katalogu konta, streaming,
   narzędzia i obrazy. Brak automatycznego przejścia do płatnego API po limicie.
6. **Odbiór**: testy offline, lokalny demo end-to-end na syntetykach, rzeczywisty
   bank HS, restart/retry/korekta/odbudowa indeksu, niezależny krytyczny review,
   pełna regresja, dokumentacja uruchomienia/backup/rollback, PR i odczyt stanu CI.

## Checkpoint odbioru 2026-10-25 12:45 UTC — BLOCKED_OWNER, nie READY

Najnowsze testowane źródła: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`.
Stan bramek i następny krok mają pierwszeństwo w STATUS.md; dowody w
VERIFICATION.md, review-evidence/independent_final_review.md oraz
review-evidence/integration_checkpoint_20261025.md. Manifest całości:
review-evidence/acceptance.json ma BLOCKED, nie PASS; niezależny PASS jest
ograniczony do offline security/source review.

| Zakres | Rzeczywisty dowód / brakująca bramka |
| --- | --- |
| documents_sqlite | Syntetyczne testy dokumentów/rewizji/backup/restore i panelu w pełnej regresji; bez migracji produkcji. |
| local_memory | Syntetyczne trwałe źródła, FTS/outbox/retry/rebuild i lokalny E2E; niezależny offline review PASS, bez akceptacji HS ACL/restart. |
| outbound_privacy | Odtworzone niezależne FAIL naprawione TDD; 106 trwałych testów kompozycji; świeży niezależny offline review PASS (202 istniejące i 140 nowych prób, także lokalny HTTP wire); prowadzący ponowił 153 probe PASS. To nie gwarancja pełnej anonimizacji. |
| hindsight_integration | Realny nowy bank testowy: retain/recall/retry/replay/korekta/rebuild/cleanup; brak dowodu restartu usługi i ograniczonej autoryzacji. |
| subscription_adapter | Testy syntetyczne, bez fallbacku; realny finalny adapter/OAuth/refresh/katalog wymaga odrębnej sesji k90 właściciela. |
| regression | Prowadzący 12:39–12:42 UTC na niezmienionym źródle f39ad1f: 404 passed / 1 jawny skip importu (84.17s), frontend 21 passed, JS syntax OK, probe 153 passed / 1 warning. |
| container | Brak lokalnego demona; rzeczywisty build/smoke pending. |
| ci | Push trigger testów dla feature, bez publikacji; API nadal nie pokazuje workflow/run, brak PASS. |

Niezależna bramka lokalnego review została zamknięta. Obie delegowane role
zakończone; koordynator odczytał artefakty i ponowił testy. Pozostały rzeczywiste
wymagania dostępu właściciela: osobne OAuth k90 z wyłączonymi dodatkowymi
kredytami, izolowane HS restart/ACL oraz runner z Dockerem i aktywacja/diagnoza
workflow forka (świeże API nadal bez workflow/run). Po zapewnieniu dostępu
wykonać brakujące rzeczywiste próby, niezależnie sprawdzić ich dowody i dopiero
wtedy ocenić pełne PASS. Bez acceptance PASS/READY ani PR przed wszystkimi bramkami.

## Załączniki i pliki konfiguracyjne

SQLite zostaje źródłem prawdy dla treści pięciu dokumentów pacjenta. Markdown jest
formatem importu/eksportu. Nie przenosimy automatycznie konfiguracji, sekretów,
logów i dużych binariów do bazy. Obecny sposób przechowywania zdjęć trzeba opisać
na podstawie kodu; backup bazy nie może być nazywany kompletnym backupem aplikacji,
jeżeli nadal wymaga osobnych plików załączników lub konfiguracji.

## Zweryfikowany punkt wyjścia

- Dokument architektury pamięci: `docs/MEMORY_ARCHITECTURE.md` (kierunek uzgodniony).
- Użytkownik przekazał wynik testu subskrypcji na Macu/Python 3.14.9:
  `gpt-6.1-sol`, tekst/narzędzie/obraz PASS, renewable_session_revoked=true.
  Kod testera: gałąź `spike/chatgpt-subscription`, commit `835f694`.
- Wyłączenie dodatkowych kredytów potwierdził użytkownik, nie API testera.
- Test nie potwierdza jeszcze produkcyjnego adaptera ani refresh po wygaśnięciu.
- Odczytano zdrowie i OpenAPI dostępnej usługi HS: HTTP 200; spec `1.1.0`.
  To nie dowód restart-persistence, autoryzacji banków ani ukończenia integracji.

## Organizacja pracy i pytania

Prace wykonywane etapami: agent kodujący, osobny krytyczny reviewer, integracja
oraz niezależne uruchomienie testów przez prowadzącego. Maksymalnie dwa aktywne
zadania o rozłącznych zakresach; bez pętli odpytywania i bez mnożenia agentów.
Subagenci zużywają ten sam zasób pracy/modelu; nie są sposobem na obejście limitów.

### Autonomiczna kontynuacja — mandat użytkownika 2026-10-25

Kontynuować bez pytania o rutynowe decyzje implementacyjne aż do gotowości odbioru
lub rzeczywistej przeszkody wymagającej właściciela. Prowadzący odpowiada za integrację;
implementacja i niezależna weryfikacja mają rozłączne role, najwyżej dwa aktywne
zadania i jeden zapisujący do checkoutu. Dwie nieudane poprawki oznaczają zmianę
diagnozy/projektu, nie automatyczny koniec całego zlecenia.

Po przeglądzie kandydatów pod kątem sekretów/PII i skutków workflow robić częste,
logiczne commity i push wyłącznie do `origin/feat/long-term-memory`; także jawnie
opisany checkpoint WIP z niezaliczoną bramką. Sprawdzać zdalny SHA po push.
Nie czekać z persystencją do końcowego PR. PR dopiero po odbiorze; bez scalenia,
wdrożenia i zapisu do main/upstream. Krótki bieżący status w `docs/STATUS.md`,
szczegółowe dowody w `docs/VERIFICATION.md`.

Zewnętrzny nadzorca ma kontrolować możliwość wznowienia co 15 minut bez wywołań
modelu, blokować równoległe uruchomienia i wznawiać pracę dopiero przy wiarygodnym
odczycie wszystkich okien poniżej 80%. Gotowość lub rzeczywisty bloker właściciela
kończy automatyczne uruchamianie. Harmonogram nie znosi wymogu checkpointów ani
kontroli quota w trakcie etapu. Do działania nadzorcy potrzebny jest działający gateway.

### Limity subskrypcji i trwałe checkpointy

Przed każdym większym etapem i po dłuższej partii testów/poprawek wykonać tylko
odczyt: `/opt/hermes/.venv/bin/hermes usage --json`. Sprawdzić `used_percent`
i `resets_at` we wszystkich oknach providera `openai-codex` (Session/Weekly).
Przy >=80% w dowolnym oknie nie zaczynać kosztownego etapu: przy 80–90% dokończyć
najwyżej mały krok w toku, zapisać checkpoint i wrócić do użytkownika. Przy >=90%
natychmiast zapisać stan i zwrócić `PAUSED_FOR_QUOTA`. Brak/nieznany odczyt nie
znaczy 0%: checkpoint i ponowna kontrola przed dalszym większym etapem.
To współpracująca kontrola na granicach etapów, nie twardy runtime kill ani obietnica
automatycznego wznowienia. Nie używać banked reset, nie zmieniać konta/providera
ani nie włączać płatnego fallbacku bez osobnej zgody użytkownika.

Po każdym ukończonym etapie, niezależnie od limitu, uzupełnić `docs/VERIFICATION.md`:
gałąź/worktree, zmienione pliki, dokładne uruchomione polecenia i wyniki, bieżące
blokery, odczyt quota oraz następne bezpieczne polecenia. Nie deklarować ukończenia
na podstawie samego zapisu checkpointu.

Nie blokujemy rozwoju pytaniami o niskiego ryzyka domyślne ustawienia. Ustawienia
prywatności i zewnętrznego dostępu pozostają konserwatywne i konfigurowalne.
Nierozstrzygnięte decyzje wdrożeniowe zapisujemy jako ograniczenia; nie zgadujemy
poświadczeń ani nie obchodzimy logowania. Wymagane nowe logowanie użytkownika
może zostać odłożone, ale nie zastąpione kopiowaniem tokenów innej usługi.
