Real chat scroll regression (synthetic HTTP fixture, actual app HTML/CSS/JS).

Requires Node and Playwright **1.56.1**, Chromium **141.0.7390.37 / build 1194**.
Install in a disposable directory, outside application/runtime dependencies:

```sh
npm install --prefix "$SCRATCH" --ignore-scripts --save-exact playwright@1.56.1
PLAYWRIGHT_BROWSERS_PATH="$SCRATCH/browsers" "$SCRATCH/node_modules/.bin/playwright" install chromium
K90_PLAYWRIGHT="$SCRATCH/node_modules/playwright" \
  PLAYWRIGHT_BROWSERS_PATH="$SCRATCH/browsers" \
  K90_SCROLL_EVIDENCE="$SCRATCH/evidence" node tests/browser/chat-scroll.cjs
```

`K90_CHROMIUM` optionally selects that exact Chromium executable. The test starts
its own loopback server, mocks only HTTP responses with 150 synthetic messages,
and blocks page requests outside that origin. Browser layout is never mocked.
It fails if Enter paints a view away from the conversation end; it also checks
reading anchors across updates above the viewport, actual interval polling,
older-page prepending, reload, Shift+Enter/composition and image submission.
Bottom-follow transitions are sampled for 200 animation frames each. A 1px
reading-anchor tolerance accommodates browser scroll rounding.

JSON frame measurements and screenshots go to `K90_SCROLL_EVIDENCE` when set.
Exit failure is a test failure; missing browser/dependency is never a skip.
No application backend, model, authentication store or production data is used.

Selection regression

`chat_selection.cjs` serves the shipped frontend over loopback HTTP with synthetic
API responses and drives an existing Chromium installation using Playwright Core.
It does not install browsers or packages, use the application database, or call a model.

Set `PLAYWRIGHT_CORE` to the installed package's absolute path, `CHROMIUM_PATH`
to the existing browser executable, and `BROWSER_EVIDENCE` to an external evidence
directory. Run `node tests/browser/chat_selection.cjs` from the repository root
inside your normal offline test guard with a synthetic HOME and short scratch TMPDIR.
The harness blocks external page requests and limits browser DNS to loopback;
use the enclosing network guard for the Node process too.

The regression uses native mouse selection and normal application polling. It
asserts selected text and text-node identity across unchanged polls, append and
unrelated status/error updates, then checks active-gesture scrolling, idle bottom
follow, reading position, reload, history prepend and old-page status refresh.
Screenshots and observations are written outside the repository.

## Dashboard/catalog owner follow-up — real backend

`ui_polish.cjs` drives **genuine FastAPI + synthetic SQLite**, not mocked meal or
catalog responses. `ui_polish_fixture:app` supplies only fictional records and
an assertion-failing model processor. It refuses an existing database or a
nonempty data directory; use a fresh directory for every run. It freezes the
application calendar date at 2026-10-29 so previous-week calculations and dynamic
sleep dates remain deterministic. No production import/snapshot is needed.

Start the fixture with the existing repository Python environment, from the
repository root, inside the normal offline guard. Example environment (all paths
must point at fresh synthetic storage outside the repository):

```sh
env -i PATH="$PATH" HOME="$SYNTHETIC/home" TMPDIR="$SYNTHETIC/tmp" \
  PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$OFFLINE_GUARD_DIR:$PWD/tests/browser:$PWD" \
  DATA_DIR="$SYNTHETIC/data" DB_PATH="$SYNTHETIC/data/synthetic-ui.db" \
  K90_CHATGPT_STATE_DIR="$SYNTHETIC/auth" K90_UI_SYNTHETIC=true \
  WEB_PASSWORD=synthetic-browser-password WEB_COOKIE_SECURE=false \
  K90_PREVIEW=false K90_SYNC_ENABLED=false TELEGRAM_ENABLED=false \
  K90_MEMORY_BACKEND=local K90_AGENT_AUTH=api \
  "$PYTHON" -m uvicorn ui_polish_fixture:app --host 127.0.0.1 --port 18998
```

Create the four empty `home`, `tmp`, `data`, `auth` directories first. Keep the
server running only for acceptance, then stop and wait for that exact child.
The enclosing guard must deny external network and non-synthetic database/file
access for the server and inherited Python children. In a separately isolated
Node process, set `PLAYWRIGHT_CORE`, `CHROMIUM_PATH`, `BROWSER_EVIDENCE` and
optionally `K90_UI_ORIGIN` (default `http://127.0.0.1:18998`), then run:

```sh
node tests/browser/ui_polish.cjs
```

Use a Node network guard in addition to the client's loopback-only browser
routing/DNS flags. Browser tooling stays dev-only, outside runtime dependencies.
Author run: Playwright Core 1.64.1, Chromium 145.0.7632.6; 1280×900 desktop and
390×844 Chromium touch emulation. This is not physical-device or WebKit coverage.
Checks cover calendar energy/actual past days, stable meal ordering, real
edit/delete with cancel/confirm and readback, legacy unowned catalog preview,
version-bound edit/confirmation/portion, validation and concurrent stale errors,
input retention and close/Escape/focus return, real spaced sparse SVG points,
hover/focus/keyboard/touch value-date-unit, AI keyboard intent, owner-verified
weight/dynamic-sleep link targets, explicit missing-link indicators, viewport
overflow and uncaught JavaScript errors. External Garmin navigation and live
provider calls are deliberately not exercised.
