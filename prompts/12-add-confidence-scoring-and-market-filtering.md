Read AGENTS.md first and follow it strictly.

# Task 12: Add Confidence Scoring and Market Filtering

Status: completed

## Context

You are working in the FirmBetting repo. Add confidence scoring and market filtering.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Compute confidence as high, medium, or low for each prediction.
- Include model probability, implied odds probability, and configurable minimum threshold where data is available.
- Allow broadcast filtering by market type and minimum confidence.
- Store confidence with each prediction.

## Files Likely Touched

- Prediction service
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- High-confidence prediction is stored and eligible for broadcast.
- Low-confidence prediction is stored but filtered when threshold requires medium/high.
- Missing odds still produces a conservative confidence or unavailable state.
- Confidence values are deterministic for fixed inputs.

## Expected Outcome

Broadcasts can prioritize stronger picks and report confidence transparently.

## Acceptance Criteria

Market filtering is configurable and reproducible.
