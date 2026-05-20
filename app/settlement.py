"""
Core football market settlement for the FirmBetting MVP.

Rules follow `info.txt`: regular 90 minutes plus stoppage time only, no extra
time or penalties for MVP markets, and interrupted/postponed matches void if
not completed within 48 hours after initial kickoff.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from app.data.ingestion import COMPLETED_STATUSES, parse_provider_datetime
from app.data.storage import session


logger = logging.getLogger(__name__)
DELAYED_STATUSES = {"PST", "POSTPONED", "INT", "SUSP", "ABD"}
CANCELLED_STATUSES = {"CANC", "CANCELLED"}


def _result_outcome(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if away_goals > home_goals:
        return "away"
    return "draw"


def _regular_time_score(row) -> Optional[Tuple[int, int]]:
    if row["status"] in {"AET", "PEN"} and row["raw_payload"]:
        raw_payload = json.loads(row["raw_payload"])
        fulltime = raw_payload.get("score", {}).get("fulltime", {})
        if fulltime.get("home") is not None and fulltime.get("away") is not None:
            return int(fulltime["home"]), int(fulltime["away"])
        return None

    if row["final_home_goals"] is None or row["final_away_goals"] is None:
        return None
    return int(row["final_home_goals"]), int(row["final_away_goals"])


def settle_market(market_type: str, selection: str, home_goals: int, away_goals: int) -> Tuple[str, str, str]:
    """Return settlement status, settled outcome, and reason for an MVP market."""
    market_type = market_type.lower()
    selection = selection.lower()
    total_goals = home_goals + away_goals
    outcome = _result_outcome(home_goals, away_goals)

    if market_type == "1x2":
        if selection not in {"home", "draw", "away"}:
            return "cancelled", outcome, "invalid 1x2 selection"
        return ("won" if selection == outcome else "lost"), outcome, "settled 1x2 from regular-time score"

    if market_type == "double_chance":
        valid = {
            "1x": {"home", "draw"},
            "12": {"home", "away"},
            "x2": {"draw", "away"},
        }
        if selection not in valid:
            return "cancelled", outcome, "invalid double chance selection"
        return ("won" if outcome in valid[selection] else "lost"), outcome, "settled double chance from regular-time score"

    if market_type in {"over_under_1_5", "over_under_2_5"}:
        line = 1.5 if market_type == "over_under_1_5" else 2.5
        if selection not in {"over", "under"}:
            return "cancelled", str(total_goals), "invalid over/under selection"
        won = total_goals > line if selection == "over" else total_goals < line
        return ("won" if won else "lost"), str(total_goals), f"settled total goals {selection} {line}"

    if market_type == "btts":
        if selection not in {"yes", "no"}:
            return "cancelled", "unknown", "invalid BTTS selection"
        both_scored = home_goals > 0 and away_goals > 0
        won = both_scored if selection == "yes" else not both_scored
        settled_outcome = "yes" if both_scored else "no"
        return ("won" if won else "lost"), settled_outcome, "settled BTTS from regular-time score"

    return "cancelled", "unknown", f"unsupported MVP market: {market_type}"


def _status_for_unfinished(row, now: datetime) -> Optional[Tuple[str, str, str]]:
    status = str(row["status"] or "").upper()
    if status in CANCELLED_STATUSES:
        return "cancelled", status, "fixture cancelled by provider"

    if status in DELAYED_STATUSES:
        kickoff = parse_provider_datetime(row["kickoff_time"])
        if now >= kickoff + timedelta(hours=48):
            return "void", status, "fixture not completed within 48 hours after initial kickoff"
        return "pending", status, "fixture delayed but still inside 48-hour completion window"

    return None


def _upsert_settlement(conn, prediction_id: int, status: str, settled_outcome: str, reason: str) -> None:
    existing = conn.execute(
        "SELECT id FROM settlements WHERE prediction_id = ?",
        (prediction_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE settlements
            SET status = ?, settled_outcome = ?, reason = ?, settled_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, settled_outcome, reason, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO settlements (prediction_id, status, settled_outcome, reason)
            VALUES (?, ?, ?, ?)
            """,
            (prediction_id, status, settled_outcome, reason),
        )


def settle_predictions(db_path: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, int]:
    """Settle predictions that have result/status data available."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    counts = {"won": 0, "lost": 0, "void": 0, "cancelled": 0, "pending": 0, "skipped": 0, "failed": 0}
    with session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                p.id AS prediction_id,
                p.market_type,
                p.selection,
                f.kickoff_time,
                r.status,
                r.final_home_goals,
                r.final_away_goals,
                r.raw_payload
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            LEFT JOIN results r ON r.fixture_id = f.id
            """
        ).fetchall()

        for row in rows:
            try:
                if row["status"] is None:
                    counts["skipped"] += 1
                    continue

                unfinished = _status_for_unfinished(row, now)
                if unfinished:
                    status, settled_outcome, reason = unfinished
                    _upsert_settlement(conn, row["prediction_id"], status, settled_outcome, reason)
                    counts[status] += 1
                    continue

                if row["status"] not in COMPLETED_STATUSES:
                    _upsert_settlement(
                        conn,
                        row["prediction_id"],
                        "pending",
                        str(row["status"]),
                        "fixture result is not final",
                    )
                    counts["pending"] += 1
                    continue

                score = _regular_time_score(row)
                if score is None:
                    _upsert_settlement(
                        conn,
                        row["prediction_id"],
                        "cancelled",
                        str(row["status"]),
                        "regular-time score unavailable",
                    )
                    counts["cancelled"] += 1
                    continue

                settlement_status, settled_outcome, reason = settle_market(
                    row["market_type"],
                    row["selection"],
                    score[0],
                    score[1],
                )
                _upsert_settlement(conn, row["prediction_id"], settlement_status, settled_outcome, reason)
                counts[settlement_status] += 1
            except Exception as exc:
                counts["failed"] += 1
                logger.error("Failed to settle prediction %s: %s", row["prediction_id"], exc, exc_info=True)

    logger.info("Settlement counts: %s", counts)
    return counts
