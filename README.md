# BettingBot - AI Football Prediction Telegram Bot

A Telegram bot that predicts football match outcomes using statistical and ML models, designed for monetized subscription delivery.

## Architecture

- **Prediction Engine:** Dixon-Coles Poisson + XGBoost ensemble
- **Data Sources:** API-Football, The Odds API, football-data.org
- **Bot:** Python-telegram-bot with subscription tiers
- **Deployment:** Docker on Coolify

## Models

1. **Dixon-Coles Poisson** — attack/defense strength → expected goals → score probability matrix
2. **XGBoost** — gradient boosting on 50+ features (form, H2H, home/away, xG, odds)
3. **Ensemble** — weighted stacking of both models with calibration

## Prediction Outputs

For each match, the bot provides:
- **Match outcome:** Home Win / Draw / Away Win (with probability %)
- **Correct score:** Top 3 most likely scores
- **Over/Under:** 2.5 goals confidence
- **BTTS:** Both Teams To Score confidence
- **Value bet alerts:** Where model probability > bookmaker implied probability

## Setup

### 1. Telegram Bot Token
Create via [@BotFather](https://t.me/BotFather), then set as `TELEGRAM_BOT_TOKEN` env var.

### 2. API Keys
- **API-Football:** Free at https://www.api-football.com (100 req/day)
- **The Odds API:** Free at https://the-odds-api.com (500 req/month)
- **OpenRouter:** For enhanced LLM analysis (optional)

### 3. Local Run
```bash
cd bettingbot
python3 -m venv venv
venv/bin/pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="your-token"
export API_FOOTBALL_KEY="your-key"
export ODDS_API_KEY="your-key"
python -m app
```

### 4. Deploy on Coolify
Push to GitHub → Coolify auto-deploys via Dockerfile.

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + subscribe |
| `/today` | Today's predictions |
| `/predict <team1> <team2>` | Specific match prediction |
| `/value` | High-value bet alerts |
| `/leagues` | Supported leagues |
| `/subscribe` | Subscription plans |
| `/accuracy` | Bot's historical accuracy |
| `/help` | All commands |

## Subscription Tiers

| Tier | Price | Features |
|------|-------|----------|
| Free | $0 | 3 predictions/day, basic output |
| Pro | $9.99/mo | Unlimited, value bets, all markets |
| VIP | $24.99/mo | Pro + in-play alerts + correct score priority |

## License
Proprietary - Firmcloud LTD
# Trigger deploy Thu Apr  2 03:30:51 UTC 2026
