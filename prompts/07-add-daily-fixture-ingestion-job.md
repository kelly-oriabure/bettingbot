Read AGENTS.md first and follow it strictly.

# Task 7: Add Daily Fixture Ingestion Job

Status: completed

## Context

You are working in the FirmBetting repo. Add the daily fixture ingestion job.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Fetch upcoming fixtures for configured leagues.
- Normalize team names and timezone-aware kickoff times.
- Upsert fixtures idempotently by provider fixture ID.
- Store raw provider payload for audit.
- Return ingestion counts for inserted, updated, skipped, and failed fixtures.

## Files Likely Touched

- Data ingestion module
- scheduler integration
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- First run inserts fixtures.
- Second run with same fixtures updates rather than duplicates.
- Malformed fixture is skipped and counted.
- Provider failure returns a failed count and does not crash the process.

## Expected Outcome

Running the job repeatedly stores one canonical fixture per provider fixture ID.

## Acceptance Criteria

Fixture ingestion is idempotent and observable.
