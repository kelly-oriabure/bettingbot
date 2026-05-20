"""
Telegram broadcast formatting from stored data.

Broadcast generation is database-driven: it must not call provider APIs or run
models at formatting time.
"""

from datetime import date
from typing import Iterable, Optional

from app.data.ingestion import parse_provider_datetime
from app.prediction import CONFIDENCE_RANK, eligible_predictions
from app.data.storage import initialize_database, session


TELEGRAM_SAFE_LIMIT = 3900
DISCLAIMER = "No prediction is guaranteed. Bet responsibly and only with money you can afford to lose."


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _title_case(value: Optional[str]) -> str:
    return (value or "unknown").replace("_", " ").title()


def format_pick_label(market_type: str, selection: str, home_team: str, away_team: str) -> str:
    """Convert stored market codes into plain-language Telegram copy."""
    market_type = market_type.lower()
    selection = selection.lower()

    if market_type == "1x2":
        labels = {
            "home": f"{home_team} to win",
            "draw": "Draw",
            "away": f"{away_team} to win",
        }
        return labels.get(selection, selection)

    if market_type == "double_chance":
        labels = {
            "1x": f"{home_team} or draw",
            "12": f"{home_team} or {away_team}",
            "x2": f"Draw or {away_team}",
        }
        return labels.get(selection, selection)

    if market_type in {"over_under_1_5", "over_under_2_5"}:
        goals = "1.5" if market_type == "over_under_1_5" else "2.5"
        direction = "Over" if selection == "over" else "Under"
        return f"{direction} {goals} goals"

    if market_type == "btts":
        return "Both teams to score" if selection == "yes" else "Not both teams to score"

    return f"{_title_case(market_type)}: {_title_case(selection)}"


def _simple_reason(prediction: dict) -> str:
    confidence = prediction.get("confidence")
    if confidence == "high":
        return "This is one of today's stronger picks."
    if confidence == "medium":
        return "This pick has enough support to make the shortlist."
    return "This pick is included, but stake carefully."


def _format_prediction_line(prediction: dict) -> str:
    kickoff = parse_provider_datetime(prediction["kickoff_time"]).strftime("%H:%M UTC")
    league = prediction.get("league_name") or "Unknown league"
    pick = format_pick_label(
        prediction["market_type"],
        prediction["selection"],
        prediction["home_team"],
        prediction["away_team"],
    )
    return (
        f"{prediction['home_team']} vs {prediction['away_team']}\n"
        f"League: {league} | Kickoff: {kickoff}\n"
        f"Prediction: {pick}\n"
        f"Confidence: {_title_case(prediction['confidence'])}\n"
        f"Why: {_simple_reason(prediction)}"
    )


def split_telegram_message(text: str, limit: int = TELEGRAM_SAFE_LIMIT) -> list[str]:
    """Split text into Telegram-safe chunks without cutting lines when possible."""
    if len(text) <= limit:
        return [text]

    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if line_len > limit:
            for start in range(0, len(line), limit):
                chunks.append(line[start:start + limit])
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def build_daily_prediction_broadcast(
    db_path: Optional[str],
    target_date: date,
    market_types: Optional[Iterable[str]] = None,
    minimum_confidence: str = "medium",
) -> list[str]:
    """Build Telegram message chunks for stored predictions on a target date."""
    if minimum_confidence not in CONFIDENCE_RANK:
        raise ValueError(f"Unknown minimum confidence: {minimum_confidence}")

    candidates = eligible_predictions(
        db_path,
        market_types=market_types,
        minimum_confidence=minimum_confidence,
    )
    target = target_date.isoformat()
    predictions = [
        prediction
        for prediction in candidates
        if parse_provider_datetime(prediction["kickoff_time"]).date().isoformat() == target
    ]

    title = f"FirmBetting Daily Picks - {target}"
    if not predictions:
        return [
            "\n\n".join(
                [
                    title,
                    "No eligible picks are available for this date.",
                    DISCLAIMER,
                ]
            )
        ]

    high_count = sum(1 for prediction in predictions if prediction.get("confidence") == "high")
    medium_count = sum(1 for prediction in predictions if prediction.get("confidence") == "medium")
    lines = [
        title,
        "",
        f"Today's shortlist: {len(predictions)} pick(s)",
        f"High confidence: {high_count} | Medium confidence: {medium_count}",
        "",
    ]
    lines.extend(f"{index}. {_format_prediction_line(prediction)}" for index, prediction in enumerate(predictions, 1))
    lines.extend(["", "Reminder:", DISCLAIMER])
    return split_telegram_message("\n\n".join(lines))


def _settlement_rows_for_date(db_path: Optional[str], target_date: date) -> list[dict]:
    initialize_database(db_path)
    with session(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                p.market_type,
                p.selection,
                p.confidence,
                f.home_team,
                f.away_team,
                f.league_name,
                f.kickoff_time,
                r.final_home_goals,
                r.final_away_goals,
                r.status AS result_status,
                s.status AS settlement_status,
                s.reason
            FROM predictions p
            JOIN fixtures f ON f.id = p.fixture_id
            LEFT JOIN results r ON r.fixture_id = f.id
            LEFT JOIN settlements s ON s.prediction_id = p.id
            ORDER BY f.kickoff_time, p.id
            """
        ).fetchall()

    target = target_date.isoformat()
    return [
        dict(row)
        for row in rows
        if parse_provider_datetime(row["kickoff_time"]).date().isoformat() == target
    ]


def _format_result_line(row: dict) -> str:
    score = "pending"
    if row.get("final_home_goals") is not None and row.get("final_away_goals") is not None:
        score = f"{row['final_home_goals']}-{row['final_away_goals']}"
    league = row.get("league_name") or "Unknown league"
    status = row.get("settlement_status") or "pending"
    return (
        f"{league} | {row['home_team']} {score} {row['away_team']}\n"
        f"Market: {row['market_type']} | Pick: {row['selection']} | Result: {status}"
    )


def build_result_comparison_broadcast(
    db_path: Optional[str],
    target_date: date,
    include_pending: bool = False,
) -> list[str]:
    """Build Telegram result-comparison chunks from stored settlements."""
    rows = _settlement_rows_for_date(db_path, target_date)
    if not include_pending:
        rows = [row for row in rows if row.get("settlement_status") != "pending"]

    title = f"FirmBetting Results - {target_date.isoformat()}"
    if not rows:
        return [f"{title}\n\nNo settled results are available for this date."]

    won_lost = [row for row in rows if row.get("settlement_status") in {"won", "lost"}]
    other_statuses = [row for row in rows if row.get("settlement_status") not in {"won", "lost"}]
    won = sum(1 for row in won_lost if row.get("settlement_status") == "won")
    lost = sum(1 for row in won_lost if row.get("settlement_status") == "lost")
    sample_size = won + lost
    hit_rate = (won / sample_size) if sample_size else 0

    lines = [
        title,
        "",
        f"Summary: {won} won / {lost} lost | Sample size: {sample_size} | Hit rate: {_format_percent(hit_rate)}",
    ]

    if won_lost:
        lines.extend(["", "Settled picks:"])
        lines.extend(_format_result_line(row) for row in won_lost)

    if other_statuses:
        lines.extend(["", "Excluded from hit rate:"])
        lines.extend(_format_result_line(row) for row in other_statuses)

    return split_telegram_message("\n\n".join(lines))
