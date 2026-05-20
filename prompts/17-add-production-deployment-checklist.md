Read AGENTS.md first and follow it strictly.

# Task 17: Add Production Deployment Checklist

Status: completed

## Context

You are working in the FirmBetting repo. Add a production deployment checklist.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Document required environment variables.
- Document database initialization.
- Document model training before first broadcast.
- Document scheduled jobs and expected run times.
- Document health check and monitoring expectations.
- Document rollback and disabled-broadcast procedures.

## Files Likely Touched

- `PRD_IMPLEMENTATION_PLAN.md`
- `README.md`
- optional deployment doc

## Constraints

- Do not change unrelated behavior.
- Add or update tests only if code is changed.
- Do not introduce random/fake predictions.

## Test Cases

- Manual checklist review confirms every required env var is listed.
- Manual checklist review confirms first-run training and DB initialization steps exist.
- Manual checklist review confirms rollback/disable-broadcast instructions exist.

## Expected Outcome

A new operator can deploy and verify the MVP without guessing.

## Acceptance Criteria

Deployment instructions are complete enough for a first MVP release.
