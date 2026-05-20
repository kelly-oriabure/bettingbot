import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from app.data.storage import connect, loads_payload
from app.train import evaluate_model, split_train_test, store_model_version, train_dixon_coles


def sample_training_data():
    return pd.DataFrame(
        [
            {
                "date": f"2026-05-{day:02d}",
                "home_team": "Home",
                "away_team": "Away",
                "home_goals": day % 4,
                "away_goals": (day + 1) % 3,
            }
            for day in range(1, 11)
        ]
    )


class RecordingModel:
    def __init__(self, max_goals=7):
        self.max_goals = max_goals
        self.fit_data = None
        self.params = {"attack_Home": 0.1, "defense_Away": -0.1, "home_advantage": 0.2, "rho": -0.13}
        self.teams = ["Home", "Away"]

    def fit(self, df):
        self.fit_data = df.copy()

    def predict_match(self, home_team, away_team):
        return SimpleNamespace(
            home_win_prob=0.6,
            draw_prob=0.2,
            away_win_prob=0.2,
            expected_home_goals=2.0,
            expected_away_goals=1.0,
            over_under_25=0.7,
            btts_prob=0.6,
        )


class PartiallyUnavailableModel:
    def __init__(self):
        self.calls = 0

    def predict_match(self, home_team, away_team):
        self.calls += 1
        if self.calls == 1:
            return None
        return SimpleNamespace(
            home_win_prob=0.6,
            draw_prob=0.2,
            away_win_prob=0.2,
            expected_home_goals=2.0,
            expected_away_goals=1.0,
            over_under_25=0.7,
            btts_prob=0.6,
        )


class TrainingPipelineTests(unittest.TestCase):
    def test_train_test_split_occurs_before_model_fit(self):
        df = sample_training_data()
        train_df, test_df = split_train_test(df, test_fraction=0.2)
        models = []

        def model_factory(max_goals=7):
            model = RecordingModel(max_goals=max_goals)
            models.append(model)
            return model

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.json"
            train_dixon_coles(train_df, artifact_path=str(artifact_path), model_cls=model_factory)

        self.assertEqual(8, len(models[0].fit_data))
        self.assertEqual(2, len(test_df))
        self.assertLess(models[0].fit_data["date"].max(), test_df["date"].min())

    def test_model_artifact_is_written_when_training_succeeds(self):
        train_df, _ = split_train_test(sample_training_data())

        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.json"
            train_dixon_coles(train_df, artifact_path=str(artifact_path), model_cls=RecordingModel)

            self.assertTrue(artifact_path.exists())
            self.assertIn("attack_Home", artifact_path.read_text())

    def test_model_version_record_is_created(self):
        train_df, test_df = split_train_test(sample_training_data())
        metrics = evaluate_model(RecordingModel(), test_df)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            version = store_model_version(
                metrics,
                artifact_path="data/model.json",
                league_ids=[39],
                seasons=[2024],
                train_df=train_df,
                db_path=str(db_path),
            )

            with connect(str(db_path)) as conn:
                row = conn.execute("SELECT * FROM model_versions WHERE version = ?", (version,)).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual("dixon_coles", row["model_type"])
        self.assertEqual("data/model.json", row["artifact_path"])
        stored_metrics = loads_payload(row["metrics"])
        self.assertEqual(8, stored_metrics["training_sample_size"])
        self.assertEqual([39], stored_metrics["leagues"])

    def test_backtest_metrics_include_sample_size_and_exclude_unavailable_predictions(self):
        _, test_df = split_train_test(sample_training_data(), test_fraction=0.2)

        metrics = evaluate_model(PartiallyUnavailableModel(), test_df)

        self.assertEqual(2, metrics["total_test_matches"])
        self.assertEqual(1, metrics["unavailable_predictions"])
        self.assertEqual(1, metrics["evaluated_predictions"])
        self.assertEqual(1, metrics["market_metrics"]["1x2"]["sample_size"])
        self.assertEqual(1, metrics["market_metrics"]["over_under_2_5"]["sample_size"])
        self.assertEqual(1, metrics["market_metrics"]["btts"]["sample_size"])


if __name__ == "__main__":
    unittest.main()
