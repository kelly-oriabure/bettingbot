"""
Automated channel broadcaster — runs multiple times daily.

Broadcasts to Telegram channel:
- Morning (6 AM Lagos): Today's fixtures + predictions + football news
- Half-time/Full-time: Live score updates
- Evening: Results recap + tomorrow preview

Rich content to attract football fans (not just bettors):
- All fixtures for the day
- League standings highlights
- Top scorer updates
- Hot takes / form analysis
"""

import os
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import Bot
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL", "")


async def send_morning_broadcast(bot_token: str):
    """Full morning broadcast: fixtures + predictions + football updates."""
    bot = Bot(token=bot_token)
    
    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL not set, skipping broadcast")
        return
    
    logger.info("Starting morning broadcast to channel...")
    
    try:
        from app.data.fetcher import DataManager
        from app.models.dixon_coles import DixonColesModel
        
        dm = DataManager()
        
        # 1. Get today's fixtures
        fixtures = await dm.get_todays_predictions_data()
        
        # 2. Load trained model
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
        
        # 3. Run predictions on all fixtures
        predictions = []
        if model and model.fitted:
            for fixture in fixtures:
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
                        "confidence": pred.confidence,
                    })
        
        # Sort by confidence
        predictions.sort(
            key=lambda p: max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"]),
            reverse=True,
        )
        
        # 4. Build broadcast message
        broadcast = _build_morning_broadcast(predictions, fixtures)
        
        # 5. Send to channel
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=broadcast,
            parse_mode="Markdown",
        )
        
        logger.info(f"✅ Morning broadcast sent: {len(predictions)} predictions, {len(fixtures)} fixtures")
        
        # 6. If there are many fixtures, send a second message with all fixtures
        if len(fixtures) > 10:
            fixtures_list = _build_fixtures_list(fixtures)
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=fixtures_list,
                parse_mode="Markdown",
            )
        
        # 7. Send top 3 "best bets" as a separate highlight
        if predictions:
            best_bets = _build_best_bets(predictions[:3])
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=best_bets,
                parse_mode="Markdown",
            )
        
    except Exception as e:
        logger.error(f"Morning broadcast failed: {e}", exc_info=True)


