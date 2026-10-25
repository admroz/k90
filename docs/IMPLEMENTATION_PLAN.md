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
