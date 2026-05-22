import unittest
from datetime import datetime

from app.bot.bot import create_bot, _is_result_broadcast_due_utc


class BotSchedulerTests(unittest.TestCase):
    def test_result_comparison_broadcast_runs_at_1150pm_utc(self):
        app = create_bot("123:ABC")

        job = app._job_scheduler.get_job("result_comparison_broadcast")

        self.assertIsNotNone(job)
        self.assertEqual("cron[hour='23', minute='50']", str(job.trigger))

    def test_result_broadcast_catchup_due_after_1150pm_utc(self):
        self.assertFalse(_is_result_broadcast_due_utc(datetime(2026, 5, 22, 23, 49)))
        self.assertTrue(_is_result_broadcast_due_utc(datetime(2026, 5, 22, 23, 50)))


if __name__ == "__main__":
    unittest.main()
