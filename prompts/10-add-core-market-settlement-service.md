Read AGENTS.md first and follow it strictly.

# Task 10: Add Core Market Settlement Service

Status: completed

## Context

You are working in the FirmBetting repo. Add the core market settlement service.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/info.txt`

## Requirements

- Settle 1X2 predictions as home, draw, or away using regular-time final score.
- Settle double chance predictions as 1X, 12, or X2.
- Settle over/under 1.5 and 2.5 using total goals.
- Settle BTTS yes/no using final goals for both teams.
- Mark interrupted/postponed matches not completed within 48 hours as void.
- Exclude extra time and penalties from MVP settlement.

## Files Likely Touched

- New settlement module
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.
- Use `info.txt` as the source for football market settlement semantics.

## Test Cases

- Home win, draw, and away win settle correctly for 1X2.
- Double chance 1X, 12, and X2 settle correctly.
- Over/under 1.5 and 2.5 settle correctly at boundary scores.
- BTTS yes/no settles correctly.
- Match not completed within 48 hours settles void.
- Cancelled/invalid fixture state creates a cancelled or void settlement reason.

## Expected Outcome

Stored predictions can be settled as won, lost, void, or cancelled.

## Acceptance Criteria

MVP markets settle deterministically from stored final results.
