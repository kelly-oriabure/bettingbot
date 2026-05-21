"""
Data ingestion jobs for FirmBetting.

These jobs fetch provider data, normalize it, and persist it for later
prediction, settlement, reporting, and Telegram delivery steps.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.data.storage import dumps_payload, initialize_database, session


logger = logging.getLogger(__name__)
MVP_TOTALS_POINTS = {1.5: "over_under_1_5", 2.5: "over_under_2_5"}
COMPLETED_STATUSES = {"FT", "AET", "PEN"}


def parse_provider_datetime(value: str) -> datetime:
    """Parse a provider datetime and normalize it to timezone-aware UTC."""
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_provider_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def normalize_team_name(name: str) -> str:
    return " ".join(name.strip().split())


class ApiFootballResultsProvider:
    """Fetch fixture result/status updates from API-Football."""

    name = "API-Football"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("API_FOOTBALL_KEY", "")

    async def get_results(self, fixtures: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")

        import aiohttp

        results = []
        headers = {"x-apisports-key": self.api_key}
        async with aiohttp.ClientSession() as client:
            for fixture in fixtures:
                async with client.get(
                    "https://v3.football.api-sports.io/fixtures",
                    headers=headers,
                    params={"id": fixture["provider_fixture_id"]},
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "API-Football result fetch failed for fixture %s with status %s",
                            fixture["provider_fixture_id"],
                            response.status,
                        )
                        continue
                    data = await response.json()
                    if data.get("response"):
                        results.append(data["response"][0])
        return results


def _provider_fixture_id(match: Dict[str, Any]) -> Optional[str]:
    fixture_id = match.get("fixture_id") or match.get("provider_fixture_id") or match.get("id")
    if fixture_id is None:
        fixture = match.get("fixture")
        if isinstance(fixture, dict):
            fixture_id = fixture.get("id")
    if fixture_id is None:
        home_team = match.get("home_team")
        away_team = match.get("away_team")
        kickoff = match.get("date") or match.get("kickoff_time") or match.get("commence_time")
        if home_team and away_team and kickoff:
            kickoff_time = parse_provider_datetime(str(kickoff)).isoformat()
            return "|".join(
                [
                    normalize_team_name(str(home_team)).lower(),
                    normalize_team_name(str(away_team)).lower(),
                    kickoff_time,
                ]
            )
        return None
    return str(fixture_id)


def _normalize_fixture(match: Dict[str, Any], provider_name: str) -> Optional[Dict[str, Any]]:
    provider_fixture_id = _provider_fixture_id(match)
    home_team = match.get("home_team")
    away_team = match.get("away_team")
    kickoff = match.get("date") or match.get("kickoff_time") or match.get("commence_time")

    if not provider_fixture_id or not home_team or not away_team or not kickoff:
        return None

    kickoff_time = parse_provider_datetime(kickoff).isoformat()
    return {
        "provider": provider_name,
        "provider_fixture_id": provider_fixture_id,
        "league_id": str(match.get("league_id")) if match.get("league_id") is not None else None,
        "league_name": match.get("league_name"),
        "home_team": normalize_team_name(str(home_team)),
        "away_team": normalize_team_name(str(away_team)),
        "kickoff_time": kickoff_time,
        "status": match.get("status"),
        "raw_payload": dumps_payload(match.get("raw_payload") or match),
    }


async def ingest_daily_fixtures(provider=None, db_path: Optional[str] = None, hours_ahead: int = 72) -> Dict[str, int]:
    """
    Fetch upcoming fixtures and upsert them into storage.

    By default this uses API-Football, the MVP fixture/result source. Tests can
    pass a provider with an async `get_upcoming_matches()` method.
    """
    if provider is None:
        from app.data.fetcher import ApiFootballProvider

        provider = ApiFootballProvider()

    initialize_database(db_path)
    provider_name = normalize_provider_name(getattr(provider, "name", provider.__class__.__name__))
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    try:
        fixtures = await provider.get_upcoming_matches(hours_ahead=hours_ahead)
    except Exception as exc:
        logger.error("Fixture ingestion provider failure: %s", exc, exc_info=True)
        counts["failed"] += 1
        return counts

    with session(db_path) as conn:
        for match in fixtures:
            try:
                fixture = _normalize_fixture(match, provider_name)
                if fixture is None:
                    counts["skipped"] += 1
                    logger.warning("Skipping malformed fixture payload: %s", match)
                    continue

                existing = conn.execute(
                    """
                    SELECT id FROM fixtures
                    WHERE provider = ? AND provider_fixture_id = ?
                    """,
                    (fixture["provider"], fixture["provider_fixture_id"]),
                ).fetchone()

                if existing:
                    conn.execute(
                        """
                        UPDATE fixtures
                        SET league_id = ?,
                            league_name = ?,
                            home_team = ?,
                            away_team = ?,
                            kickoff_time = ?,
                            status = ?,
                            raw_payload = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            fixture["league_id"],
                            fixture["league_name"],
                            fixture["home_team"],
                            fixture["away_team"],
                            fixture["kickoff_time"],
                            fixture["status"],
                            fixture["raw_payload"],
                            existing["id"],
                        ),
                    )
                    counts["updated"] += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO fixtures (
                            provider, provider_fixture_id, league_id, league_name,
                            home_team, away_team, kickoff_time, status, raw_payload
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fixture["provider"],
                            fixture["provider_fixture_id"],
                            fixture["league_id"],
                            fixture["league_name"],
                            fixture["home_team"],
                            fixture["away_team"],
                            fixture["kickoff_time"],
                            fixture["status"],
                            fixture["raw_payload"],
                        ),
                    )
                    counts["inserted"] += 1
            except Exception as exc:
                counts["failed"] += 1
                logger.error("Failed to ingest fixture payload: %s", exc, exc_info=True)

    logger.info("Fixture ingestion counts: %s", counts)
    return counts


