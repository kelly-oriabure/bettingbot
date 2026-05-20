# FirmBetting MVP PRD and Implementation Plan

## 1. Product Requirements Document

### Product Overview

FirmBetting is a Telegram-first football prediction platform. The MVP serves about 100 test users through a Telegram channel where the bot posts one daily prediction broadcast and a later result-comparison broadcast. Users do not trigger API-backed prediction commands during the MVP.

The long-term business goal is to convert users into paid subscribers, but only after the product can show credible, market-specific performance over a meaningful sample size.

### Target Users

- Football fans who want daily match predictions in a simple Telegram channel.
- Early testers who will evaluate prediction quality, consistency, transparency, and trustworthiness.
- Future paid subscribers who need reliable, tracked predictions before subscribing.

### MVP Goals

- Generate daily predictions for available football matches.
- Publish predictions to a Telegram channel once per day.
- Fetch final match results and compare predictions against actual outcomes.
- Track accuracy by market type, confidence level, sample size, and settlement status.
- Build a data foundation that supports historical training, backtesting, and future paid subscriptions.

### Product Principles

- Never generate random or fake predictions.
- Every prediction must be traceable to a fixture, model version, odds snapshot, market type, and settlement rule.
- Accuracy must be reported by market type and sample size.
- Void and cancelled predictions must be excluded from accuracy calculations.
- Do not claim 70% accuracy globally unless backed by sufficient samples and clear market definitions.
- Betting outputs are high-risk user-facing content and must be conservative, auditable, and transparent.

### MVP Scope

- Daily scheduled fixture ingestion from API-Football.
- Daily odds ingestion from The Odds API.
- Historical training/backtesting pipeline.
- Core market predictions:
  - 1X2
  - Double chance
  - Over/under 1.5
  - Over/under 2.5
  - BTTS
- Telegram channel prediction broadcast.
- Telegram channel result-comparison broadcast.
- Settlement and accuracy tracking.
- Admin-only configuration through environment variables or config files.

### Out of Scope for MVP

- User-triggered API-backed commands.
- In-play betting.
- Player prop markets.
- Cards, corners, interval markets, and advanced rulebook markets.
- Betfair, Pinnacle, international sharp books, or Sportradar integration.
- Paid subscription enforcement inside Telegram.
- Personalized predictions per user.

### Data Sources

- API-Football: fixtures, teams, standings, match status, final results, historical match results.
- The Odds API: daily odds, odds snapshots, and historical odds where plan limits permit.
- `info.txt`: football market settlement semantics and future rulebook expansion.

### Data Model Requirements

The implementation should persist the following concepts:

- Teams: provider IDs, normalized names, league metadata.
- Fixtures: provider fixture ID, teams, league, kickoff time, status, raw provider payload.
- Odds snapshots: fixture, bookmaker/source, market type, selections, prices, implied probabilities, captured timestamp.
- Predictions: fixture, market type, selection, probability, confidence, model version, odds snapshot reference, created timestamp.
- Results: fixture, final home goals, final away goals, status, completion timestamp, raw provider payload.
- Settlements: prediction, settlement status, settled outcome, settled timestamp, reason.
- Accuracy reports: date range, market type, confidence bucket, won/lost/void counts, hit rate.
- Model versions: model type, trained data window, metrics, artifact path, created timestamp.

Required settlement statuses:

- `pending`
- `won`
- `lost`
- `void`
- `cancelled`

Required MVP market types:

- `1x2`
- `double_chance`
- `over_under_1_5`
- `over_under_2_5`
- `btts`

### Settlement Rules

Settlement rules are based on `info.txt`.

- Core football result markets settle on regular 90 minutes plus stoppage time.
- Extra time and penalty shootouts do not affect MVP market settlement.
- If a match is interrupted and continued within 48 hours after initial kickoff, settle with the final result.
- If a match is interrupted or postponed and not completed within 48 hours after initial kickoff, mark undecided predictions as `void`.
- If the fixture team names, category, or score source is invalid, mark affected predictions as `cancelled` or `void` with a reason.
- Advanced player, card, corner, and interval rules remain documented for later phases and must not be implemented in the MVP unless explicitly requested.

### Success Metrics

