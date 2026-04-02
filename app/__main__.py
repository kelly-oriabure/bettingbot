"""
BettingBot - AI Football Prediction Telegram Bot
"""
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bettingbot")


def main():
    from app.bot.bot import create_bot

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your-telegram-bot-token-from-botfather":
        logger.error("TELEGRAM_BOT_TOKEN not set! Get one from @BotFather on Telegram.")
        sys.exit(1)

    bot_app = create_bot(token)
    logger.info("Starting BettingBot...")
    bot_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
