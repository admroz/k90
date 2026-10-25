# Korekta R1 po niezależnym FAIL

Źródło ocenione FAIL: `1b031e8653b43cdecde444d716fac5ec751385ae`.
Oryginalny raport i JSON zachowane jako `photo-history-original-failed-review.*`;
oryginalne probe'y i ich RED jako `photo-history-original-reviewer-probes.*`.
To korekta implementera, NIE niezależny PASS ani akceptacja.

`project_history` po dotychczasowym pełnym sprawdzeniu sekretów/local-only
przyjmuje w liście wyłącznie słowniki o dokładnych polach `type,text` (string)
albo dotychczas walidowane `type,image_url`. Inne części, skalarne/nested elementy,
nieznane typy i dodatkowe pola tekstu są blokowane. Nie zmieniono zwykłego tekstu,
kontroli prywatności, oryginałów SQL ani uprawnień nowych zdjęć.

Regresja repo obejmuje 15 przypadków rzeczywistego `agent.run_agent` z mieszaną
historią tekst/zdjęcie/błędna część; provider nie może być wywołany.
RED: 14 failed, 1 passed, 34 deselected, exit 1 (`photo-history-r1-red.log`).
Przypadek błędnego detail obrazu był już blokowany przed korektą.

Dokładny prefiks wszystkich uruchomień (cwd checkout):

```sh
env -i HOME=/opt/data/cache/scratch/k90-verification-20261025/photo-home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/photo-data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/photo-data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/photo-auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PATH=/usr/local/bin:/usr/bin:/bin TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 /opt/data/projects/k90/.venv/bin/python -m pytest
```

Argumenty RED: `-q tests/test_photo_history.py -k invalid_history_part --basetemp=/opt/data/cache/scratch/k90-verification-20261025/photo-pytest`.
Argumenty GREEN: `-q tests/test_photo_history.py tests/test_outbound_policy.py tests/test_privacy_composition.py tests/test_privacy_json_boundary.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/photo-pytest`.
Argumenty replay: `-q -s /opt/data/jobs/k90-photo-history/review-original-probes.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/photo-pytest`.

Replay bez jakichkolwiek zmian probe'ów: exit 1, **4 passed, 1 failed**.
Ostatni probe nie ma `pytest.raises`: poprawne odrzucenie przez `PrivacyError`
przerywa go przed providerem i przed późniejszymi print/assert. Nie nazywamy
tego formalnym PASS. Regresja repo sprawdza oczekiwany wyjątek, brak wywołania
providera i niezmieniony oryginał. Dowód: `photo-history-r1-reviewer-replay.log`.

Pierwszy szerzej ukierunkowany przebieg nakładał się omyłkowo z replay w tym samym
basetemp: 177 passed, 1 setup error (readonly SQLite). Zachowany jako
`photo-history-r1-overlap-error.log`, nie jest dowodem GREEN. Powtórzenie sekwencyjne
zapisane w `photo-history-r1-green.log`.

Pełna regresja, frontend i świeży niezależny review końcowego commita pozostają
koordynatorowi po sprawdzeniu quota. Live integracje i wdrożenie nie były testowane.
Brak push/PR oraz zmian kontrolera/outcome. Offline guard pozostał włączony.
Quota początkowa 86%/48%, przed powtórzeniem 88%/48%; bez resetów/fallbacku.

Końcowy sekwencyjny GREEN: **178 passed in 32.54s**, exit 0.
Końcowa quota 2026-10-25 23:22:06 UTC: sesja 88%, tydzień 48%.
`git diff --check` dla źródeł/testów przed commitem: exit 0.
