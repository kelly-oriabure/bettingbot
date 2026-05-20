Read AGENTS.md first and follow it strictly.

# Task 15: Add Accuracy Reporting

Status: completed

## Context

You are working in the FirmBetting repo. Add accuracy reporting by market, confidence bucket, and date range.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Compute won, lost, void, cancelled, pending counts.
- Compute hit rate using only won + lost denominator.
- Group reports by market type and confidence bucket.
- Include sample size in all accuracy outputs.
- Provide a function or command that returns a structured report for Telegram/admin use.

## Files Likely Touched

- Reporting module
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Void/cancelled predictions are excluded from hit-rate denominator.
- Pending predictions are counted but excluded from hit rate.
- Reports group correctly by market.
- Reports group correctly by confidence.
- Date range filtering works.

## Expected Outcome

Accuracy claims are transparent, market-specific, and sample-size aware.

## Acceptance Criteria

No global accuracy figure is produced without sample size and grouping context.
