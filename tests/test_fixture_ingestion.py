import asyncio
import tempfile
import unittest
from pathlib import Path

from app.data.ingestion import ingest_daily_fixtures
from app.data.storage import connect, loads_payload


class FakeFixtureProvider:
    name = "API-Football"

    def __init__(self, fixtures=None, error=None):
        self.fixtures = fixtures or []
        self.error = error
        self.calls = []

    async def get_upcoming_matches(self, hours_ahead=72):
        self.calls.append(hours_ahead)
        if self.error:
            raise self.error
        return list(self.fixtures)


def valid_fixture(**overrides):
    fixture = {
        "fixture_id": 123,
        "home_team": " Arsenal ",
        "away_team": "Chelsea",
        "date": "2026-05-20T12:00:00Z",
        "league_id": 39,
        "league_name": "Premier League",
        "status": "NS",
        "raw_payload": {"fixture": {"id": 123}, "teams": ["Arsenal", "Chelsea"]},
    }
    fixture.update(overrides)
    return fixture


class FixtureIngestionTests(unittest.TestCase):
    def test_first_run_inserts_fixtures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            provider = FakeFixtureProvider([valid_fixture()])

            counts = asyncio.run(ingest_daily_fixtures(provider=provider, db_path=str(db_path)))

            self.assertEqual({"inserted": 1, "updated": 0, "skipped": 0, "failed": 0}, counts)
            with connect(str(db_path)) as conn:
                row = conn.execute("SELECT * FROM fixtures").fetchone()
            self.assertEqual("api_football", row["provider"])
            self.assertEqual("123", row["provider_fixture_id"])
            self.assertEqual("Arsenal", row["home_team"])
            self.assertEqual("2026-05-20T12:00:00+00:00", row["kickoff_time"])
            self.assertEqual({"fixture": {"id": 123}, "teams": ["Arsenal", "Chelsea"]}, loads_payload(row["raw_payload"]))

    def test_second_run_updates_existing_fixture_without_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            first_provider = FakeFixtureProvider([valid_fixture(status="NS")])
            second_provider = FakeFixtureProvider([valid_fixture(status="TBD", date="2026-05-20T13:00:00+01:00")])

            first_counts = asyncio.run(ingest_daily_fixtures(provider=first_provider, db_path=str(db_path)))
            second_counts = asyncio.run(ingest_daily_fixtures(provider=second_provider, db_path=str(db_path)))

            self.assertEqual(1, first_counts["inserted"])
            self.assertEqual({"inserted": 0, "updated": 1, "skipped": 0, "failed": 0}, second_counts)
            with connect(str(db_path)) as conn:
                rows = conn.execute("SELECT * FROM fixtures").fetchall()
            self.assertEqual(1, len(rows))
            self.assertEqual("TBD", rows[0]["status"])
            self.assertEqual("2026-05-20T12:00:00+00:00", rows[0]["kickoff_time"])

    def test_malformed_fixture_is_skipped_and_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            provider = FakeFixtureProvider([valid_fixture(), {"fixture_id": 999, "home_team": "Missing Away"}])

            counts = asyncio.run(ingest_daily_fixtures(provider=provider, db_path=str(db_path)))

            self.assertEqual({"inserted": 1, "updated": 0, "skipped": 1, "failed": 0}, counts)
            with connect(str(db_path)) as conn:
                count = conn.execute("SELECT COUNT(*) AS count FROM fixtures").fetchone()["count"]
            self.assertEqual(1, count)

    def test_fixture_without_provider_id_gets_deterministic_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            provider = FakeFixtureProvider([
                {
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "date": "2026-05-20T12:00:00Z",
                    "league_name": "Premier League",
                }
            ])

            first_counts = asyncio.run(ingest_daily_fixtures(provider=provider, db_path=str(db_path)))
            second_counts = asyncio.run(ingest_daily_fixtures(provider=provider, db_path=str(db_path)))

            with connect(str(db_path)) as conn:
                rows = conn.execute("SELECT * FROM fixtures").fetchall()

            self.assertEqual(1, first_counts["inserted"])
            self.assertEqual(1, second_counts["updated"])
            self.assertEqual(1, len(rows))
            self.assertEqual("arsenal|chelsea|2026-05-20T12:00:00+00:00", rows[0]["provider_fixture_id"])

    def test_provider_failure_returns_failed_count_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            provider = FakeFixtureProvider(error=RuntimeError("provider unavailable"))

            counts = asyncio.run(ingest_daily_fixtures(provider=provider, db_path=str(db_path)))

            self.assertEqual({"inserted": 0, "updated": 0, "skipped": 0, "failed": 1}, counts)


if __name__ == "__main__":
    unittest.main()
