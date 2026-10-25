# k90 — bieżący status zadania

## Stan: WIP — poprawki privacy po niezależnym FAIL, finalny review pending

Aktualizacja 2026-10-25 12:02 UTC. Gałąź `feat/long-term-memory` w forku
`hermesinski/k90`; upstream push DISABLED. Bez PR, main writes, merge/deploy
ani produkcyjnej migracji. Plan odbioru: IMPLEMENTATION_PLAN.md; szczegółowe
wykonanie i ograniczenia: VERIFICATION.md.

### Ukończony etap (nie pełny odbiór)

- Niezależny read-only reviewer wykrył JSON w kluczach, duplikaty local_only
  i utratę restrykcji dokumentów przy kompozycji summary. Prowadzący odtworzył
  trzy przepływy FAIL; szczegóły i poprawki TDD w review-evidence/privacy_composition_fix.md.
- Wspólny strict decode odrzuca duplikaty, inspekcja kluczy ma wspólne budżety,
  oryginalne źródła są sprawdzane przed formatowaniem. Lokalnych oryginałów
  nie zmieniamy. Prowadzący dopisał 20 regresji escaped scalar reserved keys.
- Świeża finalna regresja prowadzącego: 404 passed / 1 skipped (105.83s),
  skip tylko niewybranego lokalnego importu; probe 13 passed; frontend 21 passed,
  JS syntax OK. Wyłącznie syntetyki i atrapy odbiorników, nie dowód integracji.

### Checkpointy i pozostałe bramki

- Ostatni potwierdzony lokalny/zdalny checkpoint przed poprawką:
  `4afa7083dc4286d3677b3d4a48f2501b52ca2011`. Bieżący commit utrwala poprawkę;
  jego exact SHA ustala git HEAD i odczyt ls-remote po push.
- Następny krok: niezależny adversarial review finalnych źródeł, następnie
  rzeczywiste bramki HS/OAuth/container/CI. Zielone testy nie zastępują review.
- Docker lokalnie niedostępny (brak demona). Real HS adapter przeszedł syntetyczne
  retain/recall, retry, replay, korektę i rebuild w nowym `k90-test-*` banku;
  cleanup potwierdzony odczytem 404. Nadal brak dowodu ACL i restartu usługi.
- Real OAuth wymaga osobnej sesji k90 właściciela; nie używać tokenów Hermesa.
- GitHub API: workflow list pusta, dispatch 404, Actions enabled. Dodano push
  testów na tę feature branch (job publikacji nadal tylko main), bez wczesnego PR.
  Wynik nowego push CI oczekuje; konfiguracja zmienia wyłącznie trigger testów.

### Limity i zasady

Quota usage_api 2026-10-25T12:02:09Z: Session 35%, Weekly 19%.
Resety: 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z.
Przed dużym etapem i po długich partiach odczytać wszystkie okna. >=80%:
bez nowego dużego etapu; >=90% lub unknown: checkpoint/pauza. Bez dodatkowych
resetów, paid fallbacku ani zmiany konta/providera. Jeden writer; lock nadzorcy
potwierdzony. Dwie delegowane role zakończone, żaden writer nie pozostaje w tle.

Nadzorca poza repo zapisuje wynik w `/opt/data/jobs/k90-autonomy/outcome.json`;
CONTINUE nie oznacza gotowości. Gotowość wymaga pełnego odbioru i niezależnego
PASS ze zgodnym tested commit. PR na końcu; brak automatycznego scalenia/wdrożenia.
