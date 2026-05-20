Read AGENTS.md first and follow it strictly.

# Task 14: Add Telegram Result-Comparison Broadcast

Status: completed

## Context

You are working in the FirmBetting repo. Add Telegram result-comparison broadcast from settled predictions.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/info.txt`
- Telegram Bot API documentation, if message limits or send behavior need verification: `https://core.telegram.org/bots/api`

## Requirements

- Query settled predictions for a target date.
- Show final score, prediction selection, settlement result, and market type.
- Exclude pending predictions unless explicitly reporting them as pending.
- Exclude void/cancelled predictions from hit-rate summary while listing their status separately.
- Do not fetch APIs during broadcast formatting.

## Files Likely Touched

- Bot/broadcast module
- settlement queries
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Won/lost predictions appear with correct labels.
- Void/cancelled predictions are separated from hit-rate denominator.
- Pending predictions are handled gracefully.
- Empty settlement day produces a clear no-results message.

## Expected Outcome

Telegram can publish a transparent daily performance recap.

## Acceptance Criteria

Result comparison is based only on stored settlements.