def _selection_for_h2h(outcome_name: str, match: Dict[str, Any]) -> Optional[str]:
    if outcome_name == match.get("home_team"):
        return "home"
    if outcome_name == match.get("away_team"):
        return "away"
    if outcome_name.lower() == "draw":
        return "draw"
    return None


def _extract_odds_snapshots(match: Dict[str, Any], provider_name: str, captured_at: str) -> List[Dict[str, Any]]:
    snapshots = []
    for bookmaker in match.get("bookmakers", []):
        bookmaker_name = bookmaker.get("key") or bookmaker.get("title") or bookmaker.get("name")
        for market in bookmaker.get("markets", []):
            market_key = market.get("key")
            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if price is None:
                    continue

                market_type = None
                selection = None
                if market_key == "h2h":
                    market_type = "1x2"
                    selection = _selection_for_h2h(str(outcome.get("name", "")), match)
                elif market_key == "totals":
                    point = float(outcome.get("point", 2.5))
                    market_type = MVP_TOTALS_POINTS.get(point)
                    outcome_name = str(outcome.get("name", "")).lower()
                    if outcome_name in ("over", "under"):
                        selection = outcome_name

                if not market_type or not selection:
                    continue

                numeric_price = float(price)
                snapshots.append(
                    {
                        "provider": provider_name,
                        "bookmaker": bookmaker_name,
                        "market_type": market_type,
                        "selection": selection,
                        "price": numeric_price,
                        "implied_probability": round(1 / numeric_price, 6) if numeric_price else None,
                        "captured_at": captured_at,
                        "raw_payload": dumps_payload(
                            {
                                "bookmaker": bookmaker,
                                "market": market_key,
                                "outcome": outcome,
                            }
                        ),
                    }
                )
    return snapshots


