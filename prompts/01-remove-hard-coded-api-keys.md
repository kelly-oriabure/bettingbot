Read AGENTS.md first and follow it strictly.

# Task 1: Remove Hard-Coded API Keys and Document Environment Variables

Status: completed

## Context

You are working in the FirmBetting repo. Implement removal of hard-coded API credentials and document required environment variables.

## Resources

- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/AGENTS.md`
- `/Users/kelly.o/Documents/projects/openclaw-repos/firmbetting/PRD_IMPLEMENTATION_PLAN.md`

## Requirements

- Remove all literal API keys, Telegram tokens, and provider secrets from source code.
- The Odds API provider must use only `ODDS_API_KEY` and optional comma-separated `ODDS_API_BACKUP_KEYS`.
- If no odds API key is configured, provider calls must fail safely with a clear log message and no network request.
- Document `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL`, `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `ODDS_API_BACKUP_KEYS`, `ODDS_PROVIDER`, and database path configuration.

## Files Likely Touched

- `app/data/fetcher.py`
- `README.md`
- optional `.env.example`

## Constraints

- Do not change unrelated behavior.
- Add or update tests for this task.
- Do not introduce random/fake predictions.

## Test Cases

- Search source for old literal keys and confirm none remain.
- Instantiate Odds API provider without keys and verify it reports unavailable rather than using fallback keys.
- Instantiate with `ODDS_API_KEY` and verify exactly one configured key is present.
- Instantiate with backup keys and verify key rotation uses only environment-provided keys.

## Expected Outcome

No provider secrets remain in tracked source files and missing keys are handled explicitly.

## Acceptance Criteria

- No hard-coded provider secrets exist in source.
- Missing credentials do not trigger API calls.
- Required environment variables are documented.
