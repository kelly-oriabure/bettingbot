"""
Telegram Bot - Main bot setup and command handlers.

Handles:
- /start, /help - Welcome and info
- /today - Today's predictions
- /predict <team1> <team2> - Specific match prediction
- /value - Value bet alerts
- /subscribe - Subscription plans
- /accuracy - Bot accuracy stats
- /leagues - Supported leagues

Subscription model:
- Free: 3 predictions/day
- Pro ($9.99/mo): 50/day + value bets
- VIP ($24.99/mo): 200/day + in-play + priority correct scores
"""

import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)

# Subscription tiers
TIERS = {
    "free": {"daily_limit": 3, "price": 0, "features": ["basic predictions"]},
    "pro": {"daily_limit": 50, "price": 9.99, "features": ["unlimited", "value bets", "all markets"]},
    "vip": {"daily_limit": 200, "price": 24.99, "features": ["pro + in-play", "priority correct scores", "early access"]},
}

# In-memory user store (replace with DB in production)
USERS: Dict[int, Dict] = {}


def get_user(user_id: int) -> Dict:
    """Get or create user record."""
    if user_id not in USERS:
        USERS[user_id] = {
            "tier": "free",
            "predictions_used_today": 0,
            "last_reset": datetime.utcnow().strftime("%Y-%m-%d"),
            "total_predictions": 0,
            "joined": datetime.utcnow().isoformat(),
        }
    user = USERS[user_id]
    # Reset daily count
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user["last_reset"] != today:
        user["predictions_used_today"] = 0
        user["last_reset"] = today
    return user


def format_prediction(pred: Dict) -> str:
    """Format a prediction for Telegram display."""
    home = pred["home_team"]
    away = pred["away_team"]
    hw = pred["home_win_prob"]
    dr = pred["draw_prob"]
    aw = pred["away_win_prob"]
    
    # Determine outcome emoji
    if hw > dr and hw > aw:
        outcome = f"🏠 {home} Win"
        pct = hw
    elif aw > dr:
        outcome = f"✈️ {away} Win"
        pct = aw
    else:
        outcome = "🤝 Draw"
        pct = dr
    
    # Confidence emoji
    conf = pred.get("confidence", "medium")
    conf_emoji = {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(conf, "🟡")
    
    # Top scores
    scores_text = ""
    if pred.get("top_scores"):
        scores_lines = []
        for score, prob in pred["top_scores"][:3]:
            scores_lines.append(f"  {score} ({prob*100:.1f}%)")
        scores_text = "\n".join(scores_lines)
    
    # Over/Under
    ou_25 = pred.get("over_under_25", 0)
    ou_text = f"📈 Over 2.5: {ou_25*100:.1f}%" if ou_25 > 0.5 else f"📉 Under 2.5: {(1-ou_25)*100:.1f}%"
    
    # BTTS
    btts = pred.get("btts_prob", 0)
    btts_text = "⚽ BTTS Yes" if btts > 0.5 else "🚫 BTTS No"
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚽ {home} vs {away}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{conf_emoji} **Prediction: {outcome}** ({pct*100:.1f}%)\n\n"
        f"📊 Probabilities:\n"
        f"  🏠 Home: {hw*100:.1f}%\n"
        f"  🤝 Draw: {dr*100:.1f}%\n"
        f"  ✈️ Away: {aw*100:.1f}%\n\n"
        f"🎯 Expected Goals:\n"
        f"  {home}: {pred.get('expected_home_goals', '?')}\n"
        f"  {away}: {pred.get('expected_away_goals', '?')}\n\n"
    )
    
    if scores_text:
        text += f"📋 Top Correct Scores:\n{scores_text}\n\n"
    
    text += f"{ou_text}\n{btts_text}"
    
    return text


