import asyncio
import tempfile
import unittest
from pathlib import Path

from app.data.ingestion import ingest_daily_fixtures, ingest_results
from app.data.storage import connect, dumps_payload, loads_payload, session
from tests.test_fixture_ingestion import FakeFixtureProvider, valid_fixture


class FakeResultProvider:
    def __init__(self, results):
        self.results = results
        self.requested_fixtures = []

    async def get_results(self, fixtures):
        self.requested_fixtures = fixtures
        return list(self.results)


def api_football_result(status="FT", home_goals=2, away_goals=1, completed_at="2026-05-20T14:00:00Z"):
    return {
        "fixture": {
            "id": 123,
            "date": "2026-05-20T12:00:00Z",
            "status": {"short": status},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "completed_at": completed_at,
    }


def seed_predicted_fixture(db_path):
    asyncio.run(
        ingest_daily_fixtures(
            provider=FakeFixtureProvider([valid_fixture()]),
            db_path=str(db_path),
        )
    )
    with session(str(db_path)) as conn:
        fixture_id = conn.execute("SELECT id FROM fixtures").fetchone()["id"]
        model_version_id = conn.execute(
            """
            INSERT INTO model_versions (version, model_type, artifact_path)
            VALUES (?, ?, ?)
            """,
            ("dc-test", "dixon_coles", "data/model.json"),
        ).lastrowid
        odds_snapshot_id = conn.execute(
            """
            INSERT INTO odds_snapshots (
                fixture_id, provider, bookmaker, market_type, selection, price,
                implied_probability, captured_at, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                "odds_api",
                "bet365",
                "1x2",
                "home",
                2.1,
                0.4762,
                "2026-05-20T08:00:00+00:00",
                dumps_payload({"markets": ["h2h"]}),
            ),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO predictions (
                fixture_id, odds_snapshot_id, model_version_id, market_type,
                selection, probability, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_id, odds_snapshot_id, model_version_id, "1x2", "home", 0.57, "medium"),
        )
    return fixture_id


class ResultIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "firmbetting.sqlite3"
        self.fixture_id = seed_predicted_fixture(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_completed_fixture_stores_final_score(self):
        provider = FakeResultProvider([api_football_result()])

        counts = asyncio.run(ingest_results(provider=provider, db_path=str(self.db_path)))

        self.assertEqual({"inserted": 1, "updated": 0, "pending": 0, "skipped": 0, "failed": 0}, counts)
        with connect(str(self.db_path)) as conn:
            result = conn.execute("SELECT * FROM results WHERE fixture_id = ?", (self.fixture_id,)).fetchone()
            fixture = conn.execute("SELECT * FROM fixtures WHERE id = ?", (self.fixture_id,)).fetchone()
        self.assertEqual(2, result["final_home_goals"])
        self.assertEqual(1, result["final_away_goals"])
        self.assertEqual("FT", result["status"])
        self.assertEqual("2026-05-20T14:00:00+00:00", result["completed_at"])
        self.assertEqual("FT", fixture["status"])

    def test_pending_fixture_remains_unsettled(self):
        provider = FakeResultProvider([api_football_result(status="NS", home_goals=None, away_goals=None, completed_at=None)])

        counts = asyncio.run(ingest_results(provider=provider, db_path=str(self.db_path)))

        self.assertEqual({"inserted": 1, "updated": 0, "pending": 1, "skipped": 0, "failed": 0}, counts)
        with connect(str(self.db_path)) as conn:
            result = conn.execute("SELECT * FROM results WHERE fixture_id = ?", (self.fixture_id,)).fetchone()
            settlements = conn.execute("SELECT COUNT(*) AS count FROM settlements").fetchone()["count"]
        self.assertEqual("NS", result["status"])
        self.assertIsNone(result["final_home_goals"])
        self.assertEqual(0, settlements)

    def test_postponed_fixture_stores_status_and_kickoff_reference(self):
        provider = FakeResultProvider([api_football_result(status="PST", home_goals=None, away_goals=None, completed_at=None)])

        counts = asyncio.run(ingest_results(provider=provider, db_path=str(self.db_path)))

        self.assertEqual(1, counts["pending"])
        with connect(str(self.db_path)) as conn:
            result = conn.execute("SELECT * FROM results WHERE fixture_id = ?", (self.fixture_id,)).fetchone()
        raw_payload = loads_payload(result["raw_payload"])
        self.assertEqual("PST", result["status"])
        self.assertEqual("2026-05-20T12:00:00Z", raw_payload["fixture"]["date"])

    def test_rerun_updates_existing_result_without_duplicate(self):
        first_provider = FakeResultProvider([api_football_result(status="NS", home_goals=None, away_goals=None, completed_at=None)])
        second_provider = FakeResultProvider([api_football_result(status="FT", home_goals=3, away_goals=0)])

        first_counts = asyncio.run(ingest_results(provider=first_provider, db_path=str(self.db_path)))
        second_counts = asyncio.run(ingest_results(provider=second_provider, db_path=str(self.db_path)))

        self.assertEqual(1, first_counts["inserted"])
        self.assertEqual({"inserted": 0, "updated": 1, "pending": 0, "skipped": 0, "failed": 0}, second_counts)
        with connect(str(self.db_path)) as conn:
            rows = conn.execute("SELECT * FROM results").fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("FT", rows[0]["status"])
        self.assertEqual(3, rows[0]["final_home_goals"])


if __name__ == "__main__":
    unittest.main()
