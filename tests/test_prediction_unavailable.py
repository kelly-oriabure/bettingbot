import asyncio
import inspect
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from app.bot import bot


class PredictionUnavailableTests(unittest.TestCase):
    def fake_model_module(self, model):
        module = types.ModuleType("app.models.dixon_coles")
        module.DixonColesModel = lambda: model
        return module

    def test_missing_model_file_returns_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bot_file = os.path.join(tmpdir, "app", "bot", "bot.py")
            with patch.object(bot, "__file__", fake_bot_file):
                with self.assertLogs("app.bot.bot", level="WARNING") as logs:
                    result = asyncio.run(bot._run_prediction("Arsenal", "Chelsea"))

        self.assertIsNone(result)
        self.assertIn("model file missing", "\n".join(logs.output))

    def test_unknown_teams_return_unavailable(self):
        class FakeModel:
            def predict_match(self, home_team, away_team):
                return None

        with tempfile.NamedTemporaryFile("w") as model_file:
            model_file.write('{"attack_Arsenal": 1, "defense_Arsenal": 1}')
            model_file.flush()

            with patch("app.bot.bot.os.path.exists", return_value=True):
                with patch("builtins.open", unittest.mock.mock_open(read_data='{"attack_Arsenal": 1}')):
                    fake_module = self.fake_model_module(FakeModel())
                    with patch.dict(sys.modules, {"app.models.dixon_coles": fake_module}):
                        with self.assertLogs("app.bot.bot", level="WARNING") as logs:
                            result = asyncio.run(bot._run_prediction("Unknown Home", "Unknown Away"))

        self.assertIsNone(result)
        self.assertIn("unknown teams", "\n".join(logs.output))

    def test_model_exception_returns_unavailable(self):
        class ExplodingModel:
            def predict_match(self, home_team, away_team):
                raise RuntimeError("model failed")

        with patch("app.bot.bot.os.path.exists", return_value=True):
            with patch("builtins.open", unittest.mock.mock_open(read_data='{"attack_Arsenal": 1}')):
                fake_module = self.fake_model_module(ExplodingModel())
                with patch.dict(sys.modules, {"app.models.dixon_coles": fake_module}):
                    with self.assertLogs("app.bot.bot", level="ERROR") as logs:
                        result = asyncio.run(bot._run_prediction("Arsenal", "Chelsea"))

        self.assertIsNone(result)
        self.assertIn("Prediction unavailable", "\n".join(logs.output))
        self.assertIn("model failed", "\n".join(logs.output))

    def test_prediction_path_does_not_import_or_call_random(self):
        source = inspect.getsource(bot._run_prediction)

        self.assertNotIn("import random", source)
        self.assertNotIn("random.", source)


if __name__ == "__main__":
    unittest.main()
