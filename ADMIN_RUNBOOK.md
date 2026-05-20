# FirmBetting MVP Admin Runbook

Read `AGENTS.md` first and follow it strictly.

## Operating Principle

If data, model artifacts, or settlement inputs are unavailable, do not generate substitute predictions. Publish a transparent no-picks/no-results status instead.

## Daily Morning Prediction Checks

1. Confirm fixture ingestion completed and review inserted, updated, skipped, and failed counts.
2. Confirm odds ingestion completed and odds snapshots are linked to stored fixtures.
3. Confirm the latest model artifact exists at the configured artifact path.
4. Confirm a `model_versions` record exists for the active model.
5. Confirm daily predictions were generated from stored fixtures and odds.
6. Confirm every prediction has fixture, market type, model version, probability, confidence, and odds snapshot where available.
7. Preview the Telegram prediction broadcast from stored predictions.
8. Send the Telegram prediction post only if the content is traceable and no unavailable status is present.

## Daily Result-Comparison Checks

1. Confirm result ingestion completed for predicted fixtures.
2. Confirm final scores and provider statuses were stored.
3. Confirm settlement ran after result ingestion.
4. Confirm `void` and `cancelled` predictions are excluded from hit-rate denominators.
5. Preview the result-comparison broadcast.
6. Send the Telegram result post only after final scores and settlement statuses look consistent.

## API Provider Failure Procedure

1. Check provider status dashboards, credentials, quota, and logs.
2. Review retry/backoff logs and quota metadata.
3. Retry only within configured retry limits.
4. Do not bypass cached storage by making ad hoc broadcast-time API calls.
5. If fixtures or odds remain unavailable, publish a no-picks message.
6. If results remain unavailable, publish a no-results-pending message and retry result ingestion later.

Suggested public message:

```text
Today no verified picks are available because fixture or odds data could not be confirmed. We will not publish unverified predictions.
```

## Model Unavailable Procedure

1. Do not broadcast predictions.
2. Check the latest model artifact path.
3. Check the active `model_versions` record.
4. Re-run historical training only if reliable historical data is available.
5. If training still fails or known teams are unavailable, publish a transparent service-status update.

Suggested public message:

```text
Predictions are paused while we verify the model and data pipeline. We will resume only when picks are traceable and auditable.
```

## Result Or Settlement Incident Procedure

1. Check API-Football result payloads and fixture statuses.
2. Confirm only regular 90 minutes plus stoppage time is used for MVP settlement.
3. Exclude extra time and penalties from settlement.
4. Void interrupted or postponed matches not completed within 48 hours after initial kickoff.
5. Mark invalid fixture/team/score-source cases as `void` or `cancelled` with a reason.
6. Re-run settlement after corrected result data is stored.

Suggested public message:

```text
Some results are still pending verification. We will publish the comparison once final regular-time scores are confirmed.
```

## Accuracy Review Cadence

- Daily: review won, lost, void, cancelled, and pending counts by market type.
- Daily: confirm hit rate excludes `void`, `cancelled`, and `pending`.
- Weekly: review confidence-bucket performance.
- Weekly: check sample size before making any performance claims.
- Never promote a broad accuracy claim without market type, confidence bucket, sample size, date range, and void/cancelled handling.

## Kill Switch

- Stop the scheduler or unset `TELEGRAM_CHANNEL` to disable broadcasts.
- Keep ingestion and settlement jobs available for recovery unless they are causing data corruption.
- After any incident, verify fixture and odds idempotency before re-enabling broadcasts.
