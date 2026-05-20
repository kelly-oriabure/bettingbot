import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.broadcast import build_result_comparison_broadcast
from app.data.storage import dumps_payload, initialize_database, session


def seed_settled_prediction(db_path, fixture_key, settlement_status, score=(2, 1), market_type="1x2", selection="home"):
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
                fixture_key,
                "Premier League",
                f"Home {fixture_key}",
                f"Away {fixture_key}",
                "2026-05-20T12:00:00+00:00",
                "FT",
                "{}",
            ),
        ).lastrowid
        model_version_id = conn.execute(
            "INSERT INTO model_versions (version, model_type, artifact_path) VALUES (?, ?, ?)",
            (f"dc-{fixture_key}", "dixon_coles", "data/model.json"),
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
            (fixture_id, odds_snapshot_id, model_version_id, market_type, selection, 0.6, "medium"),
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
                score[0],
                score[1],
                "FT",
                "2026-05-20T14:00:00+00:00",
                dumps_payload({"score": {"fulltime": {"home": score[0], "away": score[1]}}}),
            ),
        )
        conn.execute(
            "INSERT INTO settlements (prediction_id, status, settled_outcome, reason) VALUES (?, ?, ?, ?)",
            (prediction_id, settlement_status, selection, "test settlement"),
        )


class ResultBroadcastTests(unittest.TestCase):
    def test_won_and_lost_predictions_appear_with_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_settled_prediction(db_path, "won", "won")
            seed_settled_prediction(db_path, "lost", "lost", score=(0, 1))

            messages = build_result_comparison_broadcast(str(db_path), date(2026, 5, 20))
            text = "\n".join(messages)

            self.assertIn("Summary: 1 won / 1 lost | Sample size: 2 | Hit rate: 50.0%", text)
            self.assertIn("Home won 2-1 Away won", text)
            self.assertIn("Result: won", text)
            self.assertIn("Result: lost", text)

    def test_void_and_cancelled_are_separated_from_hit_rate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_settled_prediction(db_path, "won", "won")
            seed_settled_prediction(db_path, "void", "void")
            seed_settled_prediction(db_path, "cancelled", "cancelled")

            messages = build_result_comparison_broadcast(str(db_path), date(2026, 5, 20))
            text = "\n".join(messages)

            self.assertIn("Sample size: 1", text)
            self.assertIn("Hit rate: 100.0%", text)
            self.assertIn("Excluded from hit rate", text)
            self.assertIn("Result: void", text)
            self.assertIn("Result: cancelled", text)

    def test_pending_predictions_are_hidden_unless_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_settled_prediction(db_path, "pending", "pending")

            hidden = "\n".join(build_result_comparison_broadcast(str(db_path), date(2026, 5, 20)))
            shown = "\n".join(build_result_comparison_broadcast(str(db_path), date(2026, 5, 20), include_pending=True))

            self.assertIn("No settled results", hidden)
            self.assertIn("Result: pending", shown)

    def test_empty_settlement_day_produces_clear_no_results_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            initialize_database(str(db_path))

            messages = build_result_comparison_broadcast(str(db_path), date(2026, 5, 20))

            self.assertEqual(1, len(messages))
            self.assertIn("No settled results are available", messages[0])


if __name__ == "__main__":
    unittest.main()
