# k90 — bieżący status zadania

## Stan: WIP/BLOCKED — checkpoint zastanej implementacji

- Repo: `/opt/data/projects/k90`, fork `hermesinski/k90`, gałąź `feat/long-term-memory`.
- Uzgodniony zakres i lista odbioru: `IMPLEMENTATION_PLAN.md`.
- Szczegółowe wykonane próby i ograniczenia: `VERIFICATION.md`.
- Dotychczasowa ostatnia zapisana regresja: backend 278 passed / 1 skipped,
  frontend 21 passed. Dodatkowy niezależny privacy probe: 6 failed / 7 passed.
  Nie są to świeże wyniki ponownie uruchomione w ramach wznowienia.
- Bloker: filtr wyjściowy przepuszcza syntetyczne sekrety w uszkodzonym JSON
  i JSON zakodowanym w string; dowody w `review-evidence/`.
- Audyt wszystkich 51 kandydatów przez read-only reviewera i ograniczony skan
  prowadzącego: bez zidentyfikowanych sekretów/real PII/baz/cache. Workflow i hooks
  sprawdzone; jawny push tylko origin/feat/long-term-memory, bez publikacji obrazu.
- Kolejny etap: checkpoint Git/push, następnie diagnoza i naprawa kontraktu filtra, niezależny review,
  regresja i domknięcie pozostałych bramek.
- Rzeczywiste HS/OAuth, kontener i CI niepotwierdzone według dotychczasowego checkpointu.
- Brak zgody na main/upstream, scalenie, wdrożenie lub migrację danych produkcyjnych.
- PR dopiero po końcowym odbiorze. Częste commity/push na gałąź forka są dozwolone;
  checkpoint WIP nie oznacza gotowości rozwiązania.

## Kontynuacja i limity

Użytkownik zlecił autonomiczną kontynuację 2026-10-25. Rutynowe decyzje techniczne
nie wymagają kolejnego potwierdzenia. Nowe logowanie, koszty, zmiana zakresu
lub osłabienie zabezpieczeń wymagają właściciela.

Odczyt wznowienia: Session 72%, Weekly 11% (usage API,
2026-10-25T08:10:26Z). Resety: 2026-10-25T11:22:00Z / 2026-11-01T06:22:00Z.
Każdy wykonawca sprawdza quota przed większym etapem i po dłuższej partii.
80%: nie zaczynać dużego etapu; 90%: checkpoint i pauza. Nieznany odczyt blokuje
nowy duży etap. Bez banked reset i płatnego fallbacku.

Prywatny nadzorca poza repo: `/opt/data/jobs/k90-autonomy/` (misja, stan, logi).
Automatyczne kontrole wznowienia co 15 minut mają nie używać modelu i nie
uruchamiać drugiego wykonawcy. Nadzorca nie jest twardym odcięciem quota.
Wykonanie w tle i harmonogram wymagają działającego hosta/gatewaya; po restarcie
trwały harmonogram może wznowić pracę z dokumentów, nie z pamięci procesu.
