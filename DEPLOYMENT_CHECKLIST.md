# FirmBetting MVP Production Deployment Checklist

Read `AGENTS.md` first and follow it strictly.

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather.
- `TELEGRAM_CHANNEL`: Telegram channel ID or handle for MVP broadcasts.
- `API_FOOTBALL_KEY`: API-Football key for fixtures, results, and historical data.
- `ODDS_API_KEY`: Primary The Odds API key.
- `ODDS_API_BACKUP_KEYS`: Optional comma-separated backup keys for The Odds API.
- `ODDS_PROVIDER`: Odds provider selector. Use `odds_api` for MVP.
- `DATABASE_URL`: Production database URL. Use the Neon/Postgres URL in Coolify.
- `FIRMBETTING_DB_PATH`: Local SQLite database path for dev/test only.

Never commit real credentials, Telegram tokens, or paid data-feed secrets.
Rotate any credential that was ever committed to source.

## Database Initialization

1. In Coolify, set `DATABASE_URL` to the Neon/Postgres connection URL. Use the raw `postgresql://...` URL value when possible.
2. For local dev only, use `FIRMBETTING_DB_PATH` or a `sqlite:///...` `DATABASE_URL`.
3. Run database initialization before any scheduled job:

```bash
python3 -c "from app.data.storage import initialize_database; initialize_database()"
```

4. Confirm the database contains the MVP tables: `fixtures`, `odds_snapshots`, `predictions`, `results`, `settlements`, and `model_versions`.

## Model Training Before First Broadcast

1. Confirm `API_FOOTBALL_KEY` is configured.
2. Fetch historical results and train before publishing predictions:

```bash
python3 -m app.train --leagues 39,140,61,135,78 --seasons 2024,2025
```

3. Confirm `data/model.json` exists.
4. Confirm a `model_versions` row exists with metrics, training window, and artifact path.
5. If historical data or model artifacts are unavailable, disable prediction broadcast and publish a transparent service-status message.

## Scheduled Jobs

All scheduled jobs must read and write cached storage. Broadcast formatting must not call provider APIs.

- Morning fixture ingestion: run before odds ingestion.
- Morning odds ingestion: run after fixtures are stored.
- Prediction generation: run after fixtures, odds, and model version are available.
- Daily prediction broadcast: run after prediction generation, ideally morning Africa/Lagos time.
- Result ingestion: run after matches finish, and repeat for delayed statuses.
- Settlement: run after result ingestion.
- Result-comparison broadcast: run after settlement, typically evening or next morning.

## Manual First-Run Verification

1. Run fixture ingestion manually and confirm inserted/updated counts.
2. Run odds ingestion manually and confirm snapshots are linked to fixtures.
3. Generate predictions manually and confirm every prediction references fixture, market type, model version, odds snapshot where available, and confidence.
4. Preview the Telegram prediction broadcast from stored predictions.
5. Run result ingestion with a known completed fixture.
6. Run settlement and confirm won/lost/void/cancelled handling.
7. Preview the result-comparison broadcast.

## Health Checks And Monitoring

- Verify the health server starts with the bot process.
- Confirm logs include provider failures, retry outcomes, quota metadata where available, and ingestion counts.
- Alert on missing model artifact, missing credentials, zero eligible predictions, repeated provider failures, and Telegram send failures.
- Track daily accuracy by market type and confidence bucket with sample size.

## Rollback And Disabled-Broadcast Procedures

- Keep a kill switch for Telegram broadcasts by stopping the scheduler or unsetting `TELEGRAM_CHANNEL`.
- If model/data quality fails, do not publish predictions.
- If fixture, odds, or result providers fail after retries, publish a transparent no-picks/no-results update instead of generating substitute predictions.
- Roll back to the previous deployed image or commit if ingestion, settlement, or broadcast formatting regresses.
- After rollback, verify the database remains intact and no duplicate provider fixture IDs or odds snapshots were created.
