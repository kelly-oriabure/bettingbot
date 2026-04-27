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
            if h > d and h > a: return f"🏠 {p['home_team']}", h
            elif a > d: return f"✈️ {p['away_team']}", a
            else: return "🤝 Draw", d

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
                f"⚽ **FirmBetting Predictions**\n📅 {now.strftime('%A, %B %d, %Y')}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n🏟️ No fixtures available right now.\n\n"
                f"📅 Check back tomorrow for fresh predictions!\n"
                f"🔔 Daily picks drop every morning at 6 AM.\n\n"
                f"⚠️ _Bet at your own risk. FirmBetting is not liable for any losses._"
            ), parse_mode="Markdown")
            _set_last_broadcast_date(now.strftime("%Y-%m-%d"))
            return

        # 6. Build enhanced broadcast
        msg = f"⚽ **FirmBetting Predictions**\n📅 {now.strftime('%A, %B %d, %Y')}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        if today_preds:
            msg += f"🏟️ **Today's Picks** ({len(today_preds)} matches)\n\n"
            for i, p in enumerate(today_preds[:10], 1):
                ce = {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(p["confidence"], "🟡")
                pk, pct = pick_a(p)
                vh, vd, va = val_ind(p["home_win_prob"], p["home_impl"]), val_ind(p["draw_prob"], p["draw_impl"]), val_ind(p["away_win_prob"], p["away_impl"])
                bt = "Yes" if p["btts_prob"] > 0.5 else "No"
                ou = "Over" if p["over_under_25"] > 0.5 else "Under"
                msg += (
                    f"**{i}. {p['home_team']} vs {p['away_team']}** | {p['league_name']} | {fmt_time(p['date'])}\n"
                    f"   {ce} Pick: **{pk}** ({pct * 100:.0f}%)\n"
                    f"   ┌─ 1X2: H{p['home_odds']} {vh} | D{p['draw_odds']} {vd} | A{p['away_odds']} {va}\n"
                    f"   ├─ BTTS: {bt} ({max(p['btts_prob'], 1-p['btts_prob'])*100:.0f}%) | O/U: {ou} ({max(p['over_under_25'], 1-p['over_under_25'])*100:.0f}%)\n"
                    f"   ├─ DC: 1X@{p['dc_1x']} | 12@{p['dc_12']} | X2@{p['dc_x2']}\n"
                    f"   └─ xG: {p['expected_home_goals']}–{p['expected_away_goals']}\n\n"
                )
        else:
            msg += "🏟️ **Today** — No matches today. Check early picks below!\n\n"

        if upcoming_preds:
            msg += f"🔥 **Early Value Picks** ({len(upcoming_preds)} upcoming)\n_Get these odds before they move!_\n\n"
            by_day = {}
            for p in upcoming_preds:
                d = fmt_day(p["date"])
                by_day.setdefault(d, []).append(p)
            for day, matches in list(by_day.items())[:5]:
                msg += f"**{day}**\n"
                for p in matches[:8]:
                    pk, pct = pick_a(p)
                    ce = {"high": "🟢", "medium": "🟡", "low": "⚪"}.get(p["confidence"], "🟡")
                    vh, vd, va = val_ind(p["home_win_prob"], p["home_impl"]), val_ind(p["draw_prob"], p["draw_impl"]), val_ind(p["away_win_prob"], p["away_impl"])
                    msg += (
                        f"  {fmt_time(p['date'])} **{p['home_team']} vs {p['away_team']}** ({p['league_name']})\n"
                        f"    {ce} {pk} ({pct*100:.0f}%) | H{p['home_odds']} {vh} | D{p['draw_odds']} {vd} | A{p['away_odds']} {va}\n"
                        f"    xG {p['expected_home_goals']}–{p['expected_away_goals']}\n\n"
                    )

        # Value bets
        vb = []
        for p in today_preds + upcoming_preds:
            for mt, mp, ip, od in [("Home", p["home_win_prob"], p["home_impl"], p["home_odds"]), ("Draw", p["draw_prob"], p["draw_impl"], p["draw_odds"]), ("Away", p["away_win_prob"], p["away_impl"], p["away_odds"]), ("Over 2.5", p["over_under_25"], p.get("over_impl", 0), p.get("over_odds", 0)), ("Under 2.5", 1-p["over_under_25"], p.get("under_impl", 0), p.get("under_odds", 0))]:
                if ip > 0 and mp > ip and (mp - ip) > 0.06 and mp > 0.55:
                    vb.append({"match": f"{p['home_team']} vs {p['away_team']}", "market": mt, "odds": od, "pct": round(mp*100), "edge": round((mp-ip)*100), "day": fmt_day(p["date"])})
        if vb:
            vb.sort(key=lambda x: x["edge"], reverse=True)
            msg += "🎯 **Best Value Bets**\n\n"
            for v in vb[:6]:
                msg += f"  🏆 **{v['match']}** ({v['day']}) → {v['market']} @{v['odds']} | Model: {v['pct']}% | Edge: +{v['edge']}%\n"

        msg += "\n━━━━━━━━━━━━━━━━━━━━━━\n⚠️ _Bet at your own risk. FirmBetting is not liable for any losses._\n"

        # Send — split if too long
        if len(msg) <= 4096:
            await bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        else:
            lines = msg.split("\n")
            mid = len(lines) // 2
            await bot.send_message(chat_id=CHANNEL_ID, text="\n".join(lines[:mid]) + "\n\n_(continued...)_", parse_mode="Markdown")
            await bot.send_message(chat_id=CHANNEL_ID, text="⚽ **(cont.)**\n\n" + "\n".join(lines[mid:]), parse_mode="Markdown")

        _set_last_broadcast_date(now.strftime("%Y-%m-%d"))
        logger.info(f"✅ Broadcast sent: {len(today_preds)} today, {len(upcoming_preds)} upcoming, {len(vb)} value bets")

    except Exception as e:
        logger.error(f"Morning broadcast failed: {e}", exc_info=True)
