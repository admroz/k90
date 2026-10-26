# Niezależny przegląd: FAIL

- Commit: `1b031e8653b43cdecde444d716fac5ec751385ae`.
- Baza: `17beba2353cbc1e1a2d39d71bc9b5a78f11a2ed4`.
- Świeży kontekst niezależnego recenzenta; bez zmian źródeł, commitów i pushy.
- Kontrakt: `mission.md`; wyłącznie syntetyczna weryfikacja offline.

## R1 — MEDIUM — nieznane załączniki i błędne części historii przechodzą do providera

**Miejsce:** `outbound_policy.py:68-70` (pętla projekcji `58-70`); wywołanie `agent.py:79`.

Walidacja struktury obejmuje wyłącznie dokładne `type=image_url`. Gałąź `else` przenosi każdy inny element bez walidacji schematu wiadomości. Końcowe `PrivacyPolicy.sanitize` sprawdza ogólne drzewo i listę zabronionych nazw, nie poprawność części wiadomości. Przechodzą m.in.:

```json
{"type":"file_url","file_url":{"url":"https://synthetic.invalid/private.pdf"}}
{"type":"unrecognized_attachment","payload":"synthetic binary reference"}
{"type":"text","text":123}
null
```

**Rzeczywisty probe rozmowy:** syntetyczny rekord historii zawierał tekst, rozpoznane zdjęcie oraz `file_url`. `agent.run_agent` przy `K90_ALLOW_MODEL_IMAGES=false` zwrócił `('Synthetic answer', False)`, wywołując przechwycony provider Chat Completions. W payloadzie pozostał `file_url`, a obraz zastąpił znacznik. Oryginalny rekord SQL pozostał niezmieniony. Dowód: `review-original-probes.log:2-3,115-126`. Żadnego rzeczywistego providera ani adresu załącznika nie wywołano.

To nie tylko niepełny test: wcześniej przy wyłączonej zgodzie taki mieszany rekord blokował obraz; teraz usunięcie obrazu pozwala nieznanemu załącznikowi przekroczyć granicę wysyłki. Rzeczywisty provider może go odrzucić, ale dopiero po otrzymaniu payloadu. Kontrakt wymaga odrzucenia lokalnie. Dokumentacja `docs/OPERATIONS_MEMORY_AUTH.md` deklaruje mocniejszą gwarancję niż implementacja.

**Poprawka:** po pełnej kontroli sekretów/local-only, a przed odrzuceniem obrazu walidować cały schemat multipart: wyłącznie rozpoznane części tekstowe z tekstem typu string i dokładnie zwalidowane obrazy; inne typy, skalarne elementy oraz błędne pola odrzucać. Nie osłabiać istniejącego walk/JSON budget ani kontroli metadanych. Dodać testy rzeczywistego agenta, że dowolny nieznany załącznik obok zdjęcia nie dociera do providera.

## Co przeszło

- Ponowiony zestaw źródłowy: **283 passed in 42.61s**, exit 0 (`review-original-tests.log`). Nie jest to samodzielny dowód PASS kontraktu.
- Testy rzeczywistej rozmowy obejmują Chat Completions, Responses, subskrypcję, pamięć lokalną i syntetyczny adapter Hindsight, obie wartości zgody w kolejnej turze, zachowanie oryginałów i analizy asystenta, brak automatycznego zapisu posiłku oraz blokadę nowego zdjęcia bez zgody.
- Host-ID: brak blokującego ustalenia. Stabilny nowy UUIDv4 URN; migracja tylko kanonicznego bare UUIDv4 w rekordzie z samym `host_id`, bez wpisu plikowego credentials. Metadane wiązania, obecność credentials i symlinki blokują migrację. `authorize` używa wspólnego inicjalizatora. Odpowiednie testy login/auth/protocol/host/API wykonano.
- Sprawdzone powiązane ścieżki: `agent`, `outbound_policy`, `k90_memory/privacy`, `memory_runtime`, `k90_memory/backend`, `k90_memory/worker`, `responses_api`, `subscription_api`, `subscription_auth`, `subscription_login`, `subscription_protocol`, `subscription_host`; zmienione testy i dokumentacja. Hindsight nadal nakłada niezależną bazową politykę bez obrazów.
- Brak zmiany głębokości historii, analizowania archiwum lub automatycznych zapisów posiłków w diffie źródeł.

## Dokładne wykonanie

Prefiks obu poleceń (uruchomione z `/opt/data/projects/k90-photo-history`; wymagane katalogi scratch utworzone):

```sh
env -i HOME=/opt/data/cache/scratch/k90-verification-20261025/reviewer-home DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/reviewer-data DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/reviewer-data/test.db K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/reviewer-auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PATH=/usr/local/bin:/usr/bin:/bin TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 /opt/data/projects/k90/.venv/bin/python -m pytest
```

Argumenty zestawu (stdout/stderr: TASK/`review-original-tests.log`, exit 0):

```text
-q tests/test_photo_history.py tests/test_agent.py tests/test_outbound_policy.py tests/test_privacy_composition.py tests/test_privacy_json_boundary.py tests/test_memory_privacy.py tests/test_memory_backend.py tests/test_memory_worker.py tests/test_app_memory.py tests/test_memory_acceptance.py tests/test_subscription_api.py tests/test_subscription_host_identity.py tests/test_subscription_login.py tests/test_subscription_auth.py tests/test_subscription_protocol.py tests/test_responses_api.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/reviewer-pytest
```

Argumenty niezależnych probes (stdout/stderr: TASK/`review-original-probes.log`, exit 1):

```text
-q -s /opt/data/jobs/k90-photo-history/review-original-probes.py --basetemp=/opt/data/cache/scratch/k90-verification-20261025/reviewer-probe-pytest
```

Wynik: **5 failed in 3.63s** — cztery brakujące oczekiwane `PrivacyError` oraz jedno potwierdzone przekroczenie granicy providera. Probe pozostawiono w TASK do powtórzenia po poprawce.

## Integralność, quota i ograniczenia

- Końcowy HEAD dokładnie `1b031e8653b43cdecde444d716fac5ec751385ae`; `git status --porcelain` pusty. `git diff --check` źródeł/testów/docs z wyłączeniem surowych logów RED/GREEN: exit 0. Dowód: `review-original-git.log`.
- Quota sprawdzona przed zestawem i probes: 84% sesja / 47% tydzień; końcowo 85% / 47% (`review-original-quota.json`). Nigdy nie osiągnięto progu 90%, bez resetu/fallbacku.
- Pełny regres i frontend równolegle weryfikuje koordynator; nie przypisuję sobie tych wyników.
- Brak dostępu do prywatnych plików, rzeczywistych credentials, produkcji i usług live. LiteLLM podczas importu próbował pobrać cost-map; istniejący guard offline zablokował próbę i użyto lokalnej kopii (`review-original-probes.log:1`).
- Live owner-topology OAuth/model/HS oraz deployment pozostają odroczone. Wyniki syntetyczne ich nie certyfikują.

Utworzone wyłącznie artefakty TASK: `review-original.json`, `review-original.md`, `review-original-tests.log`, `review-original-probes.py`, `review-original-probes.log`, `review-original-git.log`, `review-original-quota.json`. Fixtures wykonania znajdują się tylko w dozwolonym scratch. Repozytorium bez zmian.
