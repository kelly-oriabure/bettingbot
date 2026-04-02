"""
Simple HTTP health check server for Coolify.

Runs alongside the Telegram bot to provide a health endpoint
that Coolify can ping for container health checks.
"""

import asyncio
import logging
from aiohttp import web

logger = logging.getLogger(__name__)

# Global health state
_health_status = {
    "status": "ok",
    "bot_running": False,
    "last_prediction": None,
}


def set_bot_running(running: bool = True):
    """Update bot running status."""
    _health_status["bot_running"] = running


def set_last_prediction(match: str = None):
    """Update last prediction timestamp."""
    _health_status["last_prediction"] = match


async def health_handler(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response(_health_status)


async def start_health_server(port: int = 8080) -> web.AppRunner:
    """Start a lightweight health check HTTP server."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health check server running on port {port}")
    except OSError as e:
        logger.warning(f"Health server could not start on port {port}: {e}")
    return runner
