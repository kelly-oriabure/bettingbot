Read AGENTS.md first and follow it strictly.

# Task 3: Fix Timezone-Aware Fixture Filtering

Status: completed

## Context

You are working in the FirmBetting repo. Implement timezone-safe fixture filtering.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Use timezone-aware UTC values for `now`, parsed fixture times, and window end times.
- Support fixture dates ending in `Z`, explicit offsets like `+01:00`, and naive ISO strings by treating naive strings as UTC.
- Apply the fix to today and upcoming fixture filtering.

## Files Likely Touched

- `app/data/fetcher.py`
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Fixture at `2026-05-20T12:00:00Z` inside window is included.
- Fixture at `2026-05-20T13:00:00+01:00` inside equivalent UTC window is included.
- Fixture outside the requested window is excluded.
- Naive ISO fixture timestamp is treated as UTC.
- No `TypeError` is raised for aware/naive comparisons.

## Expected Outcome

Date filtering works for UTC-aware, offset-aware, and naive fixture timestamps.

## Acceptance Criteria

Today/upcoming filtering is deterministic and timezone-safe.
