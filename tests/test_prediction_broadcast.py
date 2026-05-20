import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.broadcast import TELEGRAM_SAFE_LIMIT, build_daily_prediction_broadcast, split_telegram_message
from app.data.storage import dumps_payload, initialize_database, session
from app.prediction import store_prediction


def seed_prediction(db_path, fixture_key, kickoff_time, probability, implied_probability, market_type="1x2", selection="home"):
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
                kickoff_time,
                "NS",
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
            (
                fixture_id,
                "odds_api",
                "bet365",
                market_type,
                selection,
                2.0,
                implied_probability,
                "2026-05-20T08:00:00+00:00",
                dumps_payload({"selection": selection}),
            ),
        ).lastrowid

    return store_prediction(
        str(db_path),
        fixture_id,
        model_version_id,
        market_type,
        selection,
        probability,
        odds_snapshot_id=odds_snapshot_id,
    )


class PredictionBroadcastTests(unittest.TestCase):
    def test_broadcast_includes_eligible_stored_predictions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_prediction(db_path, "123", "2026-05-20T12:00:00+00:00", 0.64, 0.5)

            messages = build_daily_prediction_broadcast(str(db_path), date(2026, 5, 20), minimum_confidence="medium")
            text = "\n".join(messages)

            self.assertIn("FirmBetting Daily Predictions - 2026-05-20", text)
            self.assertIn("Home 123 vs Away 123", text)
            self.assertIn("Market: 1x2", text)
            self.assertIn("Pick: home", text)
            self.assertIn("Probability: 64.0%", text)
            self.assertIn("Confidence: high", text)
            self.assertIn("Odds: 2.00", text)
            self.assertIn("No prediction is guaranteed", text)

    def test_broadcast_excludes_low_confidence_predictions_when_configured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_prediction(db_path, "low", "2026-05-20T12:00:00+00:00", 0.51, 0.5)

            messages = build_daily_prediction_broadcast(str(db_path), date(2026, 5, 20), minimum_confidence="medium")
            text = "\n".join(messages)

            self.assertIn("No eligible picks", text)
            self.assertNotIn("Home low vs Away low", text)

    def test_empty_prediction_day_produces_clear_no_picks_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            initialize_database(str(db_path))

            messages = build_daily_prediction_broadcast(str(db_path), date(2026, 5, 20))

            self.assertEqual(1, len(messages))
            self.assertIn("No eligible picks are available for this date", messages[0])

    def test_long_messages_are_split_safely(self):
        long_text = "\n".join(f"Line {i} " + ("x" * 200) for i in range(50))

        chunks = split_telegram_message(long_text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= TELEGRAM_SAFE_LIMIT for chunk in chunks))

    def test_market_filtering_is_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_prediction(db_path, "one", "2026-05-20T12:00:00+00:00", 0.64, 0.5, "1x2", "home")
            seed_prediction(db_path, "two", "2026-05-20T15:00:00+00:00", 0.64, 0.5, "btts", "yes")

            messages = build_daily_prediction_broadcast(
                str(db_path),
                date(2026, 5, 20),
                market_types=["btts"],
                minimum_confidence="medium",
            )
            text = "\n".join(messages)

            self.assertIn("Market: btts", text)
            self.assertNotIn("Market: 1x2", text)


if __name__ == "__main__":
    unittest.main()
