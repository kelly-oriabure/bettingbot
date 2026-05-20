Read AGENTS.md first and follow it strictly.

# Task 13: Add Telegram Daily Prediction Broadcast from Stored Predictions

Status: completed

## Context

You are working in the FirmBetting repo. Add Telegram daily prediction broadcast from stored predictions.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- Telegram Bot API documentation, if message limits or send behavior need verification: `https://core.telegram.org/bots/api`

## Requirements

- Query stored predictions for the target broadcast date.
- Include match, league, kickoff time, market, selection, probability, confidence, and odds where available.
- Exclude predictions below configured broadcast confidence.
- Include responsible-gambling and no-guarantee disclaimer.
- Do not fetch APIs during broadcast formatting.

## Files Likely Touched

- Bot/broadcast module
- storage queries
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Broadcast includes eligible stored predictions.
- Broadcast excludes low-confidence predictions when configured.
- Empty prediction day produces a clear no-picks message.
- Long messages are split safely for Telegram length limits.
- Formatting test verifies key fields appear.

## Expected Outcome

Telegram broadcast content is generated from stored prediction data only.

## Acceptance Criteria

Broadcast generation is cache/database-driven.
