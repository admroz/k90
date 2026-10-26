# Chat scroll correction — author verification, 2026-10-26

Branch `fix/chat-scroll-anchor`, baseline
`69fb62661e8d26f0e771757d52c49f5de8ab4d87` (PR15).
Application source in `63f3f6e19d2778783dbc7757cb06b0cd49b31625`;
subsequent changes only extend browser evidence collection and documentation.
Independent review, final PR and actual image CI remain coordinator gates.

## Real browser RED before application edits

Playwright1.56.1 / Chromium141.0.7390.37 (build1194), actual shipped
HTML/CSS/modules, loopback synthetic HTTP fixture with150 messages. No browser
geometry mocks. The regression was committed while application source was
unchanged (`5a55a89`). It failed on Enter before any fix.

At1280x900, original list: scrollTop9899px, scrollHeight10367px, viewport468px.
After the POST/queued response and history expansion, the DOM mutation left
scrollTop9899px while scrollHeight became20495px. The view was10128px away from
the end before smooth recovery to scrollTop20027px. Thus the observed defect is
visible old-history exposure and animated recovery; the measurement does not
claim scrollTop literally reached zero. A screenshot captured during the faulty
recovery shows synthetic messages101/102 instead of the newest messages.
The final instrumented regression was also replayed against an archived original
`web/` fixture and failed with the same10128px gap.

## Correction

`loadChat` restores replacement scroll instantly in the same layout turn. When
reading history, it restores the visible message's viewport offset using its
escaped stable `data-message-id`. Prepending still prioritizes the reading
anchor, and normal refresh follows the bottom when already there. Existing CSS
smooth scrolling remains. No delays, retry, pagination/API or submission changes.

## Verification

Actual browser command (scratch paths specific to this execution):

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin \
 HOME=/opt/data/cache/scratch/k90-scroll/home \
 TMPDIR=/opt/data/cache/scratch/k90-scroll/tmp \
 K90_CHROMIUM=/opt/data/cache/scratch/k90-scroll/browsers/chromium-1194/chrome-linux/chrome \
 K90_PLAYWRIGHT=/opt/data/cache/scratch/k90-scroll/node_modules/playwright \
 K90_SCROLL_EVIDENCE=/opt/data/jobs/k90-scroll/evidence/green-final \
 node tests/browser/chat-scroll.cjs
```

Exit0, desktop1280x900 and narrow390x844:

- Enter100 animation frames: maximum distance from bottom0px on both viewports.
- Real interval polling through running/completed:200 frames per state and
  viewport, maximum distance0px, including a long final answer.
- Reading position preserved across updates above the viewport, queued/running/
  answer replacements, older-page prepending and repeated unchanged polling.
  Identity plus viewport position checked with1px browser rounding tolerance.
- Loaded pages retained, unique DOM message IDs, no automatic retries on polling
  or reload. Two intentional requests have distinct IDs. Enter sends once,
  Shift+Enter and composing Enter do not submit; image submission is preserved.

`node --check web/app.js` PASS; `node --test tests/web_*.test.mjs`:23 PASS.
Adapted offline audit guard, app interpreter and env-i scratch paths:
`python -m pytest -q tests/test_web.py tests/test_web_runtime.py`:58 PASS43.81s;
`python -m pytest -q`:594 PASS,1 existing optional-import skip143.06s.
The full suite retains sync mocks and privacy/photo/subscription/HS regressions.
No backend, auth, HS, workflow, runtime dependency or production changes.

Raw bounded JSON, screenshots (including visible failing recovery), commands,
logs and checkpoints are outside Git at `/opt/data/jobs/k90-scroll/`.
Pinned browser install is scratch-only. Node26 Playwright archive extraction
stalled; the same downloaded archive was extracted with Python zipfile and the
exact Chromium executable selected explicitly. Browser executable SHA256:
`85918a9937192b78da8edb51c38a7af4920ac6bd9ba19939ecb0bb724d5a1a95`.

These are author tests on synthetic fixtures in Chromium, including a narrow
viewport, not a claim about the deployed image or other browser engines.
Quota15:44:09Z: Session14%, Weekly16%; permanent stop >=80% any/unknown.
