import asyncio
import unittest
from unittest.mock import patch

import pandas as pd

from app.data.fetcher import DataManager
from app.train import fetch_data


class FakeFootballClient:
    def __init__(self, dataframe):
        self.dataframe = dataframe
        self.calls = []

    async def get_training_data(self, league_ids=None, seasons=None):
        self.calls.append((league_ids, seasons))
        return self.dataframe


class TrainingDataAccessTests(unittest.TestCase):
    def test_data_manager_delegates_training_data_to_api_football_client(self):
        expected = pd.DataFrame(
            [{"home_team": "Arsenal", "away_team": "Chelsea", "home_goals": 2, "away_goals": 1}]
        )
        client = FakeFootballClient(expected)
        manager = DataManager.__new__(DataManager)
        manager.api_football = client

        result = asyncio.run(manager.get_training_data([39], [2024]))

        self.assertIs(result, expected)
        self.assertEqual([([39], [2024])], client.calls)

    def test_fetch_data_uses_data_manager_training_path(self):
        expected = pd.DataFrame(
            [{"home_team": "Liverpool", "away_team": "Everton", "home_goals": 1, "away_goals": 0}]
        )
        manager = unittest.mock.AsyncMock()
        manager.get_training_data.return_value = expected

        with patch("app.data.fetcher.DataManager", return_value=manager):
            result = asyncio.run(fetch_data([39], [2024]))

        self.assertIs(result, expected)
        manager.get_training_data.assert_awaited_once_with([39], [2024])

    def test_fetch_data_exits_clearly_when_historical_data_is_empty(self):
        manager = unittest.mock.AsyncMock()
        manager.get_training_data.return_value = pd.DataFrame()

        with patch("app.data.fetcher.DataManager", return_value=manager):
            with self.assertLogs("train", level="ERROR") as logs:
                with self.assertRaises(SystemExit) as exc:
                    asyncio.run(fetch_data([39], [2024]))

        self.assertEqual(1, exc.exception.code)
        self.assertIn("No data fetched", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
