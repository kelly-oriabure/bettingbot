"""
SQLite storage helpers for the FirmBetting MVP.

The schema is intentionally plain SQL so the MVP can run locally without extra
ORM dependencies and later migrate to Postgres with minimal domain churn.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


DEFAULT_DB_PATH = Path("data") / "firmbetting.sqlite3"
SETTLEMENT_STATUSES = ("pending", "won", "lost", "void", "cancelled")
MVP_MARKET_TYPES = ("1x2", "double_chance", "over_under_1_5", "over_under_2_5", "btts")


class StorageError(RuntimeError):
    """Raised when storage cannot be initialized or opened."""


def get_database_path(db_path: Optional[str] = None) -> Path:
    """Resolve the configured SQLite database path."""
    configured = db_path or os.environ.get("FIRMBETTING_DB_PATH")
    if not configured:
        database_url = os.environ.get("DATABASE_URL", "")
        if database_url.startswith("sqlite:///"):
            configured = database_url.replace("sqlite:///", "", 1)

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


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with row access and foreign keys enabled."""
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
def session(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
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


def initialize_database(db_path: Optional[str] = None) -> Path:
    """Create MVP tables if they do not already exist."""
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