- Daily prediction broadcast succeeds without manual intervention.
- Result-comparison broadcast succeeds after matches complete.
- 100% of predictions have fixture, model version, market type, and settlement traceability.
- Accuracy reports exclude `void` and `cancelled` predictions.
- No random prediction fallback exists in production paths.
- API jobs are idempotent and tolerate provider failures.

## 2. Phased Implementation Roadmap

### Phase 0: Stabilization, 2-3 Days

Goal: remove critical production risks and make the current codebase reliable enough to build on.

Tasks:

- Remove hard-coded API keys.
- Document required environment variables.
- Fix training data access.
- Fix timezone-aware fixture filtering.
- Remove random prediction fallback.
- Add baseline tests for current critical behavior.

Deliverable: the bot fails safely when data/model requirements are missing and can train/fetch through the intended paths.

### Phase 1: Persistent Data Foundation, 4-6 Days

Goal: store fixtures, odds, predictions, results, settlements, and model metadata.

Tasks:

- Add a SQLite persistence layer with a clear migration path to Postgres.
- Add tables/models for MVP entities.
- Add idempotent upsert behavior for fixtures and odds.
- Store raw provider payloads for audit/debugging.

Deliverable: daily jobs can persist data once and broadcasts can read from storage instead of making user-facing API calls.

### Phase 2: Historical Training and Backtesting, 5-7 Days

Goal: train and evaluate models from historical data before public accuracy claims.

Tasks:

- Ingest historical fixtures/results.
- Ingest historical odds where plan limits permit.
- Train Dixon-Coles model and optional XGBoost/ensemble model.
- Store model versions and backtest metrics.
- Split training/test data correctly to avoid leakage.

Deliverable: model artifacts and backtest reports are reproducible and tied to model versions.

### Phase 3: Telegram Broadcasts, 4-5 Days

Goal: automate prediction and result-comparison broadcasts.

Tasks:

- Generate daily predictions from stored fixtures/odds.
- Format prediction broadcast from stored predictions.
- Fetch final results and settle predictions.
- Format result-comparison broadcast from settlements.

Deliverable: Telegram channel receives a daily prediction post and a later transparent results post.

### Phase 4: Accuracy Reporting, 3-5 Days

Goal: make performance transparent and market-specific.

Tasks:

- Compute accuracy by market, confidence bucket, and date range.
- Exclude void/cancelled predictions.
- Add public Telegram accuracy summary.
- Add admin/reporting command or script.

Deliverable: users can see credible performance metrics without inflated global claims.

### Phase 5: Production Hardening, 5-7 Days

Goal: prepare the MVP for reliable daily operation.

Tasks:

- Add retry/backoff and quota-aware provider handling.
- Add structured logging and health checks.
- Add deployment checklist.
- Add admin runbook.
- Add monitoring guidance and failure recovery procedures.

Deliverable: operators can deploy, monitor, and recover the Telegram MVP.

### Roadmap Phase

Goal: expand beyond MVP once the Telegram channel proves demand and credible performance.

Future work:

- Betfair Exchange API for sharp-market reference.
- Pinnacle or international-book odds benchmarking.
- Sportradar migration for enterprise-grade fixture/result coverage.
- Paid subscription gating.
- Advanced markets from `info.txt`: corners, cards, player props, goalscorers, interval markets.
- Web dashboard for admins and subscribers.

## 3. Task Breakdown, AI Prompts, and Test Cases

### Task 1: Remove Hard-Coded API Keys and Document Environment Variables

Purpose:
Remove credential leakage risk and make provider configuration explicit.

Implementation Notes:
Remove literal fallback keys from the odds provider. Add `.env.example` or README documentation for required variables without real secrets.

