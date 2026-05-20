Read AGENTS.md first and follow it strictly.

# Task 6: Add MVP Tables and Models

Status: completed

## Context

You are working in the FirmBetting repo. Add MVP database tables/models.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Add fixtures, odds_snapshots, predictions, results, settlements, and model_versions.
- Include provider IDs and raw payload storage where relevant.
- Add uniqueness constraints for fixture provider IDs and odds snapshot identity.
- Store prediction market type, selection, probability, confidence, model version, and odds snapshot reference.
- Store settlement status as pending, won, lost, void, or cancelled.

## Files Likely Touched

- Storage/schema module
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Insert fixture and prevent duplicate provider fixture IDs.
- Insert odds snapshot linked to fixture.
- Insert prediction linked to fixture/model version/odds snapshot.
- Insert result and settlement linked to prediction.
- Invalid settlement status is rejected or normalized consistently.

## Expected Outcome

All MVP data entities can be persisted and queried.

## Acceptance Criteria

MVP entities support traceability from broadcast prediction to settlement.
