import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.data.storage import (
    StorageError,
    _translate_postgres_sql,
    connect,
    dumps_payload,
    initialize_database,
    loads_payload,
    normalize_database_url,
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

    def test_postgres_database_url_uses_postgres_connector(self):
        old_database_url = os.environ.get("DATABASE_URL")
        old_db_path = os.environ.get("FIRMBETTING_DB_PATH")
        os.environ["DATABASE_URL"] = "postgresql://user:pass@example.com/firmbetting"
        os.environ.pop("FIRMBETTING_DB_PATH", None)
        try:
            with patch("app.data.storage._connect_postgres", return_value="postgres-connection") as mocked:
                connection = connect()
        finally:
            if old_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_database_url
            if old_db_path is None:
                os.environ.pop("FIRMBETTING_DB_PATH", None)
            else:
                os.environ["FIRMBETTING_DB_PATH"] = old_db_path

        self.assertEqual("postgres-connection", connection)
        mocked.assert_called_once_with("postgresql://user:pass@example.com/firmbetting")

    def test_postgres_translation_handles_placeholders_and_null_safe_is(self):
        sql = "SELECT id FROM odds_snapshots WHERE bookmaker IS ? AND fixture_id = ?"

        translated = _translate_postgres_sql(sql)

        self.assertEqual(
            "SELECT id FROM odds_snapshots WHERE bookmaker IS NOT DISTINCT FROM %s AND fixture_id = %s",
            translated,
        )

    def test_psql_wrapper_database_url_is_normalized(self):
        wrapped = "psql 'postgresql://user:pass@example.com/firmbetting?sslmode=require'"

        self.assertEqual(
            "postgresql://user:pass@example.com/firmbetting?sslmode=require",
            normalize_database_url(wrapped),
        )


if __name__ == "__main__":
    unittest.main()
