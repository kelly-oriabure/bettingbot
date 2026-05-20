import tempfile
import unittest
from pathlib import Path

from app.data.storage import connect, dumps_payload, initialize_database, session
from app.prediction import compute_confidence, eligible_predictions, store_prediction


def seed_fixture_model_and_odds(db_path, implied_probability=0.5):
    initialize_database(str(db_path))
    with session(str(db_path)) as conn:
        fixture_id = conn.execute(
            """
            INSERT INTO fixtures (
                provider, provider_fixture_id, league_name, home_team, away_team,
                kickoff_time, status, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("api_football", "123", "Premier League", "Arsenal", "Chelsea", "2026-05-20T12:00:00+00:00", "NS", "{}"),
        ).lastrowid
        model_version_id = conn.execute(
            "INSERT INTO model_versions (version, model_type, artifact_path) VALUES (?, ?, ?)",
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
                2.0,
                implied_probability,
                "2026-05-20T08:00:00+00:00",
                dumps_payload({"outcome": "home"}),
            ),
        ).lastrowid
    return fixture_id, model_version_id, odds_snapshot_id


class PredictionConfidenceTests(unittest.TestCase):
    def test_high_confidence_prediction_is_stored_and_eligible(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            fixture_id, model_version_id, odds_snapshot_id = seed_fixture_model_and_odds(db_path, implied_probability=0.5)

            prediction_id = store_prediction(
                str(db_path),
                fixture_id,
                model_version_id,
                "1x2",
                "home",
                0.64,
                odds_snapshot_id=odds_snapshot_id,
                minimum_probability=0.5,
            )
            eligible = eligible_predictions(str(db_path), market_types=["1x2"], minimum_confidence="medium")

            self.assertIsNotNone(prediction_id)
            self.assertEqual(1, len(eligible))
            self.assertEqual("high", eligible[0]["confidence"])

    def test_low_confidence_prediction_is_stored_but_filtered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            fixture_id, model_version_id, odds_snapshot_id = seed_fixture_model_and_odds(db_path, implied_probability=0.5)

            prediction_id = store_prediction(
                str(db_path),
                fixture_id,
                model_version_id,
                "1x2",
                "home",
                0.51,
                odds_snapshot_id=odds_snapshot_id,
            )
            medium_or_better = eligible_predictions(str(db_path), minimum_confidence="medium")

            self.assertIsNotNone(prediction_id)
            with connect(str(db_path)) as conn:
                row = conn.execute("SELECT confidence FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
            self.assertEqual("low", row["confidence"])
            self.assertEqual([], medium_or_better)

    def test_missing_odds_produces_conservative_confidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            fixture_id, model_version_id, _ = seed_fixture_model_and_odds(db_path)

            prediction_id = store_prediction(
                str(db_path),
                fixture_id,
                model_version_id,
                "btts",
                "yes",
                0.7,
                odds_snapshot_id=None,
            )

            with connect(str(db_path)) as conn:
                row = conn.execute("SELECT confidence FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
            self.assertEqual("low", row["confidence"])

    def test_confidence_values_are_deterministic_for_fixed_inputs(self):
        values = [
            compute_confidence(0.64, 0.5, 0.5),
            compute_confidence(0.55, 0.5, 0.5),
            compute_confidence(0.51, 0.5, 0.5),
            compute_confidence(0.7, None, 0.5),
            compute_confidence(0.49, 0.4, 0.5),
        ]

        self.assertEqual(["high", "medium", "low", "low", None], values)


if __name__ == "__main__":
    unittest.main()
