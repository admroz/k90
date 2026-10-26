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
