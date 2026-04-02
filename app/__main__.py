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
    import asyncio
    from app.bot.bot import create_bot
    from app.bot.health import start_health_server, set_bot_running

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your-telegram-bot-token-from-botfather":
        logger.error("TELEGRAM_BOT_TOKEN not set! Get one from @BotFather on Telegram.")
        sys.exit(1)

    # Start health check server for Coolify
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_health_server(8080))

    bot_app = create_bot(token)
    set_bot_running(True)
    logger.info("Starting BettingBot with health server...")
    bot_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
