# Owner decisions — personal self-hosted acceptance (2026-10-25)

This document supersedes earlier owner prerequisites that required live provider
OAuth and local Docker access before a final delivery. It does NOT authorize
production access, deployments, main/upstream writes, secrets, extra costs,
removing privacy checks, or calling synthetic tests full live integration.

## Later owner clarification — reduce Hindsight testing

The owner explicitly drops extensive HS infrastructure testing as a delivery
blocker and accepts checking real HS operation at deployment. Do not spend time
building a large HS CI/model-fixture test system or IAM infrastructure. Keep
existing useful adapter/error/fallback/privacy tests, document a short synthetic
retain/recall deployment smoke check, and preserve honest unverified status.
The ordinary k90 CI/container smoke remains useful. HS topology is currently a
proposal, NOT deployment authorization: k90 remains a separate application;
shared existing HS vs a dedicated instance is under owner discussion. Do not
move existing HS data, change its credentials/configuration, restart it, add k90
to Hermes stack, or provision a new production HS autonomously.

These later instructions override the extensive HS test requirements below.

## Test infrastructure

- Do not request or obtain Docker daemon/socket privileges on the Hermes host.
- Use standard GitHub-hosted Linux Actions runners in the public fork for
  test-only Docker builds/smoke and an isolated Hindsight service. Never publish
  a Docker image or deploy from the feature workflow.
- Diagnose and fix accessible Actions registration/execution yourself; do not
  ask the owner to diagnose generic empty workflows without a concrete action.
  Main stays untouched. If GitHub requires enabling Actions in a browser, report
  that precise owner action and verified cause.
- Pull a pinned official HS image, ephemeral synthetic banks/data and persistent
  test storage only for the restart test. Bounded runtime, small datasets, clear
  logs and cleanup. No connection to shared HS, production databases or secrets.
- HS infrastructure does not supply free model inference. Do not put owner or
  Hermes OAuth/keys into GitHub or add paid API calls. Prefer deterministic
  local protocol fixtures for the model/embedding boundaries where supported;
  real HS/database/restart tests must actually run. Distinguish real service
  integration against deterministic model fixtures from real model quality.
  If a lightweight real local model is viable within free runner resources,
  assess cost/time first; do not build an unlimited slow LLM-testing loop.
- Investigate actual supported HS auth/ACL in the selected version. Test claimed
  controls; unsupported bank-level ACL is a documented trusted-network deployment
  limitation, not a reason to invent credentials or build an unrelated IAM product.

## Subscription adapter and OAuth usability

- Run everything meaningful without a real account: fake provider HTTP protocol,
  OAuth state/PKCE/callback errors, token persistence/restarts/refresh races,
  tools/images/streaming errors, limits and no-paid-fallback behavior.
- The owner explicitly defers real account login and provider live inference to
  deployment acceptance. Do not keep BLOCKED_OWNER solely for missing live OAuth.
- Provide a friendly, documented operator flow. CLI with one or two operator
  commands is acceptable; a frontend OAuth flow is optional, not required scope.
- Inspect the actual callback/browser/container topology. A localhost callback
  inside a headless container does not automatically reach a browser on a Mac.
  Prefer supported safe device flow or documented local-browser login/SSH transfer
  if needed; don't invent provider endpoints or require tokens pasted in chat.
  Persist k90-only private auth state in /data, survive recreate, status/logout,
  no borrowing Hermes credentials, no tokens in URLs/logs/Git/public CI.

## Compose simplification

- Use service `env_file: .env` for application configuration/secrets; do not bake
  .env into an image or public repo. Keep synthetic .env.example only. Ensure
  .dockerignore and .gitignore exclude real .env and credential files.
- Keep only necessary explicit runtime overrides (DATA_DIR=/data, DB_PATH=/data/k90.db,
  timezone alias if needed and explicit required-password validation). Defaults
  must remain compatible/documented; add a default env file if needed, no silent
  environment-variable override that negates values supplied in env_file.
- Preserve the /data bind and operator-controlled image/network behavior. Owner
  pasted an accidental `${DATA_PATH:-./data}:/data` item under environment; it
  belongs only under volumes, not environment.
- User prefers configuration in one .env file, not copying every variable into
  compose environment. Adding an app config key should not require editing YAML.
- Validate Compose with synthetic env only; compose config must not leak real
  values in logs. Docker Compose config validation does not require a daemon.

## Definition of final delivery

Personal self-hosted application, not a packaged commercial product. Prefer
bounded useful tests and clear rollback/operator instructions over impossible
proof of every provider scenario. Keep independent review for changed security-
sensitive code; repeat full regression and actual CI/container/HS tests when
accessible. Frequent checkpoint commits/push after safe review.

Ready for owner review can explicitly carry deferred live subscription and owner-
network-specific checks. In acceptance manifests use `deferred_live_checks` and
`full_live_acceptance: false` for these owner-accepted deferrals; do not list them
as blocking `remaining_gates`. PASS means the revised personal-use preparation
scope passed, NOT complete production integration. Document exact executed and
unexecuted checks and real model vs fixture boundaries. Any unexecuted CI/HS job
must remain reported honestly, never fabricated or labeled as executed.

Final PR only at the end once revised preparation is ready; no merge or deploy.