def _build_morning_broadcast(predictions: List[dict], fixtures: List[dict]) -> str:
    """Build the main morning broadcast message."""
    now = datetime.utcnow()
    
    # Header
    msg = (
        f"⚽ **{'Good Morning' if now.hour < 12 else 'Hello'} Football Fans!**\n"
        f"📅 {now.strftime('%A, %B %d, %Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Today's fixture count
    leagues = set()
    for f in fixtures:
        if f.get("league_name"):
            leagues.add(f["league_name"])
    
    msg += f"🏟️ **{len(fixtures)} matches** across {len(leagues)} leagues today\n"
    if leagues:
        msg += f"📋 {', '.join(sorted(leagues)[:5])}\n"
    msg += "\n"
    
    # Hot picks (top 5 predictions)
    msg += "🔥 **Top Predictions**\n\n"
    
    for i, pred in enumerate(predictions[:5], 1):
        home = pred["home_team"]
        away = pred["away_team"]
        hw = pred.get("home_win_prob", 0)
        dr = pred.get("draw_prob", 0)
        aw = pred.get("away_win_prob", 0)
        conf = pred.get("confidence", "medium")
        conf_emoji = {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(conf, "🟡")
        
        if hw > dr and hw > aw:
            pick = f"🏠 {home}"
            pct = hw
        elif aw > dr:
            pick = f"✈️ {away}"
            pct = aw
        else:
            pick = "🤝 Draw"
            pct = dr
        
        ou = "Over 2.5" if pred.get("over_under_25", 0) > 0.5 else "Under 2.5"
        btts = "BTTS ✅" if pred.get("btts_prob", 0) > 0.5 else "BTTS ❌"
        
        msg += (
            f"**{i}. {home} vs {away}**\n"
            f"   {conf_emoji} {pick} ({pct*100:.0f}%) | {ou} | {btts}\n"
        )
    
    # Expected goals highlights
    if predictions:
        highest_scoring = max(predictions, key=lambda p: p.get("expected_home_goals", 0) + p.get("expected_away_goals", 0))
        total_xg = highest_scoring.get("expected_home_goals", 0) + highest_scoring.get("expected_away_goals", 0)
        if total_xg > 2.5:
            msg += (
                f"\n💥 **Highest-scoring match:** {highest_scoring['home_team']} vs {highest_scoring['away_team']} "
                f"(xG: {total_xg:.1f} total)\n"
            )
    
    # Engagement hook
    msg += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Dixon-Coles AI Model | Updated {now.strftime('%H:%M')} UTC\n"
        f"💬 Reply with /predict TeamA TeamB for detailed analysis\n"
        f"🔔 Subscribe for alerts: @firm_bot_bettingbot\n"
        f"⚠️ For entertainment. Gamble responsibly.\n"
    )
    
    return msg


def _build_fixtures_list(fixtures: List[dict]) -> str:
    """Build a complete fixtures list for the day."""
    now = datetime.utcnow()
    
    msg = (
        f"📋 **All Today's Fixtures**\n"
        f"📅 {now.strftime('%B %d, %Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    # Group by league
    by_league = {}
    for f in fixtures:
        league = f.get("league_name", "Unknown")
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(f)
    
    for league, matches in sorted(by_league.items()):
        msg += f"**{league}**\n"
        for m in matches[:10]:  # Cap at 10 per league
            home = m.get("home_team", "?")
            away = m.get("away_team", "?")
            date = m.get("date", "")
            time_str = ""
            if date:
                try:
                    dt = datetime.fromisoformat(date.replace("Z", "+00:00"))
                    time_str = dt.strftime("%H:%M")
                except:
                    pass
            msg += f"  {time_str:>5}  {home} vs {away}\n"
        if len(matches) > 10:
            msg += f"  ... and {len(matches) - 10} more\n"
        msg += "\n"
    
    return msg


def _build_best_bets(predictions: List[dict]) -> str:
    """Build a 'best bets' highlight message."""
    msg = (
        f"💎 **Today's Best Bets**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for i, pred in enumerate(predictions, 1):
        home = pred["home_team"]
        away = pred["away_team"]
        hw = pred.get("home_win_prob", 0)
        dr = pred.get("draw_prob", 0)
        aw = pred.get("away_win_prob", 0)
        ou_25 = pred.get("over_under_25", 0)
        btts = pred.get("btts_prob", 0)
        xg_total = pred.get("expected_home_goals", 0) + pred.get("expected_away_goals", 0)
        
        # Determine strongest signal
        signals = []
        if hw > 0.55:
            signals.append(f"🏠 Home Win ({hw*100:.0f}%)")
        elif aw > 0.45:
            signals.append(f"✈️ Away Win ({aw*100:.0f}%)")
        elif dr > 0.30:
            signals.append(f"🤝 Draw ({dr*100:.0f}%)")
        
        if ou_25 > 0.65:
            signals.append(f"📈 Over 2.5 ({ou_25*100:.0f}%)")
        elif ou_25 < 0.35:
            signals.append(f"📉 Under 2.5 ({(1-ou_25)*100:.0f}%)")
        
        if btts > 0.65:
            signals.append(f"⚽ BTTS Yes ({btts*100:.0f}%)")
        
        msg += (
            f"**{i}. {home} vs {away}**\n"
            f"   {' | '.join(signals)}\n"
            f"   xG: {xg_total:.1f} total\n\n"
        )
    
    msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Higher confidence ≠ guaranteed. These are model probabilities only._\n"
    )
    
    return msg


async def send_evening_recap(bot_token: str):
    """Evening recap: today's results + performance review."""
    bot = Bot(token=bot_token)
    
    if not CHANNEL_ID:
        return
    
    logger.info("Sending evening recap...")
    
    try:
        from app.data.fetcher import DataManager
        
        dm = DataManager()
        today = datetime.utcnow().strftime("%Y-%m-%d")
        fixtures = await dm.api_football.get_fixtures_today()
        
        # Filter to completed matches
        completed = [f for f in fixtures if f.get("status") == "FT" or f.get("home_goals") is not None]
        
        if not completed:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text="📋 No completed matches yet for today's recap. Check back later!",
                parse_mode="Markdown",
            )
            return
        
        msg = (
            f"🌙 **Evening Recap**\n"
            f"📅 {datetime.utcnow().strftime('%B %d, %Y')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        for m in completed[:15]:
            home = m.get("home_team", "?")
            away = m.get("away_team", "?")
            hg = m.get("home_goals", 0)
            ag = m.get("away_goals", 0)
            
            if hg > ag:
                result = "🏠"
            elif ag > hg:
                result = "✈️"
            else:
                result = "🤝"
            
            msg += f"  {result} **{home} {hg}-{ag} {away}**\n"
        
        msg += (
            f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 How did your picks do? Share in the channel!\n"
            f"📈 See you tomorrow for more predictions.\n"
        )
        
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode="Markdown",
        )
        
        logger.info(f"✅ Evening recap sent: {len(completed)} results")
        
    except Exception as e:
        logger.error(f"Evening recap failed: {e}", exc_info=True)
