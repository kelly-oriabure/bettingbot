import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.data.storage import connect, dumps_payload, initialize_database, session
from app.settlement import settle_predictions


def seed_prediction(db_path, market_type, selection, home_goals=2, away_goals=1, result_status="FT", kickoff="2026-05-20T12:00:00+00:00"):
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
            ("api_football", f"{market_type}-{selection}", "Premier League", "Home", "Away", kickoff, result_status, "{}"),
        ).lastrowid
        model_version_id = conn.execute(
            "INSERT INTO model_versions (version, model_type, artifact_path) VALUES (?, ?, ?)",
            (f"model-{market_type}-{selection}", "dixon_coles", "data/model.json"),
        ).lastrowid
        odds_snapshot_id = conn.execute(
            """
            INSERT INTO odds_snapshots (
                fixture_id, provider, bookmaker, market_type, selection, price,
                implied_probability, captured_at, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_id, "odds_api", "bet365", market_type, selection, 2.0, 0.5, "2026-05-20T08:00:00+00:00", "{}"),
        ).lastrowid
        prediction_id = conn.execute(
            """
            INSERT INTO predictions (
                fixture_id, odds_snapshot_id, model_version_id, market_type,
                selection, probability, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_id, odds_snapshot_id, model_version_id, market_type, selection, 0.55, "medium"),
        ).lastrowid
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
                home_goals,
                away_goals,
                result_status,
                "2026-05-20T14:00:00+00:00" if result_status == "FT" else None,
                dumps_payload({"score": {"fulltime": {"home": home_goals, "away": away_goals}}}),
            ),
        )
    return prediction_id


def settlement_for(db_path, prediction_id):
    with connect(str(db_path)) as conn:
        return conn.execute("SELECT * FROM settlements WHERE prediction_id = ?", (prediction_id,)).fetchone()


class SettlementTests(unittest.TestCase):
    def test_1x2_home_draw_and_away_settle_correctly(self):
        cases = [
            ("home", 2, 1, "won"),
            ("draw", 1, 1, "won"),
            ("away", 0, 2, "won"),
            ("home", 0, 2, "lost"),
        ]
        for selection, home_goals, away_goals, expected_status in cases:
            with self.subTest(selection=selection, score=(home_goals, away_goals)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_path = Path(tmpdir) / "firmbetting.sqlite3"
                    prediction_id = seed_prediction(db_path, "1x2", selection, home_goals, away_goals)

                    counts = settle_predictions(str(db_path))
                    settlement = settlement_for(db_path, prediction_id)

                    self.assertEqual(1, counts[expected_status])
                    self.assertEqual(expected_status, settlement["status"])

    def test_double_chance_settles_correctly(self):
        cases = [
            ("1X", 1, 1, "won"),
            ("12", 2, 0, "won"),
            ("X2", 0, 1, "won"),
            ("1X", 0, 1, "lost"),
        ]
        for selection, home_goals, away_goals, expected_status in cases:
            with self.subTest(selection=selection):
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_path = Path(tmpdir) / "firmbetting.sqlite3"
                    prediction_id = seed_prediction(db_path, "double_chance", selection, home_goals, away_goals)

                    settle_predictions(str(db_path))
                    settlement = settlement_for(db_path, prediction_id)

                    self.assertEqual(expected_status, settlement["status"])

    def test_over_under_1_5_and_2_5_settle_at_boundaries(self):
        cases = [
            ("over_under_1_5", "over", 1, 1, "won"),
            ("over_under_1_5", "under", 1, 0, "won"),
            ("over_under_2_5", "over", 2, 1, "won"),
            ("over_under_2_5", "under", 1, 1, "won"),
            ("over_under_2_5", "over", 1, 1, "lost"),
        ]
        for market_type, selection, home_goals, away_goals, expected_status in cases:
            with self.subTest(market_type=market_type, selection=selection):
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_path = Path(tmpdir) / "firmbetting.sqlite3"
                    prediction_id = seed_prediction(db_path, market_type, selection, home_goals, away_goals)

                    settle_predictions(str(db_path))
                    settlement = settlement_for(db_path, prediction_id)

                    self.assertEqual(expected_status, settlement["status"])

    def test_btts_yes_no_settles_correctly(self):
        cases = [
            ("yes", 1, 1, "won"),
            ("no", 1, 0, "won"),
            ("yes", 2, 0, "lost"),
        ]
        for selection, home_goals, away_goals, expected_status in cases:
            with self.subTest(selection=selection):
                with tempfile.TemporaryDirectory() as tmpdir:
                    db_path = Path(tmpdir) / "firmbetting.sqlite3"
                    prediction_id = seed_prediction(db_path, "btts", selection, home_goals, away_goals)

                    settle_predictions(str(db_path))
                    settlement = settlement_for(db_path, prediction_id)

                    self.assertEqual(expected_status, settlement["status"])

    def test_match_not_completed_within_48_hours_settles_void(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            prediction_id = seed_prediction(
                db_path,
                "1x2",
                "home",
                home_goals=None,
                away_goals=None,
                result_status="PST",
                kickoff="2026-05-20T12:00:00+00:00",
            )

            settle_predictions(str(db_path), now=datetime(2026, 5, 23, 12, 1, tzinfo=timezone.utc))
            settlement = settlement_for(db_path, prediction_id)

            self.assertEqual("void", settlement["status"])

    def test_cancelled_or_invalid_fixture_state_creates_cancelled_settlement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            prediction_id = seed_prediction(
                db_path,
                "1x2",
                "home",
                home_goals=None,
                away_goals=None,
                result_status="CANC",
            )

            settle_predictions(str(db_path))
            settlement = settlement_for(db_path, prediction_id)

            self.assertEqual("cancelled", settlement["status"])


if __name__ == "__main__":
    unittest.main()
