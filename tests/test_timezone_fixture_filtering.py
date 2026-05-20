import asyncio
import unittest
from datetime import datetime, timezone

from app.data.fetcher import DataManager, parse_fixture_time


class FakeOddsProvider:
    name = "Fake Odds"

    def __init__(self, matches):
        self.matches = matches

    async def get_upcoming_matches(self, hours_ahead=24):
        return list(self.matches)

    def extract_odds(self, match):
        return {"home_implied_prob": 0.5}


def make_manager(matches):
    manager = DataManager.__new__(DataManager)
    manager.odds_provider = FakeOddsProvider(matches)
    manager._utc_now = lambda: datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
    return manager


class TimezoneFixtureFilteringTests(unittest.TestCase):
    def test_parse_fixture_time_normalizes_zulu_to_utc(self):
        parsed = parse_fixture_time("2026-05-20T12:00:00Z")

        self.assertEqual(datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc), parsed)

    def test_parse_fixture_time_normalizes_offset_to_utc(self):
        parsed = parse_fixture_time("2026-05-20T13:00:00+01:00")

        self.assertEqual(datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc), parsed)

    def test_parse_fixture_time_treats_naive_iso_as_utc(self):
        parsed = parse_fixture_time("2026-05-20T12:00:00")

        self.assertEqual(datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc), parsed)

    def test_upcoming_filter_includes_z_offset_and_naive_times_inside_window(self):
        matches = [
            {"home_team": "Zulu", "away_team": "Inside", "date": "2026-05-20T12:00:00Z"},
            {"home_team": "Offset", "away_team": "Inside", "date": "2026-05-20T13:00:00+01:00"},
            {"home_team": "Naive", "away_team": "Inside", "date": "2026-05-20T12:00:00"},
        ]
        manager = make_manager(matches)

        result = asyncio.run(manager.get_upcoming_matches(hours_ahead=24))

        self.assertEqual(["Zulu", "Offset", "Naive"], [match["home_team"] for match in result])
        self.assertTrue(all("odds" in match for match in result))

    def test_upcoming_filter_excludes_fixture_outside_window(self):
        manager = make_manager(
            [{"home_team": "Late", "away_team": "Outside", "date": "2026-05-22T12:00:00Z"}]
        )

        result = asyncio.run(manager.get_upcoming_matches(hours_ahead=24))

        self.assertEqual([], result)

    def test_today_filter_uses_same_timezone_safe_window(self):
        matches = [
            {"home_team": "Today", "away_team": "Inside", "date": "2026-05-20T13:00:00+01:00"},
            {"home_team": "Tomorrow", "away_team": "Outside", "date": "2026-05-21T12:01:00Z"},
        ]
        manager = make_manager(matches)

        result = asyncio.run(manager.get_todays_predictions_data())

        self.assertEqual(["Today"], [match["home_team"] for match in result])


if __name__ == "__main__":
    unittest.main()
