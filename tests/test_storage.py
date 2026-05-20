import os
import tempfile
import unittest
from pathlib import Path

from app.data.storage import (
    StorageError,
    connect,
    dumps_payload,
    initialize_database,
    loads_payload,
    session,
)


class StorageTests(unittest.TestCase):
    def test_initialize_database_in_temporary_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"

            initialized = initialize_database(str(db_path))

            self.assertEqual(db_path, initialized)
            self.assertTrue(db_path.exists())
            with connect(str(db_path)) as conn:
                table_names = {
                    row["name"]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
            self.assertIn("fixtures", table_names)
            self.assertIn("odds_snapshots", table_names)
            self.assertIn("predictions", table_names)
            self.assertIn("results", table_names)
            self.assertIn("settlements", table_names)
            self.assertIn("model_versions", table_names)

    def test_initialize_database_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"

            initialize_database(str(db_path))
            initialize_database(str(db_path))

            with connect(str(db_path)) as conn:
                migrations = conn.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()
            self.assertEqual(1, migrations["count"])

    def test_insert_and_read_record_through_session_helper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "firmbetting.sqlite3"
            initialize_database(str(db_path))
            raw_payload = {"fixture": {"id": 123}, "status": "NS"}

            with session(str(db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO fixtures (
                        provider, provider_fixture_id, league_name, home_team,
                        away_team, kickoff_time, status, raw_payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "api_football",
                        "123",
                        "Premier League",
                        "Arsenal",
                        "Chelsea",
                        "2026-05-20T12:00:00+00:00",
                        "NS",
                        dumps_payload(raw_payload),
                    ),
                )

            with connect(str(db_path)) as conn:
                row = conn.execute("SELECT * FROM fixtures WHERE provider_fixture_id = ?", ("123",)).fetchone()

            self.assertEqual("Arsenal", row["home_team"])
            self.assertEqual(raw_payload, loads_payload(row["raw_payload"]))

    def test_invalid_database_path_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_parent = Path(tmpdir) / "missing" / "firmbetting.sqlite3"

            with self.assertRaises(StorageError) as exc:
                connect(str(missing_parent))

        self.assertIn("Database directory does not exist", str(exc.exception))

    def test_database_path_can_come_from_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "configured.sqlite3"

            old_value = os.environ.get("FIRMBETTING_DB_PATH")
            os.environ["FIRMBETTING_DB_PATH"] = str(db_path)
            try:
                initialized = initialize_database()
            finally:
                if old_value is None:
                    os.environ.pop("FIRMBETTING_DB_PATH", None)
                else:
                    os.environ["FIRMBETTING_DB_PATH"] = old_value

            self.assertEqual(db_path, initialized)
            self.assertTrue(db_path.exists())


if __name__ == "__main__":
    unittest.main()
