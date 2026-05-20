"""Accuracy reporting for FirmBetting predictions."""

from datetime import date
from typing import Dict, Optional

from app.data.ingestion import parse_provider_datetime
from app.data.storage import SETTLEMENT_STATUSES, initialize_database, session


def _empty_group(market_type: str, confidence: str) -> Dict:
    return {
        "market_type": market_type,
        "confidence": confidence,
        "won": 0,
        "lost": 0,
        "void": 0,
        "cancelled": 0,
        "pending": 0,
        "sample_size": 0,
        "hit_rate": None,
    }


def _within_date_range(kickoff_time: str, start_date: Optional[date], end_date: Optional[date]) -> bool:
    kickoff_date = parse_provider_datetime(kickoff_time).date()
    if start_date and kickoff_date < start_date:
        return False
    if end_date and kickoff_date > end_date:
        return False
    return True


def build_accuracy_report(
    db_path: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Dict:
    """Return accuracy grouped by market type and confidence bucket."""
    initialize_database(db_path)
    with session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                p.market_type,
                p.confidence,
                f.kickoff_time,
                COALESCE(s.status, 'pending') AS settlement_status
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            LEFT JOIN settlements s ON s.prediction_id = p.id
            ORDER BY p.market_type, p.confidence, f.kickoff_time
            """
        ).fetchall()

    groups = {}
    totals = {status: 0 for status in SETTLEMENT_STATUSES}
    for row in rows:
        if not _within_date_range(row["kickoff_time"], start_date, end_date):
            continue

        status = row["settlement_status"]
        if status not in totals:
            status = "cancelled"
        key = (row["market_type"], row["confidence"])
        if key not in groups:
            groups[key] = _empty_group(row["market_type"], row["confidence"])
        groups[key][status] += 1
        totals[status] += 1

    for group in groups.values():
        group["sample_size"] = group["won"] + group["lost"]
        if group["sample_size"]:
            group["hit_rate"] = round(group["won"] / group["sample_size"], 4)

    total_sample_size = totals["won"] + totals["lost"]
    return {
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "groups": sorted(groups.values(), key=lambda item: (item["market_type"], item["confidence"])),
        "totals": {
            **totals,
            "sample_size": total_sample_size,
            "hit_rate": round(totals["won"] / total_sample_size, 4) if total_sample_size else None,
        },
    }
