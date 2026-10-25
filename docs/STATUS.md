# k90 — bieżący status zadania

Stan: CONTINUE — wznowienie po resecie, końcowe przygotowanie personal self-hosted.
Aktualizacja: 2026-10-25 16:52 UTC. Feature fork, bez PR/main/upstream/deploy.

Zachowano i wypchnięto dopisek właściciela o dwóch stackach w 0a7939a;
remote SHA zgodny. Jedyny lock writer: nadzorca PID212009, rodzic tej sesji.
Quota 16:45:57Z: Session 8%, Weekly 28%, resety 21:37:40Z / Nov 1 06:22Z.
Nowa polityka >=90% pauza; 80% ostrzeżenie, unknown fail-closed. Bez reset/fallbacku.

Zweryfikowane:
- Zdiagnozowano Actions: zalogowana strona pokazała oddzielną blokadę workflow
  odziedziczonych przy forkowaniu, mimo REST enabled=true. Włączono przejrzane
  workflows przez dostępne konto; odczyt strony „Actions Enabled” i REST active.
- Rzeczywisty test-only workflow_dispatch na 0a7939a: run 40213398796 SUCCESS.
  Python 406 passed / 1 skip, frontend 21 PASS, Docker build i network-none smoke
  z restartem adaptera Telegram PASS. Job publikacji skipped. Bez sekretów/LLM.
- Niezależny scoped review: Compose/OAuth offline funkcjonalnie PASS, 26+8 testów
  i rzeczywista walidacja Compose PASS; brak high/critical. Zalecono rekurencyjne
  Docker ignore i pełny runbook. Live OAuth/HS nadal owner-deferred.
- Nowy ignore contract TDD: 1 failed/2 passed → 3 passed. Dodano mały CI smoke
  prawdziwej semantyki Docker na wyłącznie syntetycznym kontekście.

Otwarte:
- Pełna regresja i CI/container na nowym źródle oraz niezależny review nowego smoke.
- Finalny runbook dwóch osobnych stacków, Mac-local OAuth/private SSH import,
  backup, rollout i rollback; bez wymyślania ścieżek istniejącego stacka.
- Odświeżyć manifesty do wspólnego testowanego source SHA po rzeczywistych dowodach.

Nie READY. Historyczne BLOCKED manifesty nie są aktualnym zakresem właściciela;
realne logowanie/inference i topology-specific HS smoke są odroczone do wdrożenia.
Źródłowy checkpoint po tym wpisie: git HEAD; exact remote przez ls-remote.
