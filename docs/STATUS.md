# k90 — bieżący status zadania

Stan: PAUSED_FOR_QUOTA — checkpoint WIP; również wykryto zewnętrzną zmianę dokumentu właściciela.

Aktualizacja 2026-10-25 14:24 UTC. Branch feat/long-term-memory, fork
hermesinski/k90, upstream push DISABLED. Bez PR/main/merge/deploy/produkcji.

Zweryfikowane:
- Zachowano początkowe OWNER_ACCEPTANCE.md w e910dd9; remote SHA potwierdzony.
- Compose: env_file .env, minimalne runtime overrides; rozszerzone ignore secrets.
- TDD: 2 failed → 2 passed. Pełna regresja 406 passed / 1 skipped (84.51s),
  frontend 21 passed, JS syntax OK. Wyłącznie syntetyki i offline guard.
- Oficjalny standalone Compose v5.6.1, checksum zgodny: rzeczywiste config na
  syntetycznym env potwierdziło passthrough nowych K90 opcji, TZ, /data i odmowę
  pustego hasła. Nie testowano uruchomienia kontenera.
- Nowy niezależny reviewer przeczytał zmiany, ale przerwał przed testami przy
  niedostępnym odczycie własnej quota. To NIE jest niezależny PASS. Dzieci zakończone.

Otwarte:
- Dokończyć niezależny review nowej konfiguracji oraz diagnostykę Actions.
  API: enabled=true, zero workflows, workflow GET i enable PUT 404; odczyt
  po próbie nadal zero. Przyczyna niepotwierdzona, nie eskalować ogólnej diagnozy.
- CI/container build/smoke niewykonane. Nie żądać lokalnego Docker dostępu.
- OAuth usability/topologia wymaga dalszego odczytu kodu. Live login/inference
  odroczone przez właściciela, NIE blokuje przygotowania.
- Podczas sesji zewnętrznie dopisano „Later owner clarification” w OWNER_ACCEPTANCE:
  rozbudowane HS CI/restart/IAM nie jest już bramką, realny HS smoke przy wdrożeniu.
  Zmianę zachowano, bez nadpisania. Przerwano dalszą implementację wobec naruszenia
  założenia jednego writera. Kolejny nadzorowany etap musi potwierdzić wyłączność
  i odczytać pełny nowy mandat; nie budować rozbudowanego HS fixture systemu.

Limity: usage_api 14:24:21Z Session 82%, Weekly 26%; resety
2026-10-25T16:33:40Z / 2026-11-01T06:22:00Z. Bez reset/fallback/account switch.
Kolejny duży etap tylko przy świeżym <80% we wszystkich oknach.

Dowody: review-evidence/compose_checkpoint_20261025.md i VERIFICATION.md.
Manifesty historyczne BLOCKED nie zostały zastąpione PASS. Nie READY.
Checkpoint źródeł i origin: c3b00f64db2472864e8a35869c5669e856ef47ce,
ls-remote zgodny, checkout czysty po push. Po nim tylko docs status/quota.
Końcowy dokumentacyjny SHA w prywatnym outcome.json i git HEAD/ls-remote.
