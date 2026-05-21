---
name: telegram-prediction-mvp
description: Use when building or upgrading a Telegram-first football prediction MVP with provider ingestion, durable storage, prediction broadcasts, result settlement, Coolify deployment, or Neon/Postgres migration work.
---

# Telegram Prediction MVP

## Overview

Use this skill to make safe, testable changes to a football prediction app whose MVP publishes daily Telegram picks and separate result-comparison broadcasts. The priority is trust: deterministic ingestion, traceable predictions, honest confidence display, and auditable settlement.

## First Steps

1. Read `AGENTS.md` first and follow it strictly.
2. Read `info.txt` before changing football market settlement behavior.
3. Inspect the existing implementation before editing. Prefer `rg`, focused file reads, and small patches.
4. Treat `.env`, API keys, Telegram tokens, provider credentials, and database URLs as local secrets. Never commit or print them.
5. Confirm whether the app runs on Coolify, local development, or both. Keep production behavior driven by environment variables, especially `DATABASE_URL`, provider keys, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHANNEL`.

## Safety Rules

- Never generate random or fake predictions.
- If provider data, model files, odds, or required team mappings are missing, return an unavailable status instead of mock output.
- Do not claim accuracy without tracked sample size, market type, confidence bucket, and void/cancelled handling.
- Keep betting copy cautious. Do not present picks as guaranteed or instruct users to place bets.
- Support only these MVP markets unless the user explicitly expands scope: `1X2`, double chance, over/under 1.5, over/under 2.5, and BTTS.
- Exclude `void` and `cancelled` predictions from accuracy denominators.

## Implementation Workflow

1. Keep ingestion, prediction, settlement, reporting, scheduling, and Telegram delivery as separate modules or functions.
2. Store provider fixture, odds, and result responses before broadcasts. Broadcasts should read cached data, not call paid APIs at send time.
3. Make provider ingestion idempotent by using provider fixture IDs, event IDs, snapshot timestamps, or deterministic upserts.
4. Persist every prediction with fixture reference, market type, selection, confidence/probability, model version, odds snapshot, and settlement rule.
5. Store raw provider payloads where useful for audit and debugging.
6. Keep SQLite acceptable for local MVP work, but prefer storage APIs that work with Postgres/Neon through `DATABASE_URL`.
7. For Coolify, avoid machine-specific paths and implicit local services. Use environment variables and application startup hooks that are safe in a container.
8. Wire result-comparison broadcasts as a separate Telegram message from the daily prediction broadcast.

## NeonDB and Postgres

Use NeonDB when the app needs production-grade persistence on Coolify or shared state across deploys.

- Read the database connection from `DATABASE_URL`; do not hard-code Neon connection strings.
- Require SSL for Neon connections, normally through the provided URL parameters such as `sslmode=require`.
- Keep local SQLite support when it is already part of the MVP, but make storage code compatible with Postgres placeholders, transactions, JSON fields, timestamps, and upserts.
- Put schema creation or migrations in repeatable startup/admin paths. Do not depend on manually created tables unless the task is explicitly operational.
- Test Postgres behavior with focused integration checks when the user grants permission to use the external Neon database.
- Use small, harmless smoke rows or read-only checks for live Neon tests, and clean up test data when cleanup is safe and scoped.
- Never print, commit, or store Neon credentials outside local `.env` or the deployment environment.
- On Coolify, confirm the same environment variables used locally are configured in the app service before changing runtime assumptions.

## Telegram Broadcasts

Make messages easy for non-technical readers to scan on a phone.

- Use short headings, compact spacing, and plain labels.
- Show confidence as a percentage, not vague labels.
- Use confidence icons consistently:
  - Green tick for stronger picks, normally `>= 65%`.
  - Orange circle for medium picks, normally `55%` to `64.9%`.
  - Red x for low confidence or below-shortlist picks, normally `< 55%`.
- Keep the reminder short and italic.
- Do not include long explanations, raw model terms, or betting jargon in the public message.
- Send settled results as a separate Telegram broadcast that compares actual match results against previous predictions.

## Testing Checklist

Run compile/tests before handing work back when code changes are made. Add focused tests for:

- Provider config and missing-key failure paths.
- Fixture, odds, prediction, result, and settlement persistence.
- Idempotent ingestion.
- Market settlement semantics against `info.txt`.
- Telegram formatting for predictions and result-comparison messages.
- Scheduler/send paths so the same code path used in production is covered.
- Database compatibility for SQLite and Postgres/Neon when storage code changes.

For live smoke tests, only call external providers, Neon, or Telegram when the user has given permission and the required credentials are available locally. Report what was verified without exposing secrets.

## Completion Notes

When finishing a task, summarize the changed files, tests run, and any live checks performed. If a prompt/task file tracks status, mark it `completed`, `partial completed`, or `not completed` only after verification.
