import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.data.storage import initialize_database
from app.scheduler import send_result_comparison_broadcast
from tests.test_result_broadcast import seed_settled_prediction


class SchedulerResultBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def test_result_comparison_broadcast_sends_separate_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_settled_prediction(db_path, "won", "won")
            fake_bot = AsyncMock()

            with patch("app.scheduler.CHANNEL_ID", "@firmbetting"):
                with patch("app.scheduler.Bot", return_value=fake_bot):
                    messages = await send_result_comparison_broadcast(
                        "token",
                        target_date=date(2026, 5, 20),
                        db_path=str(db_path),
                    )

            self.assertEqual(1, len(messages))
            fake_bot.send_message.assert_awaited_once()
            _, kwargs = fake_bot.send_message.await_args
            self.assertEqual("@firmbetting", kwargs["chat_id"])
            self.assertIn("FirmBetting Results - 2026-05-20", kwargs["text"])
            self.assertIn("Result: won", kwargs["text"])

    async def test_result_comparison_broadcast_skips_when_channel_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            initialize_database(str(db_path))

            with patch("app.scheduler.CHANNEL_ID", ""):
                messages = await send_result_comparison_broadcast(
                    "token",
                    target_date=date(2026, 5, 20),
                    db_path=str(db_path),
                )

            self.assertEqual([], messages)


if __name__ == "__main__":
    unittest.main()
