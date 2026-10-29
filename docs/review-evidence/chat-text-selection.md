# Chat text selection — author verification

Based on `511d2dd`, branch `fix/chat-text-selection-20261029`.
Real Chromium with the shipped frontend and synthetic HTTP fixtures reproduced
native mouse-selected text disappearing on the poll that appended an unrelated
message. The selected text node was replaced. Two unchanged polls retained it;
HTML normalization on unchanged polls was not established as a cause.

The change reconciles rows by message ID and compares cached renderer output.
Unchanged rows retain their native text nodes; changed rows alone are replaced.
Selection or an active pointer gesture suppresses programmatic scroll restoration.
Existing renderers, escaping, history refresh and API paths remain in use.

Author checks: original browser assertion RED, final browser GREEN for selection,
append, unrelated running/completed/failed updates, HTTP polling error, gesture
scrolling, idle bottom follow, reading position, reload/history and old-page refresh.
Node: 30 passed; application/module/browser-harness syntax and diff checks passed.
The reusable browser regression is documented in `tests/browser/README.md`.
Original failure output, screenshots, commands and final output are retained in
the task's private implementation phase; they are not public repository artifacts.

Desktop synthetic acceptance only; selected content that itself changes may lose
its obsolete range. Independent review and exact-SHA full CI/container checks
remain parent gates. No production access, PR creation, merge or deployment.
