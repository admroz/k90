# Projekcja historii zdjęć — partia implementatora

Gałąź `fix/meal-photo-history`, baza `9e02ab0bcffb24da17faecb2199c66fc587c7696`.
Poprawka host ID pozostaje w przodku; brak zmian jej źródeł. SHA tej partii
jest podany w końcowym raporcie CLI i historii Git. To dowody implementatora,
nie niezależny review ani końcowy odbiór.

`agent.load_history` projektuje rozpoznane części `image_url` przed końcowym
filtrem bez obrazów. Pierwszy pełny, ograniczony walk oryginału nadal sprawdza
sekrety, local-only, metadane, klucze i wielokrotnie kodowany JSON. Nieznane
pola części obrazu, nieprawidłowe koperty URL/base64, duplikaty i nieznane
załączniki są odrzucane. Projekcja nie zapisuje zmian w bazie. Tekst i wcześniejsza
analiza pozostają; obraz zastępuje `[Historical image omitted]`. Zgoda na nowe
zdjęcia nie pozwala na historyczny replay ani obrazy w HS. Głębokość historii,
narzędzia posiłków i liczba wywołań modelu nie są zmieniane.

Zmieniono dawny test `test_images_and_existing_history_work_with_prefixed_model`:
jego oczekiwanie ponownego wysłania starego obrazu celowo zastępuje oczekiwanie
znacznika. Zachowano sprawdzenie wysłania nowego obrazu i dodano sprawdzenie
obu niezmienionych oryginałów SQL. Innych istniejących zabezpieczeń nie usuwano.

## Rzeczywiste RED → GREEN

Wszystkie testy używały poniższego dokładnego prefiksu i suffixu; między nimi
podano argumenty z tabeli. Przekierowanie `> docs/review-evidence/<log> 2>&1`.

```sh
env -i HOME=/opt/data/cache/scratch/k90-verification-20261025/photo-home DB_PATH=/opt/data/cache/scratch/k90-verification-20261025/photo-data/test.db DATA_DIR=/opt/data/cache/scratch/k90-verification-20261025/photo-data K90_CHATGPT_STATE_DIR=/opt/data/cache/scratch/k90-verification-20261025/photo-auth PYTHON_DOTENV_DISABLED=1 PYTHONPATH=/opt/data/cache/scratch/k90-verification-20261025:. PATH=/usr/local/bin:/usr/bin:/bin TMPDIR=/opt/data/cache/scratch/k90-verification-20261025 /opt/data/projects/k90/.venv/bin/python -m pytest -q
# ARGUMENTY
--basetemp=/opt/data/cache/scratch/k90-verification-20261025/photo-pytest
```

| Argumenty | Log (w tym katalogu) | Wynik |
| --- | --- | --- |
| `tests/test_photo_history.py` (pierwsze 17 przypadków, stary agent) | `photo-history-red-projection.log` | 7 failed, 10 passed |
| `tests/test_photo_history.py tests/test_agent.py` | `photo-history-green-projection.log` | 21 passed |
| `tests/test_photo_history.py -k real_agent` (stary agent) | `photo-history-red-conversation.log` | 8 failed, 19 deselected |
| `tests/test_photo_history.py` (27 przypadków) | `photo-history-green-conversation.log` | 27 passed |
| `tests/test_photo_history.py -k ambiguous` | `photo-history-red-malformed.log` | 2 failed, 6 passed, 21 deselected |
| poniższy zestaw przed aktualizacją starego kontraktu Responses | `photo-history-red-existing-contract.log` | 1 failed, 256 passed |
| poniższy zestaw końcowy | `photo-history-green-targeted.log` | 262 passed, 41.55s, pytest exit 0 |

RED rozmowy wykonano z dokładnym bazowym `agent.py`: `cp agent.py /opt/data/cache/scratch/k90-verification-20261025/photo-agent-projected.py`,
`git show HEAD:agent.py > agent.py`, test, potem
`cp /opt/data/cache/scratch/k90-verification-20261025/photo-agent-projected.py agent.py`.
Nie zmieniano filtra prywatności ani oryginalnych danych dla uzyskania RED.

Dokładne argumenty końcowej grupy:

```text
tests/test_photo_history.py tests/test_agent.py tests/test_outbound_policy.py tests/test_privacy_composition.py tests/test_privacy_json_boundary.py tests/test_memory_privacy.py tests/test_memory_backend.py tests/test_memory_worker.py tests/test_app_memory.py tests/test_memory_acceptance.py tests/test_subscription_api.py tests/test_subscription_host_identity.py tests/test_responses_api.py
```

Nowe testy wykonują rzeczywiste `agent.run_agent`, zapis historii/zdarzeń,
Chat Completions, Responses i SubscriptionConversation, recall lokalny oraz
`HindsightBackend` przez syntetyczny transport podłączony do `memory_runtime`.
Sprawdzają retain/recall, brak obrazu w HS i drugiej turze przy obu wartościach
flagi, zachowanie oryginałów, brak automatycznego posiłku i blokadę nowego
uploadu bez zgody przed providerem/token refresh. Wszystkie dane są fikcyjne;
żadnego live OAuth, modelu, banku ani produkcji.

## Inwentarz i dalsze bramki

Przed commitem: `git status --short`, `git diff --check`, `git diff --numstat`,
przegląd diffów źródeł i wyszukanie wzorców sekretów w nowych testach/logach.
Znalezione wartości `Bearer synthetic`, `password: synthetic` i token `synthetic`
są jawnymi fixture testowymi. Brak prywatnych plików i poświadczeń w zmianach.
Nie odczytywano `.env` ani prywatnych store. Guard offline pozostał aktywny.
Surowe logi pytest zachowują oryginalne końcowe spacje tracebacków; kontrola
`git diff --cached --check -- . ':!docs/review-evidence/photo-history-*.log'`
sprawdza źródła, testy i dokumenty bez przepisywania dowodów.

Quota `/opt/hermes/.venv/bin/hermes usage --json`: początek 74% session / 46%
weekly; przed końcową grupą 80% / 47% (ostrzeżenie, poniżej progu zatrzymania).
Końcowy odczyt 23:13:56Z: 81% session / 47% weekly. Bez resetów i płatnego fallbacku.

Pozostaje koordynatorowi niezależny review niezmiennego commitu (także host ID),
własna akceptacja/regresja, pełny Python/frontend, CI i PR. Live smoke modelu,
OAuth, topologii i autoryzacji HS oraz wdrożenie pozostają osobnymi bramkami
właściciela. Implementator nie wykonuje push, PR ani zmian kontrolera/outcome.
