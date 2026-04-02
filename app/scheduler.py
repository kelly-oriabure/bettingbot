"""
Scheduled morning predictions sender.

Sends curated predictions to subscribed users at 6 AM (Africa/Lagos time).
This module is called by the scheduler or cron job.

Usage:
    python -m app.scheduler

Or integrate with the main bot's APScheduler.
"""

import os
import asyncio
import logging
from datetime import datetime

from telegram import Bot
from telegram.error import Forbidden

logger = logging.getLogger(__name__)

# Lagos is UTC+1, so 6 AM Lagos = 5 AM UTC
MORNING_HOUR_UTC = 5


async def send_morning_predictions(bot_token: str, user_db: dict):
    """
    Send morning predictions to all subscribed users.
    
    Args:
        bot_token: Telegram bot token
        user_db: Dict of {user_id: user_data} (from bot.py USERS dict)
    """
    bot = Bot(token=bot_token)
    
    logger.info("Generating morning predictions...")
    
    # Get today's fixtures and run predictions
    predictions = await _get_morning_predictions()
    
    if not predictions:
        logger.warning("No predictions generated for morning send")
        return
    
    # Build the morning message
    header = (
        "🌅 **Good Morning! Here are today's picks**\n\n"
        f"📅 {datetime.utcnow().strftime('%A, %B %d, %Y')}\n"
        f"⚽ {len(predictions)} matches with predictions\n\n"
    )
    
    sent_count = 0
    failed_count = 0
    
    for user_id, user_data in user_db.items():
        tier = user_data.get("tier", "free")
        
        # Free users get a preview, subs get full details
        if tier == "free":
            # Send teaser to free users (drive upsell)
            msg = (
                f"🌅 Good morning! {len(predictions)} matches today.\n\n"
                f"Preview (top 3):\n"
            )
            for pred in predictions[:3]:
                msg += _format_short(pred)
            msg += (
                f"\n📊 Get all {len(predictions)} predictions + value bets!\n"
                f"Upgrade: /subscribe"
            )
        else:
            msg = header
            limit = {"pro": 50, "vip": 200}.get(tier, 3)
            for pred in predictions[:limit]:
                msg += _format_short(pred)
            
            if tier == "vip":
                msg += "\n\n💎 VIP: In-play alerts enabled for all matches."
        
        try:
            await bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode="Markdown",
            )
            sent_count += 1
        except Forbidden:
            logger.info(f"User {user_id} blocked the bot, skipping")
            failed_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {user_id}: {e}")
            failed_count += 1
        
        # Rate limit: ~30 msgs/sec for bots
        await asyncio.sleep(0.05)
    
    logger.info(f"Morning predictions sent: {sent_count} success, {failed_count} failed")


def _format_short(pred: dict) -> str:
    """Short format for morning digest."""
    hw = pred.get("home_win_prob", 0)
    dr = pred.get("draw_prob", 0)
    aw = pred.get("away_win_prob", 0)
    
    if hw > dr and hw > aw:
        pick = f"🏠 {pred['home_team']}"
        pct = hw
    elif aw > dr:
        pick = f"✈️ {pred['away_team']}"
        pct = aw
    else:
        pick = "🤝 Draw"
        pct = dr
    
    return (
        f"  ⚽ {pred['home_team']} vs {pred['away_team']}\n"
        f"    → {pick} ({pct*100:.0f}%) | "
        f"O/U2.5: {'Over' if pred.get('over_under_25', 0) > 0.5 else 'Under'}\n"
    )


async def _get_morning_predictions() -> list:
    """Fetch today's fixtures and run predictions."""
    from app.data.fetcher import DataManager
    from app.models.dixon_coles import DixonColesModel
    import json
    
    dm = DataManager()
    fixtures = await dm.get_todays_predictions_data()
    
    predictions = []
    model_path = os.path.join(os.path.dirname(__file__), "..", "data", "model.json")
    
    model = None
    if os.path.exists(model_path):
        model = DixonColesModel()
        with open(model_path) as f:
            model.params = json.load(f)
        model.teams = list(set(
            k.replace("attack_", "").replace("defense_", "")
            for k in model.params if k.startswith("attack_")
        ))
        model.fitted = True
    
    for fixture in fixtures:
        if not model or not model.fitted:
            break
        
        pred = model.predict_match(fixture["home_team"], fixture["away_team"])
        if pred:
            predictions.append({
                "home_team": pred.home_team,
                "away_team": pred.away_team,
                "home_win_prob": pred.home_win_prob,
                "draw_prob": pred.draw_prob,
                "away_win_prob": pred.away_win_prob,
                "expected_home_goals": pred.expected_home_goals,
                "expected_away_goals": pred.expected_away_goals,
                "over_under_25": pred.over_under_25,
                "btts_prob": pred.btts_prob,
            })
    
    # Sort by confidence (highest first)
    predictions.sort(
        key=lambda p: max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"]),
        reverse=True,
    )
    
    return predictions
