import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.data.storage import dumps_payload, initialize_database, session


def insert_fixture(conn):
    cursor = conn.execute(
        """
        INSERT INTO fixtures (
            provider, provider_fixture_id, league_id, league_name, home_team,
            away_team, kickoff_time, status, raw_payload
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "api_football",
            "fixture-123",
            "39",
            "Premier League",
            "Arsenal",
            "Chelsea",
            "2026-05-20T12:00:00+00:00",
            "NS",
            dumps_payload({"fixture": {"id": 123}}),
        ),
    )
    return cursor.lastrowid


def insert_model_version(conn):
    cursor = conn.execute(
        """
        INSERT INTO model_versions (
            version, model_type, trained_from, trained_to, metrics, artifact_path
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "dc-2026-05-20",
            "dixon_coles",
            "2024-08-01",
            "2026-05-19",
            dumps_payload({"matches": 380}),
            "data/model.json",
        ),
    )
    return cursor.lastrowid


def insert_odds_snapshot(conn, fixture_id):
    cursor = conn.execute(
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
    )
    return cursor.lastrowid


def insert_prediction(conn, fixture_id, odds_snapshot_id, model_version_id):
    cursor = conn.execute(
        """
        INSERT INTO predictions (
            fixture_id, odds_snapshot_id, model_version_id, market_type,
            selection, probability, confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (fixture_id, odds_snapshot_id, model_version_id, "1x2", "home", 0.57, "medium"),
    )
    return cursor.lastrowid


class MvpSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "firmbetting.sqlite3"
        initialize_database(str(self.db_path))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fixture_provider_identity_is_unique(self):
        with session(str(self.db_path)) as conn:
            insert_fixture(conn)
            with self.assertRaises(sqlite3.IntegrityError):
                insert_fixture(conn)

    def test_odds_snapshot_links_to_fixture_and_identity_is_unique(self):
        with session(str(self.db_path)) as conn:
            fixture_id = insert_fixture(conn)
            odds_snapshot_id = insert_odds_snapshot(conn, fixture_id)
            odds = conn.execute("SELECT * FROM odds_snapshots WHERE id = ?", (odds_snapshot_id,)).fetchone()

            self.assertEqual(fixture_id, odds["fixture_id"])
            self.assertEqual("1x2", odds["market_type"])
            with self.assertRaises(sqlite3.IntegrityError):
                insert_odds_snapshot(conn, fixture_id)

    def test_prediction_links_fixture_model_version_and_odds_snapshot(self):
        with session(str(self.db_path)) as conn:
            fixture_id = insert_fixture(conn)
            odds_snapshot_id = insert_odds_snapshot(conn, fixture_id)
            model_version_id = insert_model_version(conn)
            prediction_id = insert_prediction(conn, fixture_id, odds_snapshot_id, model_version_id)

            prediction = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()

            self.assertEqual(fixture_id, prediction["fixture_id"])
            self.assertEqual(odds_snapshot_id, prediction["odds_snapshot_id"])
            self.assertEqual(model_version_id, prediction["model_version_id"])
            self.assertEqual("1x2", prediction["market_type"])
            self.assertEqual("home", prediction["selection"])
            self.assertEqual("medium", prediction["confidence"])

    def test_result_and_settlement_link_to_prediction_trace(self):
        with session(str(self.db_path)) as conn:
            fixture_id = insert_fixture(conn)
            odds_snapshot_id = insert_odds_snapshot(conn, fixture_id)
            model_version_id = insert_model_version(conn)
            prediction_id = insert_prediction(conn, fixture_id, odds_snapshot_id, model_version_id)
            conn.execute(
                """
                INSERT INTO results (
                    fixture_id, final_home_goals, final_away_goals, status,
                    completed_at, raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture_id,
                    2,
                    1,
                    "FT",
                    "2026-05-20T14:00:00+00:00",
                    dumps_payload({"score": {"fulltime": {"home": 2, "away": 1}}}),
                ),
            )
            conn.execute(
                """
                INSERT INTO settlements (
                    prediction_id, status, settled_outcome, reason
                )
                VALUES (?, ?, ?, ?)
                """,
                (prediction_id, "won", "home", "1x2 home selection matched final score"),
            )

            trace = conn.execute(
                """
                SELECT
                    f.provider_fixture_id,
                    p.market_type,
                    p.selection,
                    mv.version AS model_version,
                    os.id AS odds_snapshot_id,
                    r.final_home_goals,
                    r.final_away_goals,
                    s.status AS settlement_status
                FROM predictions p
                JOIN fixtures f ON f.id = p.fixture_id
                JOIN model_versions mv ON mv.id = p.model_version_id
                JOIN odds_snapshots os ON os.id = p.odds_snapshot_id
                JOIN results r ON r.fixture_id = f.id
                JOIN settlements s ON s.prediction_id = p.id
                WHERE p.id = ?
                """,
                (prediction_id,),
            ).fetchone()

            self.assertEqual("fixture-123", trace["provider_fixture_id"])
            self.assertEqual("1x2", trace["market_type"])
            self.assertEqual("dc-2026-05-20", trace["model_version"])
            self.assertEqual("won", trace["settlement_status"])

    def test_invalid_settlement_status_is_rejected(self):
        with session(str(self.db_path)) as conn:
            fixture_id = insert_fixture(conn)
            odds_snapshot_id = insert_odds_snapshot(conn, fixture_id)
            model_version_id = insert_model_version(conn)
            prediction_id = insert_prediction(conn, fixture_id, odds_snapshot_id, model_version_id)

            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO settlements (prediction_id, status, reason)
                    VALUES (?, ?, ?)
                    """,
                    (prediction_id, "refunded", "not an MVP settlement status"),
                )


if __name__ == "__main__":
    unittest.main()
