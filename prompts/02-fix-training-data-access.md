Read AGENTS.md first and follow it strictly.

# Task 2: Fix Training Data Access

Status: completed

## Context

You are working in the FirmBetting repo. Implement the training data access fix.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Ensure `python -m app.train` can call the historical data fetch path without `AttributeError`.
- Preserve API-Football as the historical training data source.
- Add a test that verifies the training fetch function calls the API-Football client path.

## Files Likely Touched

- `app/data/fetcher.py`
- `app/train.py`
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Mock API-Football historical data client and assert `fetch_data()` returns the mocked DataFrame.
- Verify empty historical data still exits/fails with a clear message.
- Verify `DataManager` exposes the selected training data access method if delegation is chosen.

## Expected Outcome

Training script reaches historical data retrieval through a valid method.

## Acceptance Criteria

- `fetch_data()` no longer references a missing method.
- Training data retrieval is covered by tests.
