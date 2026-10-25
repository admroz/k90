# k90 — bieżący status zadania

## Stan: CONTINUE — poprawka JSON przechodzi regresję, czeka niezależny review

- Repo: `/opt/data/projects/k90`, fork `hermesinski/k90`, gałąź `feat/long-term-memory`.
- Uzgodniony zakres i lista odbioru: `IMPLEMENTATION_PLAN.md`.
- Szczegółowe wykonane próby i ograniczenia: `VERIFICATION.md`.
- Świeża regresja prowadzącego: backend 298 passed / 1 skipped (79.66 s),
  frontend 21 passed; składnia JS OK. Pierwotny privacy probe: 13 passed (1.51 s).
- Usunięto odtworzone wycieki malformed JSON/JSON-in-string przez ograniczony
  recursive decode/fail-closed; 20 nowych przypadków. Nie jest to pełna anonimizacja.
- Bramka: niezależny adversarial review NOWEJ poprawki nadal niewykonany.
  Runtime odrzucił trzecią delegację (limit 2 dzieci na sesję); obie role skończone.
- Audyt wszystkich 51 kandydatów przez read-only reviewera i ograniczony skan
  prowadzącego: bez zidentyfikowanych sekretów/real PII/baz/cache. Workflow i hooks
  sprawdzone; jawny push tylko origin/feat/long-term-memory, bez publikacji obrazu.
- Pierwszy checkpoint lokalny/zdalny: a3d54da8c2d20173b1e2a2ae082195039e5e36fa.
- Testowane źródła z poprawką: 6a3b3066653eb08dd519b46e69e0e1ecf33a6661;
  commit wypchnięty i SHA potwierdzony przez ls-remote. Późniejsze zmiany tylko docs.
  Końcowy checkpoint dokumentacji jest HEAD gałęzi; exact SHA przez git/ls-remote.
- Kolejny etap: niezależny review poprawki w świeżej sesji, następnie realne bramki
  HS/OAuth/kontenera/CI. Nie powtarzać audytu zastanej pracy jako finalnego review.
- Rzeczywiste HS/OAuth, kontener i CI niepotwierdzone według dotychczasowego checkpointu.
- Brak zgody na main/upstream, scalenie, wdrożenie lub migrację danych produkcyjnych.
- PR dopiero po końcowym odbiorze. Częste commity/push na gałąź forka są dozwolone;
  checkpoint WIP nie oznacza gotowości rozwiązania.

## Kontynuacja i limity

Użytkownik zlecił autonomiczną kontynuację 2026-10-25. Rutynowe decyzje techniczne
nie wymagają kolejnego potwierdzenia. Nowe logowanie, koszty, zmiana zakresu
lub osłabienie zabezpieczeń wymagają właściciela.

Odczyt: Session 78%, Weekly 12% (usage API,
2026-10-25T08:18:27Z). Resety: 2026-10-25T11:22:00Z / 2026-11-01T06:22:00Z.
Każdy wykonawca sprawdza quota przed większym etapem i po dłuższej partii.
80%: nie zaczynać dużego etapu; 90%: checkpoint i pauza. Nieznany odczyt blokuje
nowy duży etap. Bez banked reset i płatnego fallbacku.

Prywatny nadzorca poza repo: `/opt/data/jobs/k90-autonomy/` (misja, stan, logi).
Automatyczne kontrole wznowienia co 15 minut mają nie używać modelu i nie
uruchamiać drugiego wykonawcy. Nadzorca nie jest twardym odcięciem quota.
Wykonanie w tle i harmonogram wymagają działającego hosta/gatewaya; po restarcie
trwały harmonogram może wznowić pracę z dokumentów, nie z pamięci procesu.