def _find_fixture_id(conn, match: Dict[str, Any]) -> Optional[int]:
    provider_fixture_id = _provider_fixture_id(match)
    if provider_fixture_id:
        row = conn.execute(
            "SELECT id FROM fixtures WHERE provider_fixture_id = ? ORDER BY id LIMIT 1",
            (provider_fixture_id,),
        ).fetchone()
        if row:
            return row["id"]

    home_team = normalize_team_name(str(match.get("home_team", "")))
    away_team = normalize_team_name(str(match.get("away_team", "")))
    kickoff = match.get("date") or match.get("kickoff_time") or match.get("commence_time")
    if not home_team or not away_team or not kickoff:
        return None

    kickoff_time = parse_provider_datetime(kickoff).isoformat()
    row = conn.execute(
        """
        SELECT id FROM fixtures
        WHERE home_team = ? AND away_team = ? AND kickoff_time = ?
        ORDER BY id LIMIT 1
        """,
        (home_team, away_team, kickoff_time),
    ).fetchone()
    return row["id"] if row else None


async def ingest_daily_odds(
    provider=None,
    db_path: Optional[str] = None,
    hours_ahead: int = 72,
    captured_at: Optional[str] = None,
) -> Dict[str, int]:
    """Fetch odds and store snapshots linked to already-ingested fixtures."""
    if provider is None:
        from app.data.fetcher import OddsApiProvider

        provider = OddsApiProvider()

    initialize_database(db_path)
    provider_name = normalize_provider_name(getattr(provider, "name", provider.__class__.__name__))
    counts = {"inserted": 0, "duplicates": 0, "skipped": 0, "failed": 0}
    captured_at = captured_at or datetime.now(timezone.utc).isoformat()

    if hasattr(provider, "api_keys") and not getattr(provider, "api_keys"):
        logger.error("Odds ingestion unavailable: ODDS_API_KEY is not configured")
        counts["failed"] += 1
        return counts

    try:
        matches = await provider.get_upcoming_matches(hours_ahead=hours_ahead)
    except Exception as exc:
        logger.error("Odds ingestion provider failure: %s", exc, exc_info=True)
        counts["failed"] += 1
        return counts

    quota_metadata = getattr(provider, "quota_metadata", None) or getattr(provider, "last_quota_headers", None)
    if quota_metadata:
        logger.info("Odds provider quota metadata: %s", quota_metadata)

    with session(db_path) as conn:
        for match in matches:
            try:
                fixture_id = _find_fixture_id(conn, match)
                if fixture_id is None:
                    counts["skipped"] += 1
                    logger.warning(
                        "Skipping odds with no matching fixture: %s vs %s at %s",
                        match.get("home_team"),
                        match.get("away_team"),
                        match.get("date") or match.get("kickoff_time") or match.get("commence_time"),
                    )
                    continue

                snapshots = _extract_odds_snapshots(match, provider_name, captured_at)
                if not snapshots:
                    counts["skipped"] += 1
                    continue

                for snapshot in snapshots:
                    existing = conn.execute(
                        """
                        SELECT id FROM odds_snapshots
                        WHERE fixture_id = ?
                          AND provider = ?
                          AND bookmaker IS ?
                          AND market_type = ?
                          AND selection = ?
                          AND price = ?
                          AND implied_probability IS ?
                          AND raw_payload = ?
                        LIMIT 1
                        """,
                        (
                            fixture_id,
                            snapshot["provider"],
                            snapshot["bookmaker"],
                            snapshot["market_type"],
                            snapshot["selection"],
                            snapshot["price"],
                            snapshot["implied_probability"],
                            snapshot["raw_payload"],
                        ),
                    ).fetchone()
                    if existing:
                        counts["duplicates"] += 1
                        continue

                    conn.execute(
                        """
                        INSERT INTO odds_snapshots (
                            fixture_id, provider, bookmaker, market_type,
                            selection, price, implied_probability, captured_at,
                            raw_payload
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fixture_id,
                            snapshot["provider"],
                            snapshot["bookmaker"],
                            snapshot["market_type"],
                            snapshot["selection"],
                            snapshot["price"],
                            snapshot["implied_probability"],
                            snapshot["captured_at"],
                            snapshot["raw_payload"],
                        ),
                    )
                    counts["inserted"] += 1
            except Exception as exc:
                counts["failed"] += 1
                logger.error("Failed to ingest odds payload: %s", exc, exc_info=True)

    logger.info("Odds ingestion counts: %s", counts)
    return counts


def _candidate_result_fixtures(conn) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT DISTINCT f.*
        FROM fixtures f
        JOIN predictions p ON p.fixture_id = f.id
        LEFT JOIN results r ON r.fixture_id = f.id
        WHERE r.id IS NULL OR r.status NOT IN ('FT', 'AET', 'PEN')
        ORDER BY f.kickoff_time
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _normalize_result(result: Dict[str, Any], fixture_lookup: Dict[str, int]) -> Optional[Dict[str, Any]]:
    provider_fixture_id = _provider_fixture_id(result)
    if not provider_fixture_id or provider_fixture_id not in fixture_lookup:
        return None

    fixture = result.get("fixture") if isinstance(result.get("fixture"), dict) else {}
    status_data = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
    goals = result.get("goals") if isinstance(result.get("goals"), dict) else {}

    status = result.get("status") or status_data.get("short")
    home_goals = result.get("final_home_goals", goals.get("home"))
    away_goals = result.get("final_away_goals", goals.get("away"))
    completed_at = result.get("completed_at")
    if completed_at:
        completed_at = parse_provider_datetime(completed_at).isoformat()
    elif status in COMPLETED_STATUSES:
        completed_at = datetime.now(timezone.utc).isoformat()

    return {
        "fixture_id": fixture_lookup[provider_fixture_id],
        "provider_fixture_id": provider_fixture_id,
        "final_home_goals": home_goals,
        "final_away_goals": away_goals,
        "status": status,
        "completed_at": completed_at,
        "raw_payload": dumps_payload(result),
    }


async def ingest_results(provider=None, db_path: Optional[str] = None) -> Dict[str, int]:
    """Fetch result/status updates for stored fixtures that have predictions."""
    if provider is None:
        provider = ApiFootballResultsProvider()

    initialize_database(db_path)
    counts = {"inserted": 0, "updated": 0, "pending": 0, "skipped": 0, "failed": 0}

    with session(db_path) as conn:
        candidate_fixtures = _candidate_result_fixtures(conn)

    if not candidate_fixtures:
        logger.info("No predicted fixtures require result ingestion")
        return counts

    try:
        provider_results = await provider.get_results(candidate_fixtures)
    except Exception as exc:
        logger.error("Result ingestion provider failure: %s", exc, exc_info=True)
        counts["failed"] += 1
        return counts

    fixture_lookup = {
        str(fixture["provider_fixture_id"]): fixture["id"]
        for fixture in candidate_fixtures
    }

    with session(db_path) as conn:
        for result in provider_results:
            try:
                normalized = _normalize_result(result, fixture_lookup)
                if normalized is None or not normalized["status"]:
                    counts["skipped"] += 1
                    logger.warning("Skipping malformed result payload: %s", result)
                    continue

                existing = conn.execute(
                    "SELECT id FROM results WHERE fixture_id = ?",
                    (normalized["fixture_id"],),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE results
                        SET final_home_goals = ?,
                            final_away_goals = ?,
                            status = ?,
                            completed_at = ?,
                            raw_payload = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (
                            normalized["final_home_goals"],
                            normalized["final_away_goals"],
                            normalized["status"],
                            normalized["completed_at"],
                            normalized["raw_payload"],
                            existing["id"],
                        ),
                    )
                    counts["updated"] += 1
                else:
                    conn.execute(
                        """
                        INSERT INTO results (
                            fixture_id, final_home_goals, final_away_goals,
                            status, completed_at, raw_payload
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            normalized["fixture_id"],
                            normalized["final_home_goals"],
                            normalized["final_away_goals"],
                            normalized["status"],
                            normalized["completed_at"],
                            normalized["raw_payload"],
                        ),
                    )
                    counts["inserted"] += 1

                conn.execute(
                    """
                    UPDATE fixtures
                    SET status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (normalized["status"], normalized["fixture_id"]),
                )

                if normalized["status"] not in COMPLETED_STATUSES:
                    counts["pending"] += 1
            except Exception as exc:
                counts["failed"] += 1
                logger.error("Failed to ingest result payload: %s", exc, exc_info=True)

    logger.info("Result ingestion counts: %s", counts)
    return counts
