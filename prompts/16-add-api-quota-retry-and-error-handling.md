Read AGENTS.md first and follow it strictly.

# Task 16: Add API Quota, Retry, and Error Handling

Status: completed

## Context

You are working in the FirmBetting repo. Add API quota, retry, and error handling.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- API-Football documentation, if status/error details need verification: `https://www.api-football.com/documentation-v3`
- The Odds API documentation, if status/quota header details need verification: `https://the-odds-api.com/liveapi/guides/v4/`

## Requirements

- Add bounded retry/backoff around provider calls.
- Log quota headers when available.
- Treat 401/403 as configuration errors.
- Treat 429 as rate-limit errors and avoid tight retry loops.
- Scheduled jobs must return failure counts instead of crashing the whole process.

## Files Likely Touched

- Provider modules
- ingestion jobs
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- 429 response triggers rate-limit handling.
- 401/403 response triggers configuration error path.
- Transient 500 response retries then succeeds.
- Repeated failure returns failed count and logs context.
- Quota headers are captured when present.

## Expected Outcome

Provider failures are observable and do not break the daily scheduler.

## Acceptance Criteria

API failures are handled predictably and safely.
