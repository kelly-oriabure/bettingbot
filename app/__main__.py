"""
BettingBot - AI Football Prediction Telegram Bot
"""
import os
import sys
import asyncio
import logging

# Load .env from project directory (before other imports that may read env vars)
from dotenv import load_dotenv, dotenv_values
_env_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
if os.path.exists(_env_path):
    _env_vals = dotenv_values(_env_path)
    for _k, _v in _env_vals.items():
        if _v:
            if _k not in os.environ or not os.environ[_k]:
                os.environ[_k] = _v

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bettingbot")


def main():
    import asyncio
    from app.bot.bot import create_bot, post_init, post_shutdown
    from app.bot.health import start_health_server, set_bot_running

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "your-telegram-bot-token-from-botfather":
        logger.error("TELEGRAM_BOT_TOKEN not set! Get one from @BotFather on Telegram.")
        sys.exit(1)

    # Start health check server for Coolify
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_health_server(8080))

    bot_app = create_bot(token, post_init=post_init, post_shutdown=post_shutdown)
    set_bot_running(True)
    logger.info("Starting BettingBot with health server...")
    bot_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
