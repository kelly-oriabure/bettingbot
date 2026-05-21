"""Database-backed ingestion, prediction, and settlement pipeline."""

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from app.data.ingestion import ingest_daily_fixtures, ingest_daily_odds, ingest_results, parse_provider_datetime
from app.data.storage import dumps_payload, initialize_database, session
from app.prediction import store_prediction
from app.settlement import settle_predictions


logger = logging.getLogger(__name__)
DEFAULT_MODEL_PATH = Path("data") / "model.json"


class CachedProvider:
    """Cache provider matches so fixture and odds ingestion share one fetch."""

    def __init__(self, provider):
        self.provider = provider
        self.name = getattr(provider, "name", provider.__class__.__name__)
        self.api_keys = getattr(provider, "api_keys", None)
        self.quota_metadata = getattr(provider, "quota_metadata", None)
        self.last_quota_headers = getattr(provider, "last_quota_headers", None)
        self._matches = None

    async def get_upcoming_matches(self, hours_ahead: int = 72):
        if self._matches is None:
            self._matches = await self.provider.get_upcoming_matches(hours_ahead=hours_ahead)
            self.quota_metadata = getattr(self.provider, "quota_metadata", None)
            self.last_quota_headers = getattr(self.provider, "last_quota_headers", None)
        return list(self._matches)


def _load_dixon_coles_model(model_path: Optional[str] = None):
    """Load a trained Dixon-Coles model or return None when unavailable."""
    path = Path(model_path or os.environ.get("FIRMBETTING_MODEL_PATH") or DEFAULT_MODEL_PATH)
    if not path.exists():
        logger.error("Prediction model missing: %s", path)
        return None, path

    from app.models.dixon_coles import DixonColesModel

    try:
        model = DixonColesModel()
        model.params = json.loads(path.read_text())
        model.teams = sorted(
            key.replace("attack_", "")
            for key in model.params
            if key.startswith("attack_")
        )
        model.fitted = bool(model.teams)
        if not model.fitted:
            logger.error("Prediction model has no teams: %s", path)
            return None, path
        return model, path
    except Exception as exc:
        logger.error("Could not load prediction model %s: %s", path, exc, exc_info=True)
        return None, path


def _model_version_for_artifact(conn, model_path: Path) -> int:
    """Ensure a model_versions row exists for the current model artifact."""
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()[:12]
    version = f"dixon_coles-artifact-{digest}"
    existing = conn.execute("SELECT id FROM model_versions WHERE version = ?", (version,)).fetchone()
    if existing:
        return existing["id"]

    return conn.execute(
        """
        INSERT INTO model_versions (version, model_type, metrics, artifact_path)
        VALUES (?, ?, ?, ?)
        """,
        (
            version,
            "dixon_coles",
            dumps_payload({"source": "runtime_artifact", "sha256": digest}),
            str(model_path),
        ),
    ).lastrowid


