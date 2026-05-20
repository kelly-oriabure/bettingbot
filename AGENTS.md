# AGENTS.md

## Project Purpose

FirmBetting is a Telegram-first football prediction platform. The MVP publishes one daily prediction broadcast and a later result-comparison broadcast to a Telegram channel. Users do not trigger API-backed predictions during the MVP.

The product goal is to build trust through transparent, market-specific prediction performance before introducing paid subscriptions.

## Safety and Business Rules

- Never generate random or fake predictions.
- Never commit API keys, Telegram tokens, provider credentials, or paid data-feed secrets.
- Never claim 70% accuracy without tracked sample size, market type, confidence bucket, and void/cancelled handling.
- Treat betting outputs as high-risk user-facing content.
- If model/data requirements are missing, fail safely and report unavailable status.
- Do not present predictions as guaranteed outcomes.

## MVP Market Rules

Support only these markets unless explicitly asked otherwise:

- 1X2
- Double chance
- Over/under 1.5
- Over/under 2.5
- BTTS

Settlement rules:

- Settle regular 90 minutes plus stoppage time only.
- Exclude extra time and penalties.
- Void interrupted or postponed matches not completed within 48 hours after initial kickoff.
- Exclude `void` and `cancelled` predictions from accuracy denominators.
- Use `info.txt` as the source for football market settlement semantics.

Do not implement player props, cards, corners, interval markets, or goalscorer markets unless the task explicitly asks for them.

## Engineering Rules

- Prefer small, testable changes.
- Keep ingestion, prediction, settlement, reporting, and Telegram delivery separate.
- Store daily provider responses/results so broadcasts read cached data instead of calling APIs at send time.
- Preserve deterministic behavior in tests.
- Use timezone-aware datetimes.
- Make provider ingestion idempotent.
- Store raw provider payloads where useful for audit/debugging.
- Keep SQLite acceptable for MVP, but avoid choices that block a later Postgres migration.
- Avoid touching unrelated files.

## Data and Prediction Rules

- Every prediction must be traceable to fixture, market type, model version, odds snapshot, and settlement rule.
- Missing model files must not trigger mock output.
- Unknown teams must produce unavailable status rather than fabricated probabilities.
- Accuracy must be grouped by market type and include sample size.
- Backtests must split training/test data before fitting to avoid leakage.

## Validation Instructions

- Run compile/tests before final response when code changes are made.
- If dependencies are unavailable, report what could not be verified.
- Documentation-only changes should still be checked for expected files and sections.
- Use `rg` for searching.
- Do not run destructive git commands unless explicitly requested.

## Operational Defaults

- API-Football is the MVP source for fixtures/results.
- The Odds API is the MVP source for odds and historical odds where available.
- Betfair, Pinnacle/international books, and Sportradar are roadmap integrations.
- Telegram channel broadcast is the MVP delivery path.