Files Likely Touched:
`app/data/fetcher.py`, `README.md`, optional `.env.example`.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Implement removal of hard-coded API credentials and document required environment variables.
Requirements:
- Remove all literal API keys, Telegram tokens, and provider secrets from source code.
- The Odds API provider must use only `ODDS_API_KEY` and optional comma-separated `ODDS_API_BACKUP_KEYS`.
- If no odds API key is configured, provider calls must fail safely with a clear log message and no network request.
- Document `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL`, `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `ODDS_API_BACKUP_KEYS`, `ODDS_PROVIDER`, and database path configuration.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- No provider secrets remain in tracked source files and missing keys are handled explicitly.
"""

Test Cases:
- Search source for old literal keys and confirm none remain.
- Instantiate Odds API provider without keys and verify it reports unavailable rather than using fallback keys.
- Instantiate with `ODDS_API_KEY` and verify exactly one configured key is present.
- Instantiate with backup keys and verify key rotation uses only environment-provided keys.

Acceptance Criteria:
- No hard-coded provider secrets exist in source.
- Missing credentials do not trigger API calls.
- Required environment variables are documented.

### Task 2: Fix Training Data Access

Purpose:
Make `python -m app.train` capable of fetching historical API-Football data through the intended data manager path.

Implementation Notes:
Either add `DataManager.get_training_data()` as a delegating method or update `app/train.py` to call `dm.api_football.get_training_data(...)`.

Files Likely Touched:
`app/data/fetcher.py`, `app/train.py`, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Implement the training data access fix.
Requirements:
- Ensure `python -m app.train` can call the historical data fetch path without `AttributeError`.
- Preserve API-Football as the historical training data source.
- Add a test that verifies the training fetch function calls the API-Football client path.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Training script reaches historical data retrieval through a valid method.
"""

Test Cases:
- Mock API-Football historical data client and assert `fetch_data()` returns the mocked DataFrame.
- Verify empty historical data still exits/fails with a clear message.
- Verify `DataManager` exposes the selected training data access method if delegation is chosen.

Acceptance Criteria:
- `fetch_data()` no longer references a missing method.
- Training data retrieval is covered by tests.

### Task 3: Fix Timezone-Aware Fixture Filtering

Purpose:
Prevent valid fixtures from being dropped because offset-aware provider dates are compared with naive UTC datetimes.

Implementation Notes:
Use timezone-aware UTC datetimes consistently. Normalize parsed fixture times to UTC.

Files Likely Touched:
`app/data/fetcher.py`, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Implement timezone-safe fixture filtering.
Requirements:
- Use timezone-aware UTC values for `now`, parsed fixture times, and window end times.
- Support fixture dates ending in `Z`, explicit offsets like `+01:00`, and naive ISO strings by treating naive strings as UTC.
- Apply the fix to today and upcoming fixture filtering.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Date filtering works for UTC-aware, offset-aware, and naive fixture timestamps.
"""

Test Cases:
- Fixture at `2026-05-20T12:00:00Z` inside window is included.
- Fixture at `2026-05-20T13:00:00+01:00` inside equivalent UTC window is included.
- Fixture outside the requested window is excluded.
- Naive ISO fixture timestamp is treated as UTC.
- No `TypeError` is raised for aware/naive comparisons.

Acceptance Criteria:
- Today/upcoming filtering is deterministic and timezone-safe.

### Task 4: Remove Random Prediction Fallback

Purpose:
Ensure missing models, unknown teams, or prediction errors never produce fabricated betting advice.

Implementation Notes:
Replace random fallback with explicit unavailable result handling. Update bot messages accordingly.

Files Likely Touched:
`app/bot/bot.py`, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Remove random prediction fallback behavior.
Requirements:
- `_run_prediction()` must never import `random` or synthesize probabilities.
- If the model file is missing, return `None` or a typed unavailable result.
- If teams are unknown, return unavailable and explain the reason in logs.
- User-facing handlers must show a clear unavailable message instead of fake predictions.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- The bot only sends predictions generated by a real model.
"""

Test Cases:
- Missing model file returns unavailable.
- Unknown team returns unavailable.
- Model exception returns unavailable and logs error/debug context.
- Source no longer imports or calls `random` in prediction path.

Acceptance Criteria:
- No fabricated probabilities can be returned from `_run_prediction()`.

### Task 5: Add Persistent Storage Layer

Purpose:
Move the MVP from in-memory/transient behavior to a database-backed workflow.

Implementation Notes:
Use SQLite for MVP, configured by environment variable, and keep SQL/schema choices compatible with a future Postgres migration.

Files Likely Touched:
New storage module, tests, requirements if needed.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add a persistent storage layer for the MVP.
Requirements:
- Use SQLite by default with a configurable database path.
- Provide connection/session helpers.
- Provide initialization/migration logic for MVP tables.
- Keep provider payload fields storable as JSON text.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- The app can initialize and use a local SQLite database for fixtures, odds, predictions, results, settlements, and model versions.
"""

Test Cases:
- Initialize database in a temporary path.
- Re-run initialization idempotently.
- Insert and read a simple record through the storage helper.
- Invalid database path fails with a clear error.

Acceptance Criteria:
- Storage can be initialized locally and reused by later tasks.

### Task 6: Add MVP Tables and Models

Purpose:
Define the persistent entities required for traceable predictions and settlements.

Implementation Notes:
Add tables/models for fixtures, odds snapshots, predictions, results, settlements, and model versions. Include unique keys for idempotent ingestion.

Files Likely Touched:
Storage/schema module, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add MVP database tables/models.
Requirements:
- Add fixtures, odds_snapshots, predictions, results, settlements, and model_versions.
- Include provider IDs and raw payload storage where relevant.
- Add uniqueness constraints for fixture provider IDs and odds snapshot identity.
- Store prediction market type, selection, probability, confidence, model version, and odds snapshot reference.
- Store settlement status as pending, won, lost, void, or cancelled.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- All MVP data entities can be persisted and queried.
"""

Test Cases:
- Insert fixture and prevent duplicate provider fixture IDs.
- Insert odds snapshot linked to fixture.
- Insert prediction linked to fixture/model version/odds snapshot.
- Insert result and settlement linked to prediction.
- Invalid settlement status is rejected or normalized consistently.

Acceptance Criteria:
- MVP entities support traceability from broadcast prediction to settlement.

### Task 7: Add Daily Fixture Ingestion Job

Purpose:
Fetch and store upcoming fixtures once per day for prediction generation.

Implementation Notes:
The job should call API-Football/provider layer, normalize teams/times, and upsert fixtures.

Files Likely Touched:
Data ingestion module, scheduler integration, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add the daily fixture ingestion job.
Requirements:
- Fetch upcoming fixtures for configured leagues.
- Normalize team names and timezone-aware kickoff times.
- Upsert fixtures idempotently by provider fixture ID.
- Store raw provider payload for audit.
- Return ingestion counts for inserted, updated, skipped, and failed fixtures.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Running the job repeatedly stores one canonical fixture per provider fixture ID.
"""

Test Cases:
- First run inserts fixtures.
- Second run with same fixtures updates rather than duplicates.
- Malformed fixture is skipped and counted.
- Provider failure returns a failed count and does not crash the process.

Acceptance Criteria:
- Fixture ingestion is idempotent and observable.

### Task 8: Add Daily Odds Ingestion Job

Purpose:
Capture odds snapshots for the fixtures used by the daily predictions.

Implementation Notes:
Use The Odds API as primary odds source. Store odds snapshots with captured timestamp and provider payload.

Files Likely Touched:
Data ingestion module, odds provider integration, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add the daily odds ingestion job.
Requirements:
- Fetch odds for configured football leagues from The Odds API.
- Store odds snapshots for supported MVP markets.
- Store bookmaker/source, market type, selection, price, implied probability, and captured timestamp.
- Do not duplicate identical snapshots on repeated runs.
- Report API quota metadata if provider headers expose it.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Daily odds are persisted once and can be linked to predictions.
"""

Test Cases:
- Insert odds snapshots for h2h and totals markets.
- Duplicate provider payload does not create duplicate snapshots.
- Missing odds API key fails safely.
- Rate-limit/provider failure is logged and counted without crashing.

Acceptance Criteria:
- Predictions can reference stored odds snapshots.

### Task 9: Add Result Ingestion and Final Score Update Job

Purpose:
Fetch final scores and match statuses needed to settle predictions.

Implementation Notes:
Use API-Football results/status data. Update fixture status and persist final score details.

Files Likely Touched:
Data ingestion module, result module, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add result ingestion and final score update.
Requirements:
- Fetch final or updated match results for recently predicted fixtures.
- Store final home goals, final away goals, provider status, completion timestamp, and raw payload.
- Update fixture status consistently.
- Keep unfinished matches pending.
- Mark delayed/postponed/interrupted matches with enough metadata for settlement.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Final results are available for settlement without manual entry.
"""

Test Cases:
- Completed fixture stores final score.
- Pending fixture remains unsettled.
- Postponed fixture stores status and kickoff reference.
- Re-running result ingestion updates existing result without duplicate rows.

Acceptance Criteria:
- Settlement service has reliable result/status data.

### Task 10: Add Core Market Settlement Service

Purpose:
Apply `info.txt` settlement semantics to MVP market predictions.

Implementation Notes:
Implement regular-time settlement for 1X2, double chance, over/under 1.5, over/under 2.5, and BTTS.

Files Likely Touched:
New settlement module, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add the core market settlement service.
Requirements:
- Settle 1X2 predictions as home, draw, or away using regular-time final score.
- Settle double chance predictions as 1X, 12, or X2.
- Settle over/under 1.5 and 2.5 using total goals.
- Settle BTTS yes/no using final goals for both teams.
- Mark interrupted/postponed matches not completed within 48 hours as void.
- Exclude extra time and penalties from MVP settlement.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Stored predictions can be settled as won, lost, void, or cancelled.
"""

Test Cases:
- Home win, draw, and away win settle correctly for 1X2.
- Double chance 1X, 12, and X2 settle correctly.
- Over/under 1.5 and 2.5 settle correctly at boundary scores.
- BTTS yes/no settles correctly.
- Match not completed within 48 hours settles void.
- Cancelled/invalid fixture state creates a cancelled or void settlement reason.

Acceptance Criteria:
- MVP markets settle deterministically from stored final results.

### Task 11: Add Model Training and Backtesting Pipeline

Purpose:
Create reproducible training and evaluation before public performance claims.

Implementation Notes:
Use historical results and odds where available. Split train/test before fitting.

Files Likely Touched:
`app/train.py`, model modules, storage/model version module, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add or refactor the model training and backtesting pipeline.
Requirements:
- Fetch or load historical results for configured leagues/seasons.
- Split training and test data before fitting to avoid leakage.
- Train Dixon-Coles model and store model parameters.
- Store a model version record with training window, leagues, metrics, and artifact path.
- Produce backtest metrics by market type where supported.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Model artifacts and metrics are reproducible and versioned.
"""

Test Cases:
- Train/test split occurs before model fit.
- Model artifact is written when training succeeds.
- Model version record is created.
- Empty data fails clearly.
- Backtest metrics include sample size and exclude unavailable predictions.

Acceptance Criteria:
- Training no longer evaluates on data used for fitting.

### Task 12: Add Confidence Scoring and Market Filtering

Purpose:
Avoid broadcasting weak picks as if they are equally reliable.

Implementation Notes:
Define confidence buckets from probability edge, model certainty, and market availability. Filter daily broadcast to configured confidence thresholds.

Files Likely Touched:
Prediction service, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add confidence scoring and market filtering.
Requirements:
- Compute confidence as high, medium, or low for each prediction.
- Include model probability, implied odds probability, and configurable minimum threshold where data is available.
- Allow broadcast filtering by market type and minimum confidence.
- Store confidence with each prediction.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Broadcasts can prioritize stronger picks and report confidence transparently.
"""

Test Cases:
- High-confidence prediction is stored and eligible for broadcast.
- Low-confidence prediction is stored but filtered when threshold requires medium/high.
- Missing odds still produces a conservative confidence or unavailable state.
- Confidence values are deterministic for fixed inputs.

Acceptance Criteria:
- Market filtering is configurable and reproducible.

### Task 13: Add Telegram Daily Prediction Broadcast from Stored Predictions

Purpose:
Make Telegram delivery read from persisted predictions instead of triggering fresh API/model calls per user.

Implementation Notes:
Format a concise daily channel post grouped by match and market. Include model disclaimers and avoid overclaiming.

Files Likely Touched:
Bot/broadcast module, storage queries, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add Telegram daily prediction broadcast from stored predictions.
Requirements:
- Query stored predictions for the target broadcast date.
- Include match, league, kickoff time, market, selection, probability, confidence, and odds where available.
- Exclude predictions below configured broadcast confidence.
- Include responsible-gambling and no-guarantee disclaimer.
- Do not fetch APIs during broadcast formatting.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Telegram broadcast content is generated from stored prediction data only.
"""

Test Cases:
- Broadcast includes eligible stored predictions.
- Broadcast excludes low-confidence predictions when configured.
- Empty prediction day produces a clear no-picks message.
- Long messages are split safely for Telegram length limits.
- Formatting test verifies key fields appear.

Acceptance Criteria:
- Broadcast generation is cache/database-driven.

### Task 14: Add Telegram Result-Comparison Broadcast

Purpose:
Show users how previous predictions performed against actual results.

Implementation Notes:
Use settled predictions and final scores. Group by match and market.

Files Likely Touched:
Bot/broadcast module, settlement queries, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add Telegram result-comparison broadcast from settled predictions.
Requirements:
- Query settled predictions for a target date.
- Show final score, prediction selection, settlement result, and market type.
- Exclude pending predictions unless explicitly reporting them as pending.
- Exclude void/cancelled predictions from hit-rate summary while listing their status separately.
- Do not fetch APIs during broadcast formatting.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Telegram can publish a transparent daily performance recap.
"""

Test Cases:
- Won/lost predictions appear with correct labels.
- Void/cancelled predictions are separated from hit-rate denominator.
- Pending predictions are handled gracefully.
- Empty settlement day produces a clear no-results message.

Acceptance Criteria:
- Result comparison is based only on stored settlements.

### Task 15: Add Accuracy Reporting

Purpose:
Track performance credibly by market, confidence, and time window.

Implementation Notes:
Accuracy should exclude void/cancelled predictions and include sample sizes.

Files Likely Touched:
Reporting module, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add accuracy reporting by market, confidence bucket, and date range.
Requirements:
- Compute won, lost, void, cancelled, pending counts.
- Compute hit rate using only won + lost denominator.
- Group reports by market type and confidence bucket.
- Include sample size in all accuracy outputs.
- Provide a function or command that returns a structured report for Telegram/admin use.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Accuracy claims are transparent, market-specific, and sample-size aware.
"""

Test Cases:
- Void/cancelled predictions are excluded from hit-rate denominator.
- Pending predictions are counted but excluded from hit rate.
- Reports group correctly by market.
- Reports group correctly by confidence.
- Date range filtering works.

Acceptance Criteria:
- No global accuracy figure is produced without sample size and grouping context.

### Task 16: Add API Quota, Retry, and Error Handling

Purpose:
Make scheduled provider jobs robust enough for unattended daily operation.

Implementation Notes:
Add bounded retries, backoff, quota logging, and safe failure states.

Files Likely Touched:
Provider modules, ingestion jobs, tests.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add API quota, retry, and error handling.
Requirements:
- Add bounded retry/backoff around provider calls.
- Log quota headers when available.
- Treat 401/403 as configuration errors.
- Treat 429 as rate-limit errors and avoid tight retry loops.
- Scheduled jobs must return failure counts instead of crashing the whole process.
Constraints:
- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
Expected outcome:
- Provider failures are observable and do not break the daily scheduler.
"""

Test Cases:
- 429 response triggers rate-limit handling.
- 401/403 response triggers configuration error path.
- Transient 500 response retries then succeeds.
- Repeated failure returns failed count and logs context.
- Quota headers are captured when present.

Acceptance Criteria:
- API failures are handled predictably and safely.

### Task 17: Add Production Deployment Checklist

Purpose:
Give operators a clear release checklist for the Telegram MVP.

Implementation Notes:
Document deployment setup, environment variables, database setup, scheduled jobs, monitoring, and rollback.

Files Likely Touched:
`PRD_IMPLEMENTATION_PLAN.md`, `README.md`, optional deployment doc.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add a production deployment checklist.
Requirements:
- Document required environment variables.
- Document database initialization.
- Document model training before first broadcast.
- Document scheduled jobs and expected run times.
- Document health check and monitoring expectations.
- Document rollback and disabled-broadcast procedures.
Constraints:
- Do not change unrelated behavior.
- Add or update tests only if code is changed.
- Do not introduce random/fake predictions.
Expected outcome:
- A new operator can deploy and verify the MVP without guessing.
"""

Test Cases:
- Manual checklist review confirms every required env var is listed.
- Manual checklist review confirms first-run training and DB initialization steps exist.
- Manual checklist review confirms rollback/disable-broadcast instructions exist.

Acceptance Criteria:
- Deployment instructions are complete enough for a first MVP release.

### Task 18: Add Admin Runbook

Purpose:
Document daily operational procedures and incident handling.

Implementation Notes:
Include what to check each morning/evening, how to handle provider failures, and how to communicate transparent issues to users.

Files Likely Touched:
`PRD_IMPLEMENTATION_PLAN.md`, optional runbook doc.

Implementation Prompt:
"""
You are working in the FirmBetting repo. Add an admin runbook for daily FirmBetting operation.
Requirements:
- Document morning prediction checks.
- Document result-comparison checks.
- Document what to do when API providers fail.
- Document what to do when model predictions are unavailable.
- Document what to post publicly when predictions/results cannot be generated.
- Document accuracy review cadence.
Constraints:
- Do not change unrelated behavior.
- Add or update tests only if code is changed.
- Do not introduce random/fake predictions.
Expected outcome:
- Operators can run the Telegram MVP transparently and consistently.
"""

Test Cases:
- Manual review confirms normal daily operation steps exist.
- Manual review confirms provider failure steps exist.
- Manual review confirms model unavailable steps exist.
- Manual review confirms public communication guidance exists.

Acceptance Criteria:
- The admin runbook covers normal operation and likely MVP incidents.

## 4. Required Test Coverage Summary

The implementation must include automated tests for:

- Date filtering with UTC-aware and offset-aware fixture times.
- Training script fetch path.
- Missing model behavior.
- Unknown team behavior.
- No random prediction generation.
- Settlement: home win, draw, away win.
- Settlement: double chance.
- Settlement: over/under 1.5 and 2.5.
- Settlement: BTTS yes/no.
- Settlement: postponed/interrupted beyond 48 hours becomes void.
- Telegram broadcast formatting from stored predictions.
- Result-comparison broadcast formatting.
- Accuracy calculation excludes void/cancelled predictions.
- API failures do not crash scheduled jobs.
- Duplicate fixture/odds ingestion is idempotent.

Manual review tests are acceptable only for pure documentation tasks.

## 5. Production Deployment Checklist

- Rotate any credentials that were ever committed to source.
- Configure required environment variables:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHANNEL`
  - `API_FOOTBALL_KEY`
  - `ODDS_API_KEY`
  - `ODDS_API_BACKUP_KEYS`
  - `ODDS_PROVIDER`
  - `DATABASE_URL` or `FIRMBETTING_DB_PATH`
