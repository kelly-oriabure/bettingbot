"""
Prediction persistence and confidence filtering helpers.

This module does not generate model outputs. It stores already-computed model
predictions with deterministic confidence labels for later broadcasts.
"""

from typing import Iterable, Optional

from app.data.storage import MVP_MARKET_TYPES, initialize_database, session


CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def compute_confidence(
    model_probability: float,
    implied_probability: Optional[float] = None,
    minimum_probability: float = 0.0,
) -> Optional[str]:
    """Compute deterministic high/medium/low confidence for a prediction."""
    if model_probability < 0 or model_probability > 1:
        raise ValueError("model_probability must be between 0 and 1")
    if implied_probability is not None and (implied_probability < 0 or implied_probability > 1):
        raise ValueError("implied_probability must be between 0 and 1")
    if model_probability < minimum_probability:
        return None

    if implied_probability is None:
        return "low"

    edge = model_probability - implied_probability
    if model_probability >= 0.6 and edge >= 0.10:
        return "high"
    if model_probability >= 0.53 and edge >= 0.03:
        return "medium"
    return "low"


def store_prediction(
    db_path: Optional[str],
    fixture_id: int,
    model_version_id: int,
    market_type: str,
    selection: str,
    probability: float,
    odds_snapshot_id: Optional[int] = None,
    minimum_probability: float = 0.0,
) -> Optional[int]:
    """Store one prediction with computed confidence, or return None if below threshold."""
    if market_type not in MVP_MARKET_TYPES:
        raise ValueError(f"Unsupported MVP market type: {market_type}")

    initialize_database(db_path)
    with session(db_path) as conn:
        implied_probability = None
        if odds_snapshot_id is not None:
            odds = conn.execute(
                "SELECT implied_probability FROM odds_snapshots WHERE id = ?",
                (odds_snapshot_id,),
            ).fetchone()
            if odds is None:
                raise ValueError(f"Unknown odds snapshot id: {odds_snapshot_id}")
            implied_probability = odds["implied_probability"]

        confidence = compute_confidence(
            model_probability=probability,
            implied_probability=implied_probability,
            minimum_probability=minimum_probability,
        )
        if confidence is None:
            return None

        cursor = conn.execute(
            """
            INSERT INTO predictions (
                fixture_id, odds_snapshot_id, model_version_id, market_type,
                selection, probability, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fixture_id,
                odds_snapshot_id,
                model_version_id,
                market_type,
                selection,
                probability,
                confidence,
            ),
        )
        return cursor.lastrowid


def eligible_predictions(
    db_path: Optional[str],
    market_types: Optional[Iterable[str]] = None,
    minimum_confidence: str = "medium",
) -> list[dict]:
    """Return stored predictions eligible for broadcast filters."""
    if minimum_confidence not in CONFIDENCE_RANK:
        raise ValueError(f"Unknown minimum confidence: {minimum_confidence}")

    min_rank = CONFIDENCE_RANK[minimum_confidence]
    allowed_markets = set(market_types) if market_types is not None else None
    initialize_database(db_path)

    with session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                p.*,
                f.home_team,
                f.away_team,
                f.league_name,
                f.kickoff_time,
                os.price,
                os.implied_probability
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            LEFT JOIN odds_snapshots os ON os.id = p.odds_snapshot_id
            ORDER BY f.kickoff_time, p.market_type, p.id
            """
        ).fetchall()

    eligible = []
    for row in rows:
        prediction = dict(row)
        if allowed_markets is not None and prediction["market_type"] not in allowed_markets:
            continue
        if CONFIDENCE_RANK[prediction["confidence"]] < min_rank:
            continue
        eligible.append(prediction)
    return eligible
