Read AGENTS.md first and follow it strictly.

# Task 9: Add Result Ingestion and Final Score Update Job

Status: completed

## Context

You are working in the FirmBetting repo. Add result ingestion and final score update.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- API-Football documentation, if provider result/status details need verification: `https://www.api-football.com/documentation-v3`

## Requirements

- Fetch final or updated match results for recently predicted fixtures.
- Store final home goals, final away goals, provider status, completion timestamp, and raw payload.
- Update fixture status consistently.
- Keep unfinished matches pending.
- Mark delayed/postponed/interrupted matches with enough metadata for settlement.

## Files Likely Touched

- Data ingestion module
- result module
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Completed fixture stores final score.
- Pending fixture remains unsettled.
- Postponed fixture stores status and kickoff reference.
- Re-running result ingestion updates existing result without duplicate rows.

## Expected Outcome

Final results are available for settlement without manual entry.

## Acceptance Criteria

Settlement service has reliable result/status data.
