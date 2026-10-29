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
