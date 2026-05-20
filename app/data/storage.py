"""
SQLite storage helpers for the FirmBetting MVP.

The schema is intentionally plain SQL so the MVP can run locally without extra
ORM dependencies and later migrate to Postgres with minimal domain churn.
"""

import json
import os
import re
import shlex
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence, Union


DEFAULT_DB_PATH = Path("data") / "firmbetting.sqlite3"
SETTLEMENT_STATUSES = ("pending", "won", "lost", "void", "cancelled")
MVP_MARKET_TYPES = ("1x2", "double_chance", "over_under_1_5", "over_under_2_5", "btts")
POSTGRES_SCHEMES = ("postgres://", "postgresql://")
SQLITE_SCHEME = "sqlite:///"


class StorageError(RuntimeError):
    """Raised when storage cannot be initialized or opened."""


def is_postgres_dsn(value: Optional[str]) -> bool:
    """Return True when a configured database value targets Postgres/Neon."""
    return bool(value and value.startswith(POSTGRES_SCHEMES))


def normalize_database_url(value: Optional[str]) -> Optional[str]:
    """Normalize raw database URLs and `psql 'postgresql://...'` CLI strings."""
    if not value:
        return None
    stripped = value.strip()
    if stripped.startswith("psql "):
        try:
            parts = shlex.split(stripped)
        except ValueError:
            return stripped
        for part in parts[1:]:
            if part.startswith(POSTGRES_SCHEMES) or part.startswith(SQLITE_SCHEME):
                return part
    return stripped


def get_database_url(db_path: Optional[str] = None) -> Optional[str]:
    """Resolve a Postgres DATABASE_URL if production storage is configured."""
    normalized_db_path = normalize_database_url(db_path)
    if is_postgres_dsn(normalized_db_path):
        return normalized_db_path
    database_url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if db_path is None and is_postgres_dsn(database_url):
        return database_url
    return None


def get_database_path(db_path: Optional[str] = None) -> Path:
    """Resolve the configured SQLite database path."""
    normalized_db_path = normalize_database_url(db_path)
    if is_postgres_dsn(normalized_db_path):
        raise StorageError("Postgres URLs must be accessed through DATABASE_URL/session, not as a SQLite path")

    configured = normalized_db_path or os.environ.get("FIRMBETTING_DB_PATH")
    if not configured:
        database_url = normalize_database_url(os.environ.get("DATABASE_URL", ""))
        if database_url and database_url.startswith(SQLITE_SCHEME):
            configured = database_url.replace(SQLITE_SCHEME, "", 1)

    return Path(configured or DEFAULT_DB_PATH).expanduser()


