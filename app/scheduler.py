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
from datetime import date as date_type
from typing import Dict, List, Optional

from telegram import Bot
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL", "")
_STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "broadcast_state.json")


def _get_last_broadcast_date() -> str:
    """Get the date of the last successful broadcast."""
    try:
        if os.path.exists(_STATE_FILE):
            import json
            with open(_STATE_FILE) as f:
                return json.load(f).get("last_broadcast", "")
    except Exception:
        pass
    return ""


def _set_last_broadcast_date(date_str: str):
    """Record the date of a successful broadcast."""
    try:
        import json
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump({"last_broadcast": date_str}, f)
    except Exception:
        pass


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

        # 1. Get fixtures for next 72h (today + upcoming)
        all_fixtures = await dm.get_upcoming_matches(hours_ahead=72)

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

        if not model or not model.fitted:
            logger.error("Model not loaded — skipping broadcast")
            return

        # 3. Split into today (0-24h) and upcoming (24-72h)
        now = datetime.utcnow()
        t24 = now + timedelta(hours=24)
        today_fix = []
        upcoming_fix = []
        for f in all_fixtures:
            try:
                dt = datetime.fromisoformat(f["date"].replace("Z", "+00:00")).replace(tzinfo=None)
                if now <= dt <= t24:
                    today_fix.append(f)
                elif t24 < dt <= now + timedelta(hours=72):
                    upcoming_fix.append(f)
            except:
                pass

        logger.info(f"Today: {len(today_fix)} | Upcoming 48-72h: {len(upcoming_fix)}")

        # 4. Helper functions for odds extraction and formatting
        def extract_1x2(fixture):
            hp, dp, ap = [], [], []
            for bk in fixture.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk["key"] == "h2h":
                        for o in mk["outcomes"]:
                            if o["name"] == fixture["home_team"]:
                                hp.append(1 / o["price"])
                            elif o["name"] == fixture["away_team"]:
                                ap.append(1 / o["price"])
                            elif o["name"] == "Draw":
                                dp.append(1 / o["price"])
            if not hp:
                return None
            return {
                "home_odds": round(1 / (sum(hp) / len(hp)), 2),
                "draw_odds": round(1 / (sum(dp) / len(dp)), 2) if dp else 0,
                "away_odds": round(1 / (sum(ap) / len(ap)), 2) if ap else 0,
                "home_impl": round(sum(hp) / len(hp), 4),
                "draw_impl": round(sum(dp) / len(dp), 4) if dp else 0,
                "away_impl": round(sum(ap) / len(ap), 4) if ap else 0,
            }

        def extract_totals(fixture):
            ov, un = [], []
            for bk in fixture.get("bookmakers", []):
                for mk in bk.get("markets", []):
                    if mk["key"] == "totals":
                        for o in mk["outcomes"]:
                            if o.get("point") == 2.5:
                                if "Over" in o["name"]:
                                    ov.append(1 / o["price"])
                                elif "Under" in o["name"]:
                                    un.append(1 / o["price"])
            if not ov:
                return None
            return {
                "over_odds": round(1 / (sum(ov) / len(ov)), 2),
                "under_odds": round(1 / (sum(un) / len(un)), 2),
                "over_impl": round(sum(ov) / len(ov), 4),
                "under_impl": round(sum(un) / len(un), 4),
            }

        def fmt_time(d):
            try:
                return (datetime.fromisoformat(d.replace("Z", "+00:00")) + timedelta(hours=1)).strftime("%a %H:%M")
            except:
                return "TBD"

        def fmt_day(d):
            try:
                return (datetime.fromisoformat(d.replace("Z", "+00:00")) + timedelta(hours=1)).strftime("%a %b %d")
            except:
                return "TBD"

        def val_ind(mp, ip):
            e = (mp - ip) * 100
            if e > 8: return f"✅+{e:.0f}%"
            elif e > 3: return f"⚡+{e:.0f}%"
            elif e > -3: return "—"
            else: return f"❌{e:.0f}%"

        def pick_a(p):
            h, d, a = p["home_win_prob"], p["draw_prob"], p["away_win_prob"]
            if h > d and h > a: return f"{p['home_team']} to win", h
            elif a > d: return f"{p['away_team']} to win", a
            else: return "Draw", d

        def simple_reason(confidence):
            if confidence == "high":
                return "This is one of today's stronger picks."
            if confidence == "medium":
                return "This pick has enough support to make the shortlist."
            return "This pick is included, but stake carefully."

        # 5. Build predictions with odds
        def build_preds(fixtures):
            results = []
            for fix in fixtures:
                o1x2 = extract_1x2(fix)
                if not o1x2:
                    continue
                pred = model.predict_match(fix["home_team"], fix["away_team"])
                if not pred:
                    continue
                tot = extract_totals(fix) or {"over_odds": 0, "under_odds": 0, "over_impl": 0, "under_impl": 0}
                ho, do, ao = o1x2["home_odds"], o1x2["draw_odds"], o1x2["away_odds"]
                results.append({
                    "home_team": pred.home_team, "away_team": pred.away_team,
                    "home_win_prob": pred.home_win_prob, "draw_prob": pred.draw_prob,
                    "away_win_prob": pred.away_win_prob,
                    "expected_home_goals": pred.expected_home_goals,
                    "expected_away_goals": pred.expected_away_goals,
                    "over_under_25": pred.over_under_25, "btts_prob": pred.btts_prob,
                    "confidence": pred.confidence,
                    **o1x2, **tot,
                    "league_name": fix.get("league_name", ""),
                    "date": fix.get("date", ""),
                    "dc_1x": round(1 / (1 / ho + 1 / do), 2) if ho and do else 0,
                    "dc_12": round(1 / (1 / ho + 1 / ao), 2) if ho and ao else 0,
                    "dc_x2": round(1 / (1 / do + 1 / ao), 2) if do and ao else 0,
                })
            results.sort(key=lambda p: max(p["home_win_prob"], p["draw_prob"], p["away_win_prob"]), reverse=True)
            return results

        today_preds = build_preds(today_fix)
        upcoming_preds = build_preds(upcoming_fix)

        # No matches at all
        if not today_preds and not upcoming_preds:
            await bot.send_message(chat_id=CHANNEL_ID, text=(
                f"FirmBetting Daily Picks\n{now.strftime('%A, %B %d, %Y')}\n\n"
                f"No eligible picks are available right now.\n\n"
                f"No prediction is guaranteed. Bet responsibly."
            ))
            _set_last_broadcast_date(now.strftime("%Y-%m-%d"))
            return

        # 6. Build a simple public broadcast. Technical details stay in storage/logs.
        total_picks = len(today_preds) + len(upcoming_preds)
        high_count = sum(1 for p in today_preds + upcoming_preds if p["confidence"] == "high")
        medium_count = sum(1 for p in today_preds + upcoming_preds if p["confidence"] == "medium")
        msg = (
            f"FirmBetting Daily Picks\n{now.strftime('%A, %B %d, %Y')}\n\n"
            f"Today's shortlist: {total_picks} pick(s)\n"
            f"High confidence: {high_count} | Medium confidence: {medium_count}\n\n"
        )

        if today_preds:
            msg += f"Today's Picks ({len(today_preds)})\n\n"
            for i, p in enumerate(today_preds[:10], 1):
                pk, pct = pick_a(p)
                msg += (
                    f"{i}. {p['home_team']} vs {p['away_team']}\n"
                    f"League: {p['league_name'] or 'Unknown league'} | Kickoff: {fmt_time(p['date'])}\n"
                    f"Prediction: {pk}\n"
                    f"Confidence: {p['confidence'].title()}\n"
                    f"Why: {simple_reason(p['confidence'])}\n\n"
                )
        else:
            msg += "No eligible picks for today. Check early picks below.\n\n"

        if upcoming_preds:
            msg += f"Early Picks ({len(upcoming_preds)} upcoming)\n\n"
            by_day = {}
            for p in upcoming_preds:
                d = fmt_day(p["date"])
                by_day.setdefault(d, []).append(p)
            for day, matches in list(by_day.items())[:5]:
                msg += f"{day}\n"
                for p in matches[:8]:
                    pk, pct = pick_a(p)
                    msg += (
                        f"{fmt_time(p['date'])} | {p['home_team']} vs {p['away_team']}\n"
                        f"Prediction: {pk}\n"
                        f"Confidence: {p['confidence'].title()}\n\n"
                    )

        msg += "\nReminder:\nNo prediction is guaranteed. Bet responsibly."

        # Send — split if too long
        if len(msg) <= 4096:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg)
        else:
            lines = msg.split("\n")
            mid = len(lines) // 2
            await bot.send_message(chat_id=CHANNEL_ID, text="\n".join(lines[:mid]) + "\n\n(continued...)")
            await bot.send_message(chat_id=CHANNEL_ID, text="FirmBetting Daily Picks (continued)\n\n" + "\n".join(lines[mid:]))

        _set_last_broadcast_date(now.strftime("%Y-%m-%d"))
        logger.info("✅ Broadcast sent: %s today, %s upcoming", len(today_preds), len(upcoming_preds))

    except Exception as e:
        logger.error(f"Morning broadcast failed: {e}", exc_info=True)


async def send_result_comparison_broadcast(
    bot_token: str,
    target_date: Optional[date_type] = None,
    db_path: Optional[str] = None,
) -> List[str]:
    """Send the separate prediction-vs-result comparison broadcast."""
    bot = Bot(token=bot_token)

    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL not set, skipping result comparison broadcast")
        return []

    from app.broadcast import build_result_comparison_broadcast

    target_date = target_date or datetime.utcnow().date()
    messages = build_result_comparison_broadcast(db_path, target_date)
    for message in messages:
        await bot.send_message(chat_id=CHANNEL_ID, text=message)
        await asyncio.sleep(0.3)

    _set_last_broadcast_date(f"{target_date.isoformat()}_results")
    logger.info("✅ Result comparison broadcast sent: %s message(s)", len(messages))
    return messages


async def send_evening_recap(bot_token: str):
    """Backward-compatible evening job name for result-comparison broadcast."""
    return await send_result_comparison_broadcast(bot_token)
