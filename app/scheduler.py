"""
Scheduled morning predictions sender.

Sends curated predictions via:
1. Telegram channel broadcast (all subscribers see it)
2. VIP user DMs (priority alerts)

Usage:
    Set TELEGRAM_CHANNEL env var to channel username (e.g. @BettingBotPicks)
    Integrated with the main bot's APScheduler at 5 AM UTC (6 AM Lagos).
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from telegram import Bot
from telegram.error import Forbidden, BadRequest

logger = logging.getLogger(__name__)

# Channel username — set via env var after creating the channel
# Can be @username or numeric channel ID (-100...)
CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL", "")


async def send_morning_predictions(bot_token: str, user_db: dict):
    """
    Send morning predictions:
    1. Broadcast to channel (all subscribers see it)
    2. DM VIP users with priority summary
    """
    bot = Bot(token=bot_token)
    
    logger.info("Generating morning predictions...")
    
    predictions = await _get_morning_predictions()
    
    if not predictions:
        logger.warning("No predictions generated for morning send")
        return
    
    # ── 1. Broadcast to channel ──
    channel_msg = _format_channel_broadcast(predictions)
    
    if CHANNEL_USERNAME:
        try:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=channel_msg,
                parse_mode="Markdown",
            )
            logger.info(f"✅ Channel broadcast sent to {CHANNEL_USERNAME}")
        except BadRequest as e:
            logger.error(f"Channel broadcast failed: {e}. Check TELEGRAM_CHANNEL env var.")
        except Exception as e:
            logger.error(f"Channel broadcast error: {e}")
    else:
        logger.warning("⚠️ TELEGRAM_CHANNEL not set — skipping channel broadcast")
    
    # ── 2. DM VIP users with priority picks ──
    sent_count = 0
    for user_id, user_data in user_db.items():
        tier = user_data.get("tier", "free")
        
        if tier != "vip":
            continue
        
        try:
            vip_picks = "\n".join(
                f"  ⚽ {p['home_team']} vs {p['away_team']} → "
                f"{'🏠' if p.get('home_win_prob',0) > max(p.get('draw_prob',0), p.get('away_win_prob',0)) else '✈️' if p.get('away_win_prob',0) > p.get('draw_prob',0) else '🤝'} "
                f"({max(p.get('home_win_prob',0), p.get('draw_prob',0), p.get('away_win_prob',0))*100:.0f}%)"
                for p in predictions[:5]
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"👑 **VIP Morning Picks**\n\n"
                    f"Full predictions in the channel:\n{CHANNEL_USERNAME or '@BettingBotPicks'}\n\n"
                    f"_Top 5 picks:_\n{vip_picks}\n\n"
                    f"💎 In-play alerts active."
                ),
                parse_mode="Markdown",
            )
            sent_count += 1
        except Forbidden:
            pass  # User blocked bot
        except Exception as e:
            logger.error(f"Failed to DM VIP {user_id}: {e}")
        
        await asyncio.sleep(0.05)
    
    logger.info(f"Morning broadcast: channel={bool(CHANNEL_USERNAME)}, VIP DMs={sent_count}")


def _format_channel_broadcast(predictions: List[dict]) -> str:
    """Format predictions for channel broadcast (clean, public)."""
    now = datetime.utcnow()
    
    msg = (
        f"⚽ **Daily Football Predictions**\n"
        f"📅 {now.strftime('%A, %B %d, %Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for i, pred in enumerate(predictions[:10], 1):
        home = pred["home_team"]
        away = pred["away_team"]
        hw = pred.get("home_win_prob", 0)
        dr = pred.get("draw_prob", 0)
        aw = pred.get("away_win_prob", 0)
        
        if hw > dr and hw > aw:
            pick, emoji = home, "🏠"
            pct = hw
        elif aw > dr:
            pick, emoji = away, "✈️"
            pct = aw
        else:
            pick, emoji = "Draw", "🤝"
            pct = dr
        
        ou = "O2.5" if pred.get("over_under_25", 0) > 0.5 else "U2.5"
        btts = "BTTS ✅" if pred.get("btts_prob", 0) > 0.5 else "BTTS ❌"
        
        msg += (
            f"**{i}. {home} vs {away}**\n"
            f"   {emoji} {pick} ({pct*100:.0f}%) | {ou} | {btts}\n\n"
        )
    
    msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Dixon-Coles Poisson Model\n"
        f"⚠️ For info only. Gamble responsibly.\n"
        f"💎 Upgrade: DM @firm_bot_bettingbot → /subscribe"
    )
    
    return msg


async def _get_morning_predictions() -> List[dict]:
    """Fetch today's fixtures and run predictions."""
    from app.data.fetcher import DataManager
    from app.models.dixon_coles import DixonColesModel
    
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
    
    # Sort by confidence
    predictions.sort(
        key=lambda p: max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"]),
        reverse=True,
    )
    
    return predictions