def _target_fixture_rows(conn, target_date: Optional[date]) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, home_team, away_team, kickoff_time
        FROM fixtures
        ORDER BY kickoff_time, id
        """
    ).fetchall()
    fixtures = [dict(row) for row in rows]
    if target_date is None:
        return fixtures
    return [
        row
        for row in fixtures
        if parse_provider_datetime(row["kickoff_time"]).date() == target_date
    ]


def _latest_odds_snapshot_id(conn, fixture_id: int, market_type: str, selection: str) -> Optional[int]:
    row = conn.execute(
        """
        SELECT id
        FROM odds_snapshots
        WHERE fixture_id = ? AND market_type = ? AND selection = ?
        ORDER BY captured_at DESC, id DESC
        LIMIT 1
        """,
        (fixture_id, market_type, selection),
    ).fetchone()
    return row["id"] if row else None


def _prediction_exists(conn, fixture_id: int, model_version_id: int, market_type: str, selection: str) -> bool:
    row = conn.execute(
        """
        SELECT id
        FROM predictions
        WHERE fixture_id = ?
          AND model_version_id = ?
          AND market_type = ?
          AND selection = ?
        LIMIT 1
        """,
        (fixture_id, model_version_id, market_type, selection),
    ).fetchone()
    return row is not None


def _prediction_candidates(prediction) -> list[tuple[str, str, float]]:
    h2h = {
        "home": prediction.home_win_prob,
        "draw": prediction.draw_prob,
        "away": prediction.away_win_prob,
    }
    double_chance = {
        "1x": prediction.home_win_prob + prediction.draw_prob,
        "12": prediction.home_win_prob + prediction.away_win_prob,
        "x2": prediction.draw_prob + prediction.away_win_prob,
    }
    over_under = {
        "over": prediction.over_under_25,
        "under": 1 - prediction.over_under_25,
    }
    btts = {
        "yes": prediction.btts_prob,
        "no": 1 - prediction.btts_prob,
    }
    return [
        ("1x2", max(h2h, key=h2h.get), max(h2h.values())),
        ("double_chance", max(double_chance, key=double_chance.get), max(double_chance.values())),
        ("over_under_2_5", max(over_under, key=over_under.get), max(over_under.values())),
        ("btts", max(btts, key=btts.get), max(btts.values())),
    ]


def generate_stored_predictions(
    db_path: Optional[str] = None,
    target_date: Optional[date] = None,
    model_path: Optional[str] = None,
    minimum_probability: float = 0.5,
) -> Dict[str, int]:
    """Generate deterministic predictions for stored fixtures and persist them."""
    initialize_database(db_path)
    model, resolved_model_path = _load_dixon_coles_model(model_path)
    counts = {"inserted": 0, "duplicates": 0, "unavailable": 0, "skipped": 0, "failed": 0}
    if model is None:
        counts["failed"] += 1
        return counts

    with session(db_path) as conn:
        model_version_id = _model_version_for_artifact(conn, resolved_model_path)
        fixtures = _target_fixture_rows(conn, target_date)

    for fixture in fixtures:
        try:
            prediction = model.predict_match(fixture["home_team"], fixture["away_team"])
            if prediction is None:
                counts["unavailable"] += 1
                continue

            for market_type, selection, probability in _prediction_candidates(prediction):
                with session(db_path) as conn:
                    if _prediction_exists(conn, fixture["id"], model_version_id, market_type, selection):
                        counts["duplicates"] += 1
                        continue
                    odds_snapshot_id = _latest_odds_snapshot_id(conn, fixture["id"], market_type, selection)

                prediction_id = store_prediction(
                    db_path,
                    fixture["id"],
                    model_version_id,
                    market_type,
                    selection,
                    probability,
                    odds_snapshot_id=odds_snapshot_id,
                    minimum_probability=minimum_probability,
                )
                if prediction_id is None:
                    counts["skipped"] += 1
                else:
                    counts["inserted"] += 1
        except Exception as exc:
            counts["failed"] += 1
            logger.error("Failed to generate prediction for fixture %s: %s", fixture["id"], exc, exc_info=True)

    logger.info("Prediction generation counts: %s", counts)
    return counts


async def run_daily_prediction_pipeline(
    db_path: Optional[str] = None,
    target_date: Optional[date] = None,
    fixture_provider=None,
    odds_provider=None,
) -> Dict[str, Dict[str, int]]:
    """Populate storage for the daily prediction broadcast."""
    fixture_counts = await ingest_daily_fixtures(provider=fixture_provider, db_path=db_path)
    if not any(fixture_counts.get(key, 0) for key in ("inserted", "updated")):
        if odds_provider is None:
            from app.data.fetcher import get_odds_provider

            odds_provider = get_odds_provider()
        cached_odds_provider = CachedProvider(odds_provider)
        fallback_counts = await ingest_daily_fixtures(provider=cached_odds_provider, db_path=db_path)
        fixture_counts = {
            **fixture_counts,
            "inserted": fixture_counts.get("inserted", 0) + fallback_counts.get("inserted", 0),
            "updated": fixture_counts.get("updated", 0) + fallback_counts.get("updated", 0),
            "skipped": fixture_counts.get("skipped", 0) + fallback_counts.get("skipped", 0),
            "failed": fixture_counts.get("failed", 0) + fallback_counts.get("failed", 0),
        }
        odds_provider = cached_odds_provider

    odds_counts = await ingest_daily_odds(provider=odds_provider, db_path=db_path)
    prediction_counts = generate_stored_predictions(db_path=db_path, target_date=target_date)
    return {
        "fixtures": fixture_counts,
        "odds": odds_counts,
        "predictions": prediction_counts,
    }


async def run_result_settlement_pipeline(db_path: Optional[str] = None, result_provider=None) -> Dict[str, Dict[str, int]]:
    """Populate results and settlements before the result-comparison broadcast."""
    result_counts = await ingest_results(provider=result_provider, db_path=db_path)
    settlement_counts = settle_predictions(db_path=db_path, now=datetime.now(timezone.utc))
    return {
        "results": result_counts,
        "settlements": settlement_counts,
    }
