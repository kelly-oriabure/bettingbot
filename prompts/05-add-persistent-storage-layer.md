Read AGENTS.md first and follow it strictly.

# Task 5: Add Persistent Storage Layer

Status: completed

## Context

You are working in the FirmBetting repo. Add a persistent storage layer for the MVP.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Use SQLite by default with a configurable database path.
- Provide connection/session helpers.
- Provide initialization/migration logic for MVP tables.
- Keep provider payload fields storable as JSON text.

## Files Likely Touched

- New storage module
- tests
- `requirements.txt` if needed

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Initialize database in a temporary path.
- Re-run initialization idempotently.
- Insert and read a simple record through the storage helper.
- Invalid database path fails with a clear error.

## Expected Outcome

The app can initialize and use a local SQLite database for fixtures, odds, predictions, results, settlements, and model versions.

## Acceptance Criteria

Storage can be initialized locally and reused by later tasks.
