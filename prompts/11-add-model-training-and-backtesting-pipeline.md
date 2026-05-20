Read AGENTS.md first and follow it strictly.

# Task 11: Add Model Training and Backtesting Pipeline

Status: completed

## Context

You are working in the FirmBetting repo. Add or refactor the model training and backtesting pipeline.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`
- API-Football documentation, if historical fixture/result details need verification: `https://www.api-football.com/documentation-v3`
- The Odds API documentation, if historical odds details need verification: `https://the-odds-api.com/liveapi/guides/v4/`

## Requirements

- Fetch or load historical results for configured leagues/seasons.
- Split training and test data before fitting to avoid leakage.
- Train Dixon-Coles model and store model parameters.
- Store a model version record with training window, leagues, metrics, and artifact path.
- Produce backtest metrics by market type where supported.

## Files Likely Touched

- `app/train.py`
- model modules
- storage/model version module
- tests

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Train/test split occurs before model fit.
- Model artifact is written when training succeeds.
- Model version record is created.
- Empty data fails clearly.
- Backtest metrics include sample size and exclude unavailable predictions.

## Expected Outcome

Model artifacts and metrics are reproducible and versioned.

## Acceptance Criteria

Training no longer evaluates on data used for fitting.
