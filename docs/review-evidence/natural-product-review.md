# Natural product review — author evidence, 2026-10-28

Feature branch `feat/natural-product-review-20261027`, base
`a4160f36524b502abcf003c4ca4ec7cb3b6a5183`. Independent of meal UI PR20.

Backend-generated, persisted previews bind owner, product, shown version and
review event. A small local Polish resolver handles consent, cancellation and
single-field corrections before sync/model. Corrections require a new preview
and separate consent, including “zmień białko na 12 i zatwierdź”. Multiple,
expired, interrupted, quoted, negated and conditional contexts cannot authorize
natural confirmation. Explicit show selects a draft; migration grants no owner
or consent to old records. Existing commands and panel use owner/version checks.

Confirmation, approval audit, pending consumption and request result commit in
one SQLite transaction. Replays preserve the outcome. Panel revision invalidates
chat review; cancellation retains its audit. A known committed local outcome is
available after response failure/restart. The model has no confirm/revise tool
and cannot supply owner, consent event or version authority. No provider, auth,
HS, image transport or outbound policy changes. `COPY tools/` ships the new module.

Author verification uses synthetic SQLite/data/auth and a loopback-only network
guard, with separate quota watchdogs. The immutable baseline RED reaches sync/model
for plain “zatwierdzam”. The first attempted RED had a copied harness path error;
it is not behavioral evidence. Catalog iteration: 47 PASS. One full boundary:
745 PASS, 1 existing skip, 2 failures (CLI command invalidation order and restart
test reading stdout redirected by its watchdog). Both were corrected; focused
agent/catalog/runtime/backup/privacy regression: 144 PASS. Node25 and JS syntax
PASS. Final CLI/topic and product-review regression: 24 PASS.
No second full-suite PASS is claimed. No UI source changed; no new browser campaign.
Private logs retain exact commands, outcomes and failed harness attempts.

Fresh independent verification and exact final SHA fork CI/image/PR are coordinator
gates. No author selfapproval, production access, publication or deployment.
Real label vision, OAuth/provider inference and Telegram transport delivery are
unperformed owner checks; synthetic providers do not establish their behavior.
Backup/restore, legacy migration and rollback guidance: [catalog documentation](../PRODUCT_CATALOG.md#migracja-przeglądu-produktu).

## Bounded CI fixture correction — 2026-10-28

Fork CI run40704172109/job122871686520 on `56af79d` failed with
749 PASS/1 skip/1 failure; image execution was skipped. The CLI slash-command
test mocked startup initialization without providing its review-state database.
An absent synthetic database parent reproduced the same SQLite open failure.
The test now explicitly requests `temp_db`; production topic invalidation and
all bypass assertions remain unchanged. Focused CLI/product-review replay:
24 PASS under the same absent-default-path harness. No local full-suite rerun
or new final CI/image success is claimed; narrow independent review and new
exact-SHA CI remain coordinator gates.
