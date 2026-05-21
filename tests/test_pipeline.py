import json
import tempfile
import unittest
from pathlib import Path

from app.data.storage import connect, dumps_payload, initialize_database, session
from app.pipeline import generate_stored_predictions


def write_model_artifact(path: Path):
    path.write_text(
        json.dumps(
            {
                "attack_Arsenal": 0.15,
                "defense_Arsenal": -0.05,
                "attack_Chelsea": 0.05,
                "defense_Chelsea": 0.02,
                "home_advantage": 0.25,
                "rho": -0.13,
            }
        )
    )


def seed_fixture_with_odds(db_path: Path):
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
            (
                "api_football",
                "pipeline-1",
                "Premier League",
                "Arsenal",
                "Chelsea",
                "2026-05-20T12:00:00+00:00",
                "NS",
                "{}",
            ),
        ).lastrowid
        conn.execute(
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
                3.0,
                0.3333,
                "2026-05-20T08:00:00+00:00",
                dumps_payload({"selection": "home"}),
            ),
        )
    return fixture_id


class PipelineTests(unittest.TestCase):
    def test_generate_stored_predictions_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            model_path = Path(tmpdir) / "model.json"
            write_model_artifact(model_path)
            seed_fixture_with_odds(db_path)

            first = generate_stored_predictions(
                db_path=str(db_path),
                model_path=str(model_path),
                minimum_probability=0.0,
            )
            second = generate_stored_predictions(
                db_path=str(db_path),
                model_path=str(model_path),
                minimum_probability=0.0,
            )

            with connect(str(db_path)) as conn:
                prediction_count = conn.execute("SELECT COUNT(*) AS count FROM predictions").fetchone()["count"]
                model_count = conn.execute("SELECT COUNT(*) AS count FROM model_versions").fetchone()["count"]

            self.assertGreater(first["inserted"], 0)
            self.assertEqual(0, second["inserted"])
            self.assertGreater(second["duplicates"], 0)
            self.assertEqual(first["inserted"], prediction_count)
            self.assertEqual(1, model_count)

    def test_missing_model_fails_safely_without_predictions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_fixture_with_odds(db_path)

            counts = generate_stored_predictions(
                db_path=str(db_path),
                model_path=str(Path(tmpdir) / "missing.json"),
            )

            with connect(str(db_path)) as conn:
                prediction_count = conn.execute("SELECT COUNT(*) AS count FROM predictions").fetchone()["count"]

            self.assertEqual(1, counts["failed"])
            self.assertEqual(0, prediction_count)


if __name__ == "__main__":
    unittest.main()
