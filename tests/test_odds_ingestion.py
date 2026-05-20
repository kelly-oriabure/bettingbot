import asyncio
import tempfile
import unittest
from pathlib import Path

from app.data.ingestion import ingest_daily_fixtures, ingest_daily_odds
from app.data.storage import connect
from tests.test_fixture_ingestion import FakeFixtureProvider, valid_fixture


class FakeOddsProvider:
    name = "The Odds API"

    def __init__(self, matches=None, api_keys=None, error=None, quota_metadata=None):
        self.matches = matches or []
        self.api_keys = api_keys if api_keys is not None else ["configured-key"]
        self.error = error
        self.quota_metadata = quota_metadata

    async def get_upcoming_matches(self, hours_ahead=72):
        if self.error:
            raise self.error
        return list(self.matches)


def odds_match(price=2.1):
    return {
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "date": "2026-05-20T12:00:00Z",
        "bookmakers": [
            {
                "key": "bet365",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Arsenal", "price": price},
                            {"name": "Draw", "price": 3.4},
                            {"name": "Chelsea", "price": 3.2},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.9},
                            {"name": "Under", "point": 2.5, "price": 1.95},
                        ],
                    },
                ],
            }
        ],
    }


class OddsIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "firmbetting.sqlite3"
        asyncio.run(
            ingest_daily_fixtures(
                provider=FakeFixtureProvider([valid_fixture()]),
                db_path=str(self.db_path),
            )
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_inserts_h2h_and_totals_snapshots(self):
        provider = FakeOddsProvider([odds_match()])

        counts = asyncio.run(
            ingest_daily_odds(
                provider=provider,
                db_path=str(self.db_path),
                captured_at="2026-05-20T08:00:00+00:00",
            )
        )

        self.assertEqual({"inserted": 5, "duplicates": 0, "skipped": 0, "failed": 0}, counts)
        with connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT market_type, selection, price FROM odds_snapshots ORDER BY market_type, selection"
            ).fetchall()
        self.assertEqual(
            [
                ("1x2", "away", 3.2),
                ("1x2", "draw", 3.4),
                ("1x2", "home", 2.1),
                ("over_under_2_5", "over", 1.9),
                ("over_under_2_5", "under", 1.95),
            ],
            [(row["market_type"], row["selection"], row["price"]) for row in rows],
        )

    def test_duplicate_provider_payload_does_not_create_duplicate_snapshots(self):
        provider = FakeOddsProvider([odds_match()])

        first_counts = asyncio.run(ingest_daily_odds(provider=provider, db_path=str(self.db_path)))
        second_counts = asyncio.run(ingest_daily_odds(provider=provider, db_path=str(self.db_path)))

        self.assertEqual(5, first_counts["inserted"])
        self.assertEqual({"inserted": 0, "duplicates": 5, "skipped": 0, "failed": 0}, second_counts)
        with connect(str(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM odds_snapshots").fetchone()["count"]
        self.assertEqual(5, count)

    def test_missing_odds_api_key_fails_safely(self):
        provider = FakeOddsProvider([odds_match()], api_keys=[])

        counts = asyncio.run(ingest_daily_odds(provider=provider, db_path=str(self.db_path)))

        self.assertEqual({"inserted": 0, "duplicates": 0, "skipped": 0, "failed": 1}, counts)

    def test_provider_failure_is_counted_without_crashing(self):
        provider = FakeOddsProvider(error=RuntimeError("rate limited"))

        counts = asyncio.run(ingest_daily_odds(provider=provider, db_path=str(self.db_path)))

        self.assertEqual({"inserted": 0, "duplicates": 0, "skipped": 0, "failed": 1}, counts)


if __name__ == "__main__":
    unittest.main()