- Initialize the database.
- Run historical training/backtesting.
- Verify a model version exists.
- Run fixture ingestion manually.
- Run odds ingestion manually.
- Generate predictions manually.
- Preview Telegram prediction broadcast before enabling scheduler.
- Enable daily prediction scheduler.
- Enable result ingestion and settlement scheduler.
- Enable result-comparison broadcast.
- Verify health endpoint.
- Verify logs include provider failures and quota metadata.
- Keep a kill switch for broadcasts if model/data quality fails.

## 6. Admin Runbook

### Daily Morning Checks

- Confirm fixture ingestion completed.
- Confirm odds ingestion completed.
- Confirm model version is available.
- Confirm daily predictions were generated.
- Preview broadcast content.
- Confirm Telegram post was sent.

### Daily Result Checks

- Confirm final results were ingested.
- Confirm predictions were settled.
- Confirm void/cancelled predictions are excluded from hit-rate denominator.
- Preview result-comparison broadcast.
- Confirm Telegram result post was sent.

### Provider Failure Procedure

- Check provider status, credentials, quota, and logs.
- Retry only within configured retry limits.
- Do not generate fake predictions.
- If data remains unavailable, post a transparent no-picks/no-results message.

### Model Unavailable Procedure

- Do not broadcast predictions.
- Check latest model artifact and model version record.
- Re-run training if historical data is available.
- If model remains unavailable, publish a transparent service status update.

### Accuracy Review Cadence

- Review hit rate daily by market.
- Review confidence-bucket performance weekly.
- Do not promote subscription claims until sample size and ROI/hit-rate data are credible.

## 7. Assumptions

- The MVP uses API-Football for fixtures/results and The Odds API for odds/historical odds.
- Betfair, Pinnacle/international books, and Sportradar are roadmap integrations.
- SQLite is acceptable for MVP persistence unless Postgres is explicitly requested before implementation.
- Telegram channel broadcast is the only user-facing delivery path for MVP.
- Core markets are 1X2, double chance, over/under 1.5, over/under 2.5, and BTTS.
