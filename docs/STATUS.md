# k90 — bieżący status zadania

## Stan: CONTINUE — checkpoint po poprawkach; finalny niezależny review pending

Aktualizacja 2026-10-25 12:16 UTC. Gałąź `feat/long-term-memory` w forku
`hermesinski/k90`; upstream push DISABLED. Bez PR, main writes, merge/deploy
ani produkcyjnej migracji. Pełne bramki: IMPLEMENTATION_PLAN.md; dowody:
VERIFICATION.md i review-evidence/integration_checkpoint_20261025.md.

### Zweryfikowane

- Niezależny reviewer znalazł trzy kolejne klasy wycieku; prowadzący je odtworzył.
  Implementator naprawił strict decode i kontrolę źródeł przed kompozycją;
  prowadzący dodał 20 regresji escaped scalar reserved keys. Łącznie 106 trwałych
  testów kompozycji, z zachowaniem Markdown i oryginałów lokalnych.
- Najnowsze testowane źródła: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`.
  Prowadzący: 404 passed / 1 skipped (84.41s), skip tylko niewybranego importu;
  frontend 21 passed, JS syntax OK. Probe pierwotnej luki: 13 passed.
- Real HS w nowym losowym banku `k90-test-*`: retain/recall, zdalna redakcja,
  retry z SQLite po symulowanej awarii, replay bez duplikatu, korekta i rebuild.
  Usunięcie obu utworzonych banków potwierdzone odczytem 404. Bez istniejących banków.
- Checkpoint poprawki: `289d3ffd918a066fdf9a8dc9d0cda24c8fd8d585`.
  Lokalny/zdalny source checkpoint CI: `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`,
  push i SHA potwierdzone przez ls-remote. Późniejszy checkpoint wyłącznie docs;
  jego dokładny SHA ustala HEAD/zdalna gałąź po końcowym push.

### Następny etap i niewykonane bramki

1. Świeża sesja: niezależny read-only adversarial review f39ad1f. Dwie role
   zakończyły pracę; trzecia delegacja odrzucona przez limit całej sesji 2/2.
   Nie jest to approval, błąd kodu ani bloker wymagający właściciela.
2. Real OAuth finalnego adaptera: właściciel musi zalogować odrębną aplikację k90
   i potwierdzić wyłączone dodatkowe kredyty; żadnych tokenów Hermesa/Git/chat.
3. HS: brak dowodu ACL i persistence po restarcie usługi. Potrzebne izolowane
   restartowalne środowisko lub okno restartu zarządzane przez właściciela oraz
   ograniczone uprawnienia testowe. Nie restartować wspólnej usługi samowolnie.
4. Container/CI: lokalny Docker bez demona. GitHub Actions enabled=true, lecz
   workflow/runs puste i dispatch 404; także po dodaniu feature push triggera.
   Przy ponownym pustym odczycie potrzebna aktywacja/diagnoza workflow przez
   właściciela lub autoryzowany runner z Dockerem. Przyczyna niepotwierdzona.
   Job publikacji nadal wyłącznie main; nie tworzono wczesnego PR.

Po niezależnym review poprawić ewentualne lokalne ustalenia; gdy pozostaną tylko
zewnętrzne wymagania, zapisać BLOCKED_OWNER z minimalnymi działaniami powyżej.
Bez manifestów PASS/READY dopóki wszystkie bramki nie mają rzeczywistych dowodów.

### Limity

usage_api 2026-10-25T12:16:30Z: Session 47%, Weekly 20%.
Resety: 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. Kontrola przed etapem
oraz po długich partiach; >=80% bez nowego dużego etapu, >=90%/unknown pauza.
Bez dodatkowych resetów, paid fallbacku ani zmiany konta/providera. Jeden writer,
lock nadzorcy potwierdzony. Żadne dziecko/writer nie pozostaje w tle.
