"""Automated Telegram channel broadcasts backed by stored FirmBetting data."""

import os
import asyncio
import logging
from datetime import datetime
from datetime import date as date_type
from typing import List, Optional

from telegram import Bot

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
    """Run the DB-backed prediction pipeline and send the daily picks."""
    bot = Bot(token=bot_token)

    if not CHANNEL_ID:
        logger.warning("TELEGRAM_CHANNEL not set, skipping broadcast")
        return []

    try:
        from app.broadcast import build_daily_prediction_broadcast, next_prediction_date
        from app.pipeline import run_daily_prediction_pipeline

        target_date = datetime.utcnow().date()
        counts = await run_daily_prediction_pipeline(target_date=None)
        logger.info("Daily prediction pipeline counts: %s", counts)

        broadcast_date = next_prediction_date(None, target_date, minimum_confidence="medium") or target_date
        messages = build_daily_prediction_broadcast(None, broadcast_date, minimum_confidence="medium")
        for message in messages:
            await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="Markdown")
            await asyncio.sleep(0.3)

        _set_last_broadcast_date(target_date.isoformat())
        logger.info("✅ Daily prediction broadcast sent: %s message(s)", len(messages))
        return messages
    except Exception as e:
        logger.error(f"Morning broadcast failed: {e}", exc_info=True)
        return []


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
    from app.pipeline import run_result_settlement_pipeline

    target_date = target_date or datetime.utcnow().date()
    counts = await run_result_settlement_pipeline(db_path=db_path)
    logger.info("Result settlement pipeline counts: %s", counts)

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
