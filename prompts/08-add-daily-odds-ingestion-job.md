Read AGENTS.md first and follow it strictly.

# Task 8: Add Daily Odds Ingestion Job

Status: completed

## Context

You are working in the FirmBetting repo. Add the daily odds ingestion job.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- The Odds API documentation, if provider request/response details need verification: `https://the-odds-api.com/liveapi/guides/v4/`

## Requirements

- Fetch odds for configured football leagues from The Odds API.
- Store odds snapshots for supported MVP markets.
- Store bookmaker/source, market type, selection, price, implied probability, and captured timestamp.
- Do not duplicate identical snapshots on repeated runs.
- Report API quota metadata if provider headers expose it.

## Files Likely Touched

- Data ingestion module
- odds provider integration
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Insert odds snapshots for h2h and totals markets.
- Duplicate provider payload does not create duplicate snapshots.
- Missing odds API key fails safely.
- Rate-limit/provider failure is logged and counted without crashing.

## Expected Outcome

Daily odds are persisted once and can be linked to predictions.

## Acceptance Criteria

Predictions can reference stored odds snapshots.