def dumps_payload(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    """Serialize provider payloads as deterministic JSON text."""
    if payload is None:
        return None
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def loads_payload(payload_text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Deserialize provider payload JSON text."""
    if payload_text is None:
        return None
    return json.loads(payload_text)


def _translate_postgres_sql(sql: str) -> str:
    """Translate the repo's SQLite-style placeholders to psycopg placeholders."""
    translated = re.sub(r"\bIS\s+\?", "IS NOT DISTINCT FROM %s", sql)
    return translated.replace("?", "%s")


class PostgresCursor:
    """Small cursor adapter exposing the sqlite3 cursor shape used by callers."""

    def __init__(self, cursor, lastrowid: Optional[int] = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PostgresConnection:
    """psycopg connection adapter for the small sqlite3 API surface in use."""

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql: str, parameters: Optional[Sequence[Any]] = None) -> PostgresCursor:
        cursor = self._connection.cursor()
        normalized = sql.lstrip().upper()
        translated = _translate_postgres_sql(sql)
        wants_lastrowid = (
            normalized.startswith("INSERT INTO")
            and " RETURNING " not in normalized
            and "INSERT INTO SCHEMA_MIGRATIONS" not in normalized
        )
        if wants_lastrowid:
            translated = f"{translated.rstrip()} RETURNING id"

        cursor.execute(translated, parameters or ())
        lastrowid = None
        if wants_lastrowid:
            row = cursor.fetchone()
            if row:
                lastrowid = row["id"]
        return PostgresCursor(cursor, lastrowid)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


def _connect_postgres(database_url: str) -> PostgresConnection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise StorageError("Postgres DATABASE_URL is configured but psycopg is not installed") from exc

    try:
        conn = psycopg.connect(database_url, row_factory=dict_row)
    except Exception as exc:
        raise StorageError(f"Could not open Postgres database: {exc}") from exc
    return PostgresConnection(conn)


def connect(db_path: Optional[str] = None) -> Union[sqlite3.Connection, PostgresConnection]:
    """Open a SQLite connection with row access and foreign keys enabled."""
    database_url = get_database_url(db_path)
    if database_url:
        return _connect_postgres(database_url)

    path = get_database_path(db_path)
    parent = path.parent
    if parent and not parent.exists():
        raise StorageError(f"Database directory does not exist: {parent}")

    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error as exc:
        raise StorageError(f"Could not open database at {path}: {exc}") from exc

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(db_path: Optional[str] = None) -> Iterator[Union[sqlite3.Connection, PostgresConnection]]:
    """Context-managed SQLite connection that commits or rolls back."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _initialize_postgres(database_url: str) -> str:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fixtures (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            provider TEXT NOT NULL,
            provider_fixture_id TEXT NOT NULL,
            league_id TEXT,
            league_name TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            kickoff_time TEXT NOT NULL,
            status TEXT,
            raw_payload TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, provider_fixture_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
            provider TEXT NOT NULL,
            bookmaker TEXT,
            market_type TEXT NOT NULL,
            selection TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            implied_probability DOUBLE PRECISION,
            captured_at TEXT NOT NULL,
            raw_payload TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fixture_id, provider, bookmaker, market_type, selection, captured_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_versions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            version TEXT NOT NULL UNIQUE,
            model_type TEXT NOT NULL,
            trained_from TEXT,
            trained_to TEXT,
            metrics TEXT,
            artifact_path TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            fixture_id INTEGER NOT NULL REFERENCES fixtures(id),
            odds_snapshot_id INTEGER REFERENCES odds_snapshots(id),
            model_version_id INTEGER NOT NULL REFERENCES model_versions(id),
            market_type TEXT NOT NULL,
            selection TEXT NOT NULL,
            probability DOUBLE PRECISION NOT NULL,
            confidence TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(probability >= 0 AND probability <= 1),
            CHECK(confidence IS NULL OR confidence IN ('high', 'medium', 'low'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            fixture_id INTEGER NOT NULL UNIQUE REFERENCES fixtures(id),
            final_home_goals INTEGER,
            final_away_goals INTEGER,
            status TEXT NOT NULL,
            completed_at TEXT,
            raw_payload TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS settlements (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            prediction_id INTEGER NOT NULL UNIQUE REFERENCES predictions(id),
            status TEXT NOT NULL,
            settled_outcome TEXT,
            reason TEXT,
            settled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK(status IN ('pending', 'won', 'lost', 'void', 'cancelled'))
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshot_identity
        ON odds_snapshots(fixture_id, provider, bookmaker, market_type, selection, captured_at)
        """,
        "INSERT INTO schema_migrations(version) VALUES (?) ON CONFLICT (version) DO NOTHING",
    ]
    try:
        with session(database_url) as conn:
            for statement in statements:
                conn.execute(statement, (1,) if "schema_migrations(version)" in statement else None)
    except Exception as exc:
        raise StorageError(f"Could not initialize Postgres database: {exc}") from exc
    return database_url


def initialize_database(db_path: Optional[str] = None) -> Union[Path, str]:
    """Create MVP tables if they do not already exist."""
    database_url = get_database_url(db_path)
    if database_url:
        return _initialize_postgres(database_url)

    path = get_database_path(db_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with session(str(path)) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS fixtures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    provider_fixture_id TEXT NOT NULL,
                    league_id TEXT,
                    league_name TEXT,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    kickoff_time TEXT NOT NULL,
                    status TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, provider_fixture_id)
                );

                CREATE TABLE IF NOT EXISTS odds_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    bookmaker TEXT,
                    market_type TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    price REAL NOT NULL,
                    implied_probability REAL,
                    captured_at TEXT NOT NULL,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(fixture_id) REFERENCES fixtures(id),
                    UNIQUE(fixture_id, provider, bookmaker, market_type, selection, captured_at)
                );

                CREATE TABLE IF NOT EXISTS model_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    model_type TEXT NOT NULL,
                    trained_from TEXT,
                    trained_to TEXT,
                    metrics TEXT,
                    artifact_path TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER NOT NULL,
                    odds_snapshot_id INTEGER,
                    model_version_id INTEGER NOT NULL,
                    market_type TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    probability REAL NOT NULL,
                    confidence TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(probability >= 0 AND probability <= 1),
                    CHECK(confidence IS NULL OR confidence IN ('high', 'medium', 'low')),
                    FOREIGN KEY(fixture_id) REFERENCES fixtures(id),
                    FOREIGN KEY(odds_snapshot_id) REFERENCES odds_snapshots(id),
                    FOREIGN KEY(model_version_id) REFERENCES model_versions(id)
                );

                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fixture_id INTEGER NOT NULL UNIQUE,
                    final_home_goals INTEGER,
                    final_away_goals INTEGER,
                    status TEXT NOT NULL,
                    completed_at TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(fixture_id) REFERENCES fixtures(id)
                );

                CREATE TABLE IF NOT EXISTS settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prediction_id INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    settled_outcome TEXT,
                    reason TEXT,
                    settled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(status IN ('pending', 'won', 'lost', 'void', 'cancelled')),
                    FOREIGN KEY(prediction_id) REFERENCES predictions(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshot_identity
                ON odds_snapshots(fixture_id, provider, bookmaker, market_type, selection, captured_at);

                CREATE TRIGGER IF NOT EXISTS validate_settlement_status_insert
                BEFORE INSERT ON settlements
                WHEN NEW.status NOT IN ('pending', 'won', 'lost', 'void', 'cancelled')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid settlement status');
                END;

                CREATE TRIGGER IF NOT EXISTS validate_settlement_status_update
                BEFORE UPDATE OF status ON settlements
                WHEN NEW.status NOT IN ('pending', 'won', 'lost', 'void', 'cancelled')
                BEGIN
                    SELECT RAISE(ABORT, 'invalid settlement status');
                END;

                INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
                """
            )
    except sqlite3.Error as exc:
        raise StorageError(f"Could not initialize database at {path}: {exc}") from exc

    return path