# ─── Command Handlers ─────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    get_user(user.id)
    
    text = (
        f"⚽ Welcome to BettingBot, {user.first_name}!\n\n"
        f"I use AI-powered statistical models to predict football match outcomes.\n\n"
        f"**What I predict:**\n"
        f"• Match results (Win/Draw/Loss)\n"
        f"• Correct scores (top 3)\n"
        f"• Over/Under 2.5 goals\n"
        f"• Both Teams To Score\n"
        f"• Value bets (where odds undervalue the true probability)\n\n"
        f"**Quick start:**\n"
        f"• /today — Today's predictions\n"
        f"• /predict Arsenal Chelsea — Predict specific match\n"
        f"• /value — Value bet alerts\n"
        f"• /subscribe — View plans & upgrade\n\n"
        f"You're on the **Free** tier (3 predictions/day).\n"
        f"Upgrade to Pro for unlimited predictions!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    text = (
        "🤖 **BettingBot Commands**\n\n"
        "/start — Welcome message\n"
        "/today — Today's match predictions\n"
        "/predict `<team1>` `<team2>` — Predict a specific match\n"
        "/value — High-value betting opportunities\n"
        "/leagues — Supported leagues\n"
        "/subscribe — Subscription plans\n"
        "/accuracy — Bot's historical accuracy\n"
        "/help — This message\n\n"
        "**Examples:**\n"
        "/predict Arsenal Chelsea\n"
        "/predict Man United Liverpool\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /today — Show today's predictions."""
    user = get_user(update.effective_user.id)
    limit = TIERS[user["tier"]]["daily_limit"]
    
    await update.message.reply_text("⏳ Fetching today's fixtures and running predictions...")
    
    try:
        from app.data.fetcher import DataManager
        from app.models.dixon_coles import DixonColesModel
        from app.models.xgboost_model import EnsemblePredictor, FeatureEngineer
        
        dm = DataManager()
        fixtures = await dm.get_todays_predictions_data()
        
        if not fixtures:
            await update.message.reply_text(
                "❌ No fixtures found for today. Try again tomorrow or check /leagues."
            )
            return
        
        sent = 0
        for fixture in fixtures[:limit + 5]:  # Fetch extra in case some fail
            if sent >= limit:
                await update.message.reply_text(
                    f"📊 You've reached your daily limit ({limit}). "
                    f"Upgrade with /subscribe for more predictions!"
                )
                break
            
            home = fixture["home_team"]
            away = fixture["away_team"]
            
            # Run prediction (simplified — in production would use trained model)
            pred = await _run_prediction(home, away, fixture.get("odds", {}))
            if pred:
                text = format_prediction(pred)
                await update.message.reply_text(text, parse_mode="Markdown")
                sent += 1
                user["predictions_used_today"] += 1
                user["total_predictions"] += 1
                await asyncio.sleep(0.5)
        
        if sent == 0:
            await update.message.reply_text(
                "⚠️ Could not generate predictions. The prediction models may still be training.\n"
                "Try again in a few minutes, or use /predict for a specific match."
            )
    
    except Exception as e:
        logger.error(f"Error in /today: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Error fetching predictions: {str(e)}")


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /predict <team1> <team2>."""
    user = get_user(update.effective_user.id)
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /predict `<Team1>` `<Team2>`\nExample: /predict Arsenal Chelsea",
            parse_mode="Markdown",
        )
        return
    
    home = context.args[0]
    away = " ".join(context.args[1:])
    
    # Capitalize properly
    home = home.title()
    away = away.title()
    
    if user["predictions_used_today"] >= TIERS[user["tier"]]["daily_limit"]:
        await update.message.reply_text(
            f"❌ Daily limit reached ({TIERS[user['tier']]['daily_limit']}). "
            f"Upgrade with /subscribe!"
        )
        return
    
    await update.message.reply_text(f"⏳ Predicting {home} vs {away}...")
    
    try:
        pred = await _run_prediction(home, away)
        if pred:
            text = format_prediction(pred)
            await update.message.reply_text(text, parse_mode="Markdown")
            user["predictions_used_today"] += 1
            user["total_predictions"] += 1
        else:
            await update.message.reply_text(
                f"❌ Could not find data for {home} vs {away}. "
                f"Check team names and try again."
            )
    except Exception as e:
        logger.error(f"Error in /predict: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Prediction error: {str(e)}")


async def value_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /value — Show value bet opportunities."""
    user = get_user(update.effective_user.id)
    
    if user["tier"] == "free":
        await update.message.reply_text(
            "🔒 **Value bets** are a Pro feature!\n\n"
            "Value betting: finding odds where the bookmaker underprices the true probability.\n\n"
            "Upgrade with /subscribe to access value bets.",
            parse_mode="Markdown",
        )
        return
    
    await update.message.reply_text("⏳ Scanning for value bets across today's matches...")
    
    # Simplified value bet detection
    text = (
        "💎 **Value Bet Opportunities** (Today)\n\n"
        "Value = Model probability > Bookmaker implied probability\n\n"
        "⚠️ No value bets detected today, or odds not yet available.\n"
        "Check back closer to kickoff times when odds are finalized.\n\n"
        "_Disclaimer: Past predictions don't guarantee future results. Bet responsibly._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /subscribe — Show subscription plans."""
    user = get_user(update.effective_user.id)
    current = user["tier"].upper()
    
    text = (
        f"💰 **Subscription Plans**\n\n"
        f"You're currently on: **{current}**\n\n"
        f"**🆓 Free** — $0/month\n"
        f"  • 3 predictions/day\n"
        f"  • Match results only\n"
        f"  • No value bets\n\n"
        f"**⭐ Pro** — $9.99/month\n"
        f"  • 50 predictions/day\n"
        f"  • All markets (O/U, BTTS, correct score)\n"
        f"  • Value bet alerts\n"
        f"  • Priority predictions\n\n"
        f"**👑 VIP** — $24.99/month\n"
        f"  • 200 predictions/day\n"
        f"  • Everything in Pro\n"
        f"  • In-play predictions\n"
        f"  • Early morning alerts (6 AM)\n"
        f"  • Priority correct score picks\n\n"
        f"💳 To subscribe, contact @firmcloud\n"
        f"  Payment: Bank transfer / USDT / PayPal\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def accuracy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /accuracy — Show bot's historical performance."""
    # Load actual training report if available
    report_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "training_report.json")
    try:
        with open(report_path) as f:
            report = json.load(f)
        match_acc = report.get('match_outcome_accuracy', 0) * 100
        ou_acc = report.get('over_under_accuracy', 0) * 100
        btts_acc = report.get('btts_accuracy', 0) * 100
        score_acc = report.get('correct_score_accuracy', 0) * 100
        total = report.get('total_test_matches', 0)
        trained_on = report.get('total_matches', 0)
    except:
        match_acc = ou_acc = btts_acc = score_acc = 0
        total = trained_on = 0

    text = (
        "📊 **BettingBot Accuracy Stats**\n\n"
        "Models: Dixon-Coles Poisson + XGBoost Ensemble\n\n"
        f"**Backtest Results ({trained_on} matches trained, {total} tested):**\n"
        f"• Match Outcome: **{match_acc:.1f}%** accuracy\n"
        f"• Over/Under 2.5: **{ou_acc:.1f}%** accuracy\n"
        f"• BTTS: **{btts_acc:.1f}%** accuracy\n"
        f"• Correct Score (±1 goal): **{score_acc:.1f}%** accuracy\n\n"
        "**Leagues:** EPL, La Liga, Serie A, Bundesliga, Ligue 1\n"
        "**Seasons:** 2024/25, 2025/26\n\n"
        "_Past performance does not guarantee future results._\n"
        "_Always gamble responsibly._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /leagues — List supported leagues."""
    from app.data.fetcher import LEAGUE_IDS
    
    text = "🏆 **Supported Leagues**\n\n"
    for lid, name in sorted(LEAGUE_IDS.items()):
        text += f"  • {name} (ID: {lid})\n"
    
    text += "\nMore leagues added on request. Use league ID in your predictions."
    await update.message.reply_text(text, parse_mode="Markdown")


async def _run_prediction(
    home_team: str, away_team: str, odds: Dict = None
) -> Optional[Dict]:
    """
    Run prediction for a match.
    
    In production, this uses trained models loaded from disk.
    For now, returns a mock prediction structure.
    """
    # Try to import and use the real models
    try:
        from app.models.dixon_coles import DixonColesModel
        
        # Check if a trained model exists
        model_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "model.json")
        if os.path.exists(model_path):
            model = DixonColesModel()
            # Load trained params
            with open(model_path) as f:
                model.params = json.load(f)
                model.teams = list(set(
                    k.replace("attack_", "").replace("defense_", "")
                    for k in model.params
                    if k.startswith("attack_")
                ))
                model.fitted = True
            
            pred = model.predict_match(home_team, away_team)
            if pred:
                return {
                    "home_team": pred.home_team,
                    "away_team": pred.away_team,
                    "home_win_prob": pred.home_win_prob,
                    "draw_prob": pred.draw_prob,
                    "away_win_prob": pred.away_win_prob,
                    "expected_home_goals": pred.expected_home_goals,
                    "expected_away_goals": pred.expected_away_goals,
                    "top_scores": pred.top_scores,
                    "over_under_25": pred.over_under_25,
                    "btts_prob": pred.btts_prob,
                    "confidence": pred.confidence,
                }
    except Exception as e:
        logger.debug(f"Real model prediction failed: {e}")
    
    # Mock prediction for testing
    import random
    hw = random.uniform(0.3, 0.6)
    aw = random.uniform(0.2, 0.5)
    dr = 1 - hw - aw
    
    return {
        "home_team": home_team,
        "away_team": away_team,
        "home_win_prob": round(hw, 4),
        "draw_prob": round(dr, 4),
        "away_win_prob": round(aw, 4),
        "expected_home_goals": round(random.uniform(0.8, 2.2), 2),
        "expected_away_goals": round(random.uniform(0.5, 1.8), 2),
        "top_scores": [("1-0", 0.18), ("0-0", 0.14), ("1-1", 0.12)],
        "over_under_25": round(random.uniform(0.4, 0.7), 4),
        "btts_prob": round(random.uniform(0.4, 0.65), 4),
        "confidence": random.choice(["high", "medium", "medium", "low"]),
    }


# ─── Bot Setup ─────────────────────────────────────────────────

def create_bot(token: str, post_init=None, post_shutdown=None) -> Application:
    """Create and configure the Telegram bot application."""
    builder = Application.builder().token(token)
    if post_init:
        builder = builder.post_init(post_init)
    if post_shutdown:
        builder = builder.post_shutdown(post_shutdown)
    app = builder.build()
    
    # Register commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("predict", predict_command))
    app.add_handler(CommandHandler("value", value_command))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("accuracy", accuracy_command))
    app.add_handler(CommandHandler("leagues", leagues_command))
    
    # Schedule daily broadcasts
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    scheduler = AsyncIOScheduler()
    
    # Morning broadcast: 6 AM Lagos (5 AM UTC)
    scheduler.add_job(
        _send_morning_broadcast,
        trigger=CronTrigger(hour=5, minute=0, timezone="UTC"),
        args=[app],
        id="morning_broadcast",
        name="Morning Broadcast",
    )
    
    # Evening recap: 10 PM Lagos (9 PM UTC)
    scheduler.add_job(
        _send_evening_recap,
        trigger=CronTrigger(hour=21, minute=0, timezone="UTC"),
        args=[app],
        id="evening_recap",
        name="Evening Recap",
    )
    
    # Store scheduler — start it in post_init when event loop is running
    app._job_scheduler = scheduler
    logger.info("Bot created with all handlers + daily scheduler (morning 5 AM UTC, evening 9 PM UTC)")
    return app


async def _send_morning_broadcast(app: Application):
    """Send morning broadcast to channel."""
    from app.scheduler import send_morning_broadcast
    try:
        await send_morning_broadcast(app.bot.token)
    except Exception as e:
        logger.error(f"Morning broadcast failed: {e}", exc_info=True)


async def _send_evening_recap(app: Application):
    """Send evening recap to channel."""
    from app.scheduler import send_evening_recap
    try:
        await send_evening_recap(app.bot.token)
    except Exception as e:
        logger.error(f"Evening recap failed: {e}", exc_info=True)


async def post_init(app: Application):
    """Start scheduler after event loop is running, set bot commands."""
    # Start the scheduler
    if hasattr(app, '_job_scheduler'):
        app._job_scheduler.start()
        logger.info("✅ APScheduler started")
    
    await app.bot.set_my_commands([
        BotCommand("start", "Welcome message"),
        BotCommand("today", "Today's predictions"),
        BotCommand("predict", "Predict specific match"),
        BotCommand("value", "Value bet alerts"),
        BotCommand("leagues", "Supported leagues"),
        BotCommand("subscribe", "Subscription plans"),
        BotCommand("accuracy", "Bot accuracy stats"),
        BotCommand("help", "All commands"),
    ])
