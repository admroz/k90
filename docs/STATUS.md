# k90 — bieżący status zadania

## Stan: BLOCKED_OWNER — niezależny review offline PASS; brakuje dostępu do bramek integracji

Aktualizacja 2026-10-25 12:45 UTC. Gałąź `feat/long-term-memory` w forku
`hermesinski/k90`; upstream push DISABLED. Bez PR, main writes, merge/deploy
ani migracji produkcji. Odbiór integracji nadal nieukończony.

### Zweryfikowane w tej sesji

- Źródło `f39ad1fd54674f78be6a4ca35a1064fdc39a37a2`; później tylko docs.
  Zastany HEAD i origin zgodne: `8133b1bbd1488ef8747095fb39a5bfd9f098e1b7`;
  checkout na wejściu czysty, lock nadzorcy potwierdzony, bez zastanej pracy.
- Niezależny read-only adversarial review: scoped PASS; 202 istniejące testy
  i 140 nowych przypadków, również rzeczywiste lokalne odbiorniki HTTP.
  Brak odtworzonej blokującej luki w badanym zakresie. Nie jest to akceptacja
  integracji, pełnej anonimizacji ani wdrożenia. Raport i probe pliki w
  `review-evidence/independent_final_*`, manifest `independent-review.json`.
- Prowadzący po odczycie dowodów ponowił: Python 404 passed / 1 skipped
  (84.17s; skip wyłącznie niewybranego importu), frontend 21 passed,
  JS syntax OK, historyczny + nowe probe: 153 passed / 1 warning (17.73s).
  Syntetyki i offline guard; LiteLLM warning dotyczący event loop.
- Role niezależnej weryfikacji i implementacyjnego utrwalenia dowodów zakończone.
  Brak aktywnych dzieci/writerów. Nie zmieniano aplikacji ani polityki prywatności.

### Pozostałe bramki zewnętrzne — nie READY

1. Właściciel: odrębne logowanie aplikacji k90 i potwierdzenie wyłączonych
   dodatkowych kredytów; następnie realny finalny adapter, refresh, katalog,
   streaming/tools/image. Nie wolno użyć tokenów Hermesa ani przesyłać ich w czacie.
2. HS: izolowana restartowalna instancja lub okno restartu zarządzane przez
   właściciela; bank-restricted test endpoint/token i dozwolona/odmowna tożsamość.
   Historyczny realny test retain/recall/retry/rebuild/cleanup jest częściowy;
   nie potwierdza ACL ani trwałości po restarcie usługi. Nie restartować wspólnego HS.
3. CI/container: świeżo 12:32 UTC Docker bez demona; GitHub API enabled=true,
   workflows total_count=0, feature runs puste także po push o 12:45 UTC.
   Potrzebna aktywacja/diagnoza
   workflow forka przez właściciela i autoryzowany runner z Dockerem.
   Przyczyna niepotwierdzona. Pipeline ma build/smoke bez publikacji na feature.

### Limity i checkpoint

usage_api 2026-10-25T12:45:05Z: Session 63%, Weekly 23%.
Resety: 2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z.
Bez resetów, paid fallbacku i zmian konta/providera. Próg >=80%/unknown pauza.

Checkpoint dowodów lokalnie/zdalnie potwierdzony ls-remote:
`e31a42754fa181accf2fc0f7a698afaae0996117`; po push checkout był czysty.
Ten końcowy wpis i manifest BLOCKED są wyłącznie docs; ich zamykający commit
identyfikuje HEAD i zdalne refs/heads/feat/long-term-memory (SHA po końcowym push
także w prywatnym outcome.json). To nie nowy commit testowanych źródeł.

Następny krok zależy od powyższych trzech działań właściciela. Po zapewnieniu
dostępu wykonać rzeczywiste próby na syntetykach i niezależnie sprawdzić dowody.
`review-evidence/acceptance.json`: BLOCKED, niepuste remaining_gates; bez
READY/PR do zamknięcia całości. Nie powtarzać automatycznie tych samych testów
w zastępstwie brakującego OAuth/HS ACL/restart/container/CI.
Dowody poleceń i ograniczenia: VERIFICATION.md; pełny zakres: IMPLEMENTATION_PLAN.md.
