# Product catalog — author verification, 2026-10-26

Tested source: `89467c68238a16e9ba5a0a3df01f9e3db7a012e0` on
`feat/local-food-catalog`, base `69fb62661e8d26f0e771757d52c49f5de8ab4d87`.
Later evidence/status-only commits do not change this tested source.
Implementation is ready for coordinator review, not PR/deployment acceptance.

- Full Python regression: **643 passed, 1 existing optional-import skip**,192.97s.
  Command: isolated `python -m pytest -q`, using `/opt/data/projects/k90/.venv/bin/python`.
- `node --check web/app.js`, `node --check web/catalog.mjs`: PASS.
  `node --test tests/web_*.test.mjs`: **25 passed**,302.93ms.
- Real headless Chromium on fresh loopback synthetic app: authenticated create→
  review→confirm→portion96kcal→reload PASS; malicious product name rendered as
  inert text. Final run used env-i and a fresh synthetic HOME/SQLite/auth/TMPDIR;
  browser routes block non-loopback. An initial attempt before readiness was
  connection-refused and was repeated successfully after startup.
- Offline backup/restore probe: SQLite API backup restored into a separate file;
  original synthetic weight, product/version, original label image, ml portion
  snapshot, idempotency and repeated initialization preserved; integrity_check ok.
- Synthetic provider E2E exercises real HTTP queue/default process_message→
  agent tool→draft→exact owner command→later local lookup→one96kcal meal.
  Explicit local vision permission; no actual provider/OAuth/live vision request.
  Existing meal-photo→text/history/policy regressions remain in the full suite.
- Exact new embedded image helper executed twice on HOST, then included in full
  regression: real SQLite/local lookup/approval/portion/backup. Docker packaging
  uses existing COPY tools/ and web/. Actual built-image execution remains pending
  fork Actions; no daemon/socket was used and no image was published.

Vertical RED/GREEN slices covered draft persistence/validation, stale versions,
barcode check digits and leading-zero-preserving format, decimal comma/null/zero,
unit mismatch, deterministic portions/snapshots, API auth/CSRF, chat photo evidence,
OFF parsing/local priority/cache, Unicode local search, concurrent response snapshot,
malformed structures and review corrections. Private task logs preserve each RED
and subsequent GREEN; all source changes followed observed appropriate failures.
New frontend behavior first failed in real browser before implementation.

Independent advisory source reviewer was read-only and executed no tests. Findings
were reproduced and corrected: slow OFF streaming/compression, country tag type,
model-selected duplicate keys and mixed freeform/catalog tools, ID type aliases,
text-only event promoted to own-label, approval dispatch before sync, and CSP sizing.
Final coordinator review remains a separate gate; no advisory final PASS is claimed.

Public bounded OFF GETs before and after adapter:5900531004544 has Polish market,
Skyr Naturalny/Piatnica,100g64/12/4.1/0; final adapter returns **unverified**.
5901062003082 is rejected for ambiguous liquid units. Only public barcodes/field
parameters were sent; no owner data/photos, credentials or uploads. Public responses
are private task evidence, not guarantees of accuracy or Polish-market coverage.
See [workflow, provenance, limits and rollout](../PRODUCT_CATALOG.md).

Source commits5cb6433,86601c7,89467c6 were pushed only to explicit origin feature
ref and remote SHAs read back. No main/upstream writes, PR, merge or deployment.
Final quota17:21:02Z: session77%, weekly26%; no new coding/tests started afterwards.

Remaining gates: coordinator independent final review; actual fork Actions image
build/network-none smoke on tested source; parent final PR decision. Owner live
vision/rollout check is documented and separate from synthetic acceptance.

## Końcowy review i powtórzenie koordynatora — 2026-10-26

Testowane i niezależnie ocenione źródło:
`2df48534b97f8d74d6aefb6ed8684b4ccad51292`, ta sama baza `69fb626`.
Późniejsze zmiany wyłącznie w docs nie są nowym review kodu.

Pierwszy pełny niezależny reviewer wykonał rzeczywiste testy i wydał FAIL:
OFF przyjmował10000kcal/100g i zapisywał je do cache. Koordynator niezależnie
odtworzył oba błędy (2FAIL/12PASS). Osobny kontekst naprawczy dodał regresje
kcal/kJ/parser/cache:4RED, następnie33GREEN, minimalny limit1000 po konwersji.
Oryginalne probe'y nie zostały zmienione ani osłabione.

Świeży niezależny reviewer całego połączonego zakresu22 plików wydał PASS,
bez otwartych ustaleń:31 rzeczywistych probe'ów transportu/cache/granic
(14oryginalnych+17nowych),67testów katalogu,283testy agenta/web/prywatności,
25frontend, Chromium, HTTP i backup/restore. Końcowe SHA, inventory/hashes oraz
pięć oryginalnych harnessów sprawdzone bez zmian. Przegląd objął też prompt
nadpisywany przez właściciela, licencję/proweniencję, historyczne obrazy i5MB.

Koordynator uruchomił na tym źródle:

- pełne izolowane `python -m pytest -q`:661PASS/1istniejący skip,196.46s;
- `node --check web/app.js`, `node --check web/catalog.mjs`:PASS;
  `node --test tests/web_*.test.mjs`:25PASS;
- niezmienione31probe'ów niezależnych reviewerów:PASS;
- niezmieniony rzeczywisty HTTP probe:7tras bez autoryzacji, CSRF, ignorowanie
  modelowego confirmed, stare zatwierdzenie, g/ml, idempotencja i snapshot:PASS;
- świeży Chromium:formularz→kontrola→zatwierdzenie→96kcal→reload/XSS:PASS;
- oddzielny SQLite API backup/restore oryginalnego zdjęcia/katalogu/wersji/
  porcji ml/idempotencji i integralności:PASS.

Wszystkie testy aplikacyjne były syntetyczne, z osobnym HOME/DB/DATA/auth,
wyłączonym dotenv i blokadą sieci poza loopback. Zachowano błędy pierwszego
harnessu (.env fixture poza SAFE i błędny prywatny health URL); poprawiono
wyłącznie harness i powtórzono testy, nie kod ani oczekiwania aplikacji.

Rzeczywiste publiczne GET adaptera:trzy rekordy Piątnicy
5900531004544/5900531000102/5900531000010, Poland,100g,unverified.
Zweryfikowano oficjalny indeks/specyfikację v3/licencję. Brak deklaracji
reprezentatywności rynku lub poprawności etykiet. Publiczny search503 zachowany;
indywidualne GET zakończone powodzeniem. Bez owner-data/model/OAuth/upload.

Wcześniejszy fork Actions [40393559615](https://github.com/hermesinski/k90/actions/runs/40393559615)
przeszedł testy i rzeczywisty build/network-none smoke na `f9af4df`; publikacja
pominięta. Nie certyfikuje to późniejszego HEAD. Końcowy PR wolno utworzyć dopiero
po zielonym dispatch dla dokładnego końcowego HEAD; link/readback w opisie PR.
Nowe CI upstream PR może wymagać zgody właściciela i nie jest wcześniejszym runem.
Nie wykonano merge, publikacji, wdrożenia ani odczytu produkcji. Live vision i
rollout pozostają jawnym, odrębnym sprawdzeniem właściciela z PRODUCT_CATALOG.md.
