import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.data.storage import initialize_database, session
from app.reporting import build_accuracy_report


def seed_report_prediction(db_path, fixture_key, market_type, confidence, settlement_status, kickoff_date="2026-05-20"):
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
                f"{kickoff_date}T12:00:00+00:00",
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
            (fixture_id, "odds_api", "bet365", market_type, "home", 2.0, 0.5, f"{kickoff_date}T08:00:00+00:00", "{}"),
        ).lastrowid
        prediction_id = conn.execute(
            """
            INSERT INTO predictions (
                fixture_id, odds_snapshot_id, model_version_id, market_type,
                selection, probability, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (fixture_id, odds_snapshot_id, model_version_id, market_type, "home", 0.6, confidence),
        ).lastrowid
        if settlement_status is not None:
            conn.execute(
                "INSERT INTO settlements (prediction_id, status, settled_outcome, reason) VALUES (?, ?, ?, ?)",
                (prediction_id, settlement_status, "home", "test settlement"),
            )


class AccuracyReportingTests(unittest.TestCase):
    def test_void_and_cancelled_are_excluded_from_hit_rate_denominator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_report_prediction(db_path, "won", "1x2", "medium", "won")
            seed_report_prediction(db_path, "lost", "1x2", "medium", "lost")
            seed_report_prediction(db_path, "void", "1x2", "medium", "void")
            seed_report_prediction(db_path, "cancelled", "1x2", "medium", "cancelled")

            report = build_accuracy_report(str(db_path))
            group = report["groups"][0]

            self.assertEqual(1, group["won"])
            self.assertEqual(1, group["lost"])
            self.assertEqual(1, group["void"])
            self.assertEqual(1, group["cancelled"])
            self.assertEqual(2, group["sample_size"])
            self.assertEqual(0.5, group["hit_rate"])

    def test_pending_predictions_are_counted_but_excluded_from_hit_rate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_report_prediction(db_path, "won", "1x2", "medium", "won")
            seed_report_prediction(db_path, "pending", "1x2", "medium", None)

            report = build_accuracy_report(str(db_path))
            group = report["groups"][0]

            self.assertEqual(1, group["pending"])
            self.assertEqual(1, group["sample_size"])
            self.assertEqual(1.0, group["hit_rate"])

    def test_reports_group_by_market(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_report_prediction(db_path, "one", "1x2", "medium", "won")
            seed_report_prediction(db_path, "two", "btts", "medium", "lost")

            report = build_accuracy_report(str(db_path))
            markets = {group["market_type"] for group in report["groups"]}

            self.assertEqual({"1x2", "btts"}, markets)

    def test_reports_group_by_confidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_report_prediction(db_path, "high", "1x2", "high", "won")
            seed_report_prediction(db_path, "low", "1x2", "low", "lost")

            report = build_accuracy_report(str(db_path))
            confidences = {group["confidence"] for group in report["groups"]}

            self.assertEqual({"high", "low"}, confidences)

    def test_date_range_filtering_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            seed_report_prediction(db_path, "inside", "1x2", "medium", "won", kickoff_date="2026-05-20")
            seed_report_prediction(db_path, "outside", "1x2", "medium", "lost", kickoff_date="2026-05-21")

            report = build_accuracy_report(
                str(db_path),
                start_date=date(2026, 5, 20),
                end_date=date(2026, 5, 20),
            )

            self.assertEqual(1, len(report["groups"]))
            self.assertEqual(1, report["groups"][0]["won"])
            self.assertEqual(0, report["groups"][0]["lost"])


if __name__ == "__main__":
    unittest.main()
