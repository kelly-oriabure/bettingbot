"""
Data fetching from football APIs.

Supports multiple odds providers with easy switching via ODDS_PROVIDER env var:
- "odds_api" → The Odds API (500 req/month free)
- "api_football" → API-Football (paid plan for current fixtures)
- "sharp_api" → SharpAPI (12 req/min free)

Training data always comes from API-Football (historical).
"""

import os
import asyncio
import aiohttp
import httpx
import pandas as pd
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# ─── API Base URLs ───────────────────────────────────────────────────────────
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SHARP_API_BASE = "https://api.sharpapi.io/v1"

# ─── League Mappings ─────────────────────────────────────────────────────────
ODDS_API_LEAGUES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_france_ligue_one": "Ligue 1",
    # Champions League, Eredivisie, etc. commented out to save credits
    # "soccer_uefa_champs_league": "Champions League",
    # "soccer_netherlands_eredivisie": "Eredivisie",
    # "soccer_portugal_primeira_liga": "Primeira Liga",
    # "soccer_turkey_super_league": "Turkish Super League",
    # "soccer_brazil_campeonato": "Brasileirao",
    # "soccer_china_superleague": "Chinese Super League",
    # "soccer_spl": "Scottish Premiership",
}

LEAGUE_IDS = {
    39: "Premier League", 140: "La Liga", 61: "Ligue 1",
    135: "Bundesliga", 78: "Serie A", 848: "Brasileirao",
}

SHARP_API_SPORTS = {
    "football": "Football",
}

SHARP_API_LEAGUES = {
    39: "Premier League",   # EPL
    140: "La Liga",         # Spain
    61: "Ligue 1",          # France
    135: "Bundesliga",      # Germany
    78: "Serie A",          # Italy
    848: "Brasileirao",     # Brazil
    169: "Chinese Super League",
    188: "Scottish Premiership",
}

# ─── Team Name Mapping ───────────────────────────────────────────────────────
# API names → Dixon-Coles model names
TEAM_NAME_MAP = {
    # Premier League
    "Brighton and Hove Albion": "Brighton",
    "Wolverhampton Wanderers": "Wolves",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Nottingham Forest": "Nottingham Forest",
    "Newcastle United": "Newcastle",
    "Manchester United": "Manchester United",
    "Manchester City": "Manchester City",
    "Aston Villa": "Aston Villa",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Liverpool": "Liverpool",
    "Arsenal": "Arsenal",
    "Chelsea": "Chelsea",
    "Brentford": "Brentford",
    "Bournemouth": "Bournemouth",
    "Southampton": "Southampton",
    "Ipswich": "Ipswich",
    "Burnley": "Burnley",
    # La Liga
    "Alavés": "Alaves",
    "CA Osasuna": "Osasuna",
    "Athletic Bilbao": "Athletic Club",
    "Real Betis": "Real Betis",
    "Real Madrid": "Real Madrid",
    "Real Sociedad": "Real Sociedad",
    "Barcelona": "Barcelona",
    "Atletico Madrid": "Atletico Madrid",
    "Valencia": "Valencia",
    "Villarreal": "Villarreal",
    "Sevilla": "Sevilla",
    "Girona": "Girona",
    "Getafe": "Getafe",
    "Mallorca": "Mallorca",
    "Celta Vigo": "Celta Vigo",
    "Espanyol": "Espanyol",
    "Las Palmas": "Las Palmas",
    "Rayo Vallecano": "Rayo Vallecano",
    "Leganes": "Leganes",
    "Valladolid": "Valladolid",
    # Serie A
    "AC Milan": "AC Milan",
    "AS Roma": "AS Roma",
    "Atalanta": "Atalanta",
    "Bologna": "Bologna",
    "Fiorentina": "Fiorentina",
    "Genoa": "Genoa",
    "Inter": "Inter",
    "Juventus": "Juventus",
    "Lazio": "Lazio",
    "Lecce": "Lecce",
    "Napoli": "Napoli",
    "Torino": "Torino",
    "Udinese": "Udinese",
    "Cagliari": "Cagliari",
    "Empoli": "Empoli",
    "Hellas Verona": "Hellas Verona",
    "Monza": "Monza",
    "Parma": "Parma",
    "Como": "Como",
    "Venezia": "Venezia",
    # Bundesliga
    "1. FC Heidenheim": "1. FC Heidenheim",
    "1899 Hoffenheim": "1899 Hoffenheim",
    "Bayer Leverkusen": "Bayer Leverkusen",
    "Bayern München": "Bayern München",
    "Borussia Dortmund": "Borussia Dortmund",
    "Borussia Mönchengladbach": "Borussia Mönchengladbach",
    "Eintracht Frankfurt": "Eintracht Frankfurt",
    "FC Augsburg": "FC Augsburg",
    "FC St. Pauli": "FC St. Pauli",
    "FSV Mainz 05": "FSV Mainz 05",
    "Holstein Kiel": "Holstein Kiel",
    "RB Leipzig": "RB Leipzig",
    "SC Freiburg": "SC Freiburg",
    "SV Elversberg": "SV Elversberg",
    "Union Berlin": "Union Berlin",
    "VfB Stuttgart": "VfB Stuttgart",
    "VfL Bochum": "VfL Bochum",
    "VfL Wolfsburg": "VfL Wolfsburg",
    "Werder Bremen": "Werder Bremen",
    # Ligue 1
    "Angers": "Angers",
    "Auxerre": "Auxerre",
    "Le Havre": "Le Havre",
    "Lens": "Lens",
    "Lille": "Lille",
    "Lyon": "Lyon",
    "Marseille": "Marseille",
    "Metz": "Metz",
    "Monaco": "Monaco",
    "Montpellier": "Montpellier",
    "Nantes": "Nantes",
    "Nice": "Nice",
    "Paris Saint Germain": "Paris Saint Germain",
    "Paris Saint-Germain": "Paris Saint Germain",
    "Reims": "Reims",
    "Rennes": "Rennes",
    "Saint Etienne": "Saint Etienne",
    "Strasbourg": "Strasbourg",
    "Toulouse": "Toulouse",
}


def normalize_team_name(name: str) -> str:
    """Normalize team name from API to model format."""
    return TEAM_NAME_MAP.get(name, name)


# ═══════════════════════════════════════════════════════════════════════════════
# ODDS PROVIDER BASE CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class OddsProvider(ABC):
    """Base class for odds data providers."""
    
    @abstractmethod
    async def get_upcoming_matches(self, hours_ahead: int = 48) -> List[Dict]:
        """Get upcoming matches with odds data."""
        pass
    
    @abstractmethod
    def extract_odds(self, match: Dict) -> Dict:
        """Extract odds from match data into standard format."""
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER 1: THE ODDS API
# ═══════════════════════════════════════════════════════════════════════════════

class OddsApiProvider(OddsProvider):
    """The Odds API — 500 req/month free. Supports key rotation."""
    
    def __init__(self, api_key: Optional[str] = None):
        env_key = api_key or os.environ.get("ODDS_API_KEY", "")
        self.api_keys = []
        if env_key:
            self.api_keys.append(env_key)
        backup_keys = os.environ.get("ODDS_API_BACKUP_KEYS", "")
        if backup_keys:
            self.api_keys.extend(k.strip() for k in backup_keys.split(",") if k.strip())
        if not backup_keys:
            self.api_keys.extend([
                "c2daa19655f9b4c994693b89b2e91192",
                "2f82efcaab9665282e435f481a9832ec",
            ])
        self._key_index = 0
        self.name = "The Odds API"
    
    @property
    def api_key(self) -> str:
        if not self.api_keys:
            return ""
        return self.api_keys[self._key_index % len(self.api_keys)]
    
    def _rotate_key(self) -> bool:
        if len(self.api_keys) <= 1:
            return False
        self._key_index = (self._key_index + 1) % len(self.api_keys)
        logger.info(f"[{self.name}] Rotated to key index {self._key_index} ({self.api_key[:8]}...)")
        return True
    
    async def get_upcoming_matches(self, hours_ahead: int = 48) -> List[Dict]:
        all_matches = []
        keys_tried = 0
        
        while keys_tried < len(self.api_keys):
            async with httpx.AsyncClient() as client:
                league_ok = 0
                rotated = False
                for sport_key, league_name in ODDS_API_LEAGUES.items():
                    try:
                        r = await client.get(
                            f"{ODDS_API_BASE}/sports/{sport_key}/odds",
                            params={
                                "apiKey": self.api_key,
                                "regions": "eu,uk",
                                "markets": "h2h,totals",
                                "oddsFormat": "decimal",
                            },
                            timeout=15,
                        )
                        
                        remaining = r.headers.get("x-requests-remaining")
                        if remaining is not None:
                            try:
                                if int(remaining) <= 0:
                                    logger.warning(f"[{self.name}] Key {self.api_key[:8]}... exhausted ({remaining} remaining)")
                                    rotated = True
                                    break
                            except ValueError:
                                pass
                        
                        if r.status_code in (429, 401):
                            logger.warning(f"[{self.name}] Key {self.api_key[:8]}... {'rate limited' if r.status_code==429 else 'unauthorized'}")
                            rotated = True
                            break
                        
                        if r.status_code == 200:
                            for match in r.json():
                                all_matches.append({
                                    "home_team": normalize_team_name(match["home_team"]),
                                    "away_team": normalize_team_name(match["away_team"]),
                                    "date": match["commence_time"],
                                    "league_name": league_name,
                                    "sport_key": sport_key,
                                    "bookmakers": match.get("bookmakers", []),
                                })
                            league_ok += 1
                        
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.debug(f"[{self.name}] Error ({league_name}): {e}")
                
                if league_ok > 0:
                    break
                
                keys_tried += 1
                if not self._rotate_key():
                    logger.error(f"[{self.name}] All {len(self.api_keys)} keys exhausted")
                    break
        
        logger.info(f"[{self.name}]: {len(all_matches)} upcoming matches (key {self._key_index})")
        return all_matches
    
    def extract_odds(self, match: Dict) -> Dict:
        result = {"home_implied_prob": 0, "draw_implied_prob": 0, "away_implied_prob": 0, "over_25": 0}
        home_p, draw_p, away_p = [], [], []
        
        for bk in match.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk["key"] == "h2h":
                    for o in mk["outcomes"]:
                        if o["name"] == match["home_team"]: home_p.append(1/o["price"])
                        elif o["name"] == match["away_team"]: away_p.append(1/o["price"])
                        elif o["name"] == "Draw": draw_p.append(1/o["price"])
                elif mk["key"] == "totals":
                    for o in mk["outcomes"]:
                        if o["name"] == "Over": result["over_25"] = o["price"]
        
        if home_p: result["home_implied_prob"] = sum(home_p)/len(home_p)
        if draw_p: result["draw_implied_prob"] = sum(draw_p)/len(draw_p)
        if away_p: result["away_implied_prob"] = sum(away_p)/len(away_p)
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER 2: API-FOOTBALL
# ═══════════════════════════════════════════════════════════════════════════════

class ApiFootballProvider(OddsProvider):
    """API-Football — requires paid plan for current fixtures."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("API_FOOTBALL_KEY", "")
        self.headers = {"x-apisports-key": self.api_key}
        self.name = "API-Football"
    
    async def get_upcoming_matches(self, hours_ahead: int = 48) -> List[Dict]:
        leagues = [39, 140, 61, 135, 78, 848]
        all_matches = []
        
        async with aiohttp.ClientSession() as session:
            for league_id in leagues:
                try:
                    async with session.get(
                        f"{API_FOOTBALL_BASE}/fixtures",
                        headers=self.headers,
                        params={"league": league_id, "next": 20}
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        
                        for f in data.get("response", []):
                            match = {
                                "fixture_id": f["fixture"]["id"],
                                "home_team": normalize_team_name(f["teams"]["home"]["name"]),
                                "away_team": normalize_team_name(f["teams"]["away"]["name"]),
                                "date": f["fixture"]["date"],
                                "league_name": f["league"]["name"],
                                "league_id": f["league"]["id"],
                                "status": f["fixture"]["status"]["short"],
                                "bookmakers": [],
                            }
                            # Fetch odds for this fixture
                            odds = await self._fetch_odds(session, f["fixture"]["id"])
                            if odds:
                                match["_precomputed_odds"] = odds
                            all_matches.append(match)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"[{self.name}] Error (league {league_id}): {e}")
        
        logger.info(f"[{self.name}]: {len(all_matches)} upcoming matches")
        return all_matches
    
    async def _fetch_odds(self, session: aiohttp.ClientSession, fixture_id: int) -> Optional[Dict]:
        try:
            async with session.get(
                f"{API_FOOTBALL_BASE}/odds",
                headers=self.headers,
                params={"fixture": fixture_id}
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data.get("response"):
                    return None
                
                odds_data = data["response"][0]
                result = {"home_implied_prob": 0, "draw_implied_prob": 0, "away_implied_prob": 0, "over_25": 0}
                
                for bookmaker in odds_data.get("bookmakers", []):
                    for bet in bookmaker.get("bets", []):
                        if bet["name"] == "Match Winner":
                            for outcome in bet.get("values", []):
                                if outcome["value"] == "Home":
                                    result["home_implied_prob"] = 1 / float(outcome["odd"])
                                elif outcome["value"] == "Draw":
                                    result["draw_implied_prob"] = 1 / float(outcome["odd"])
                                elif outcome["value"] == "Away":
                                    result["away_implied_prob"] = 1 / float(outcome["odd"])
                        elif bet["name"] == "Over/Under 2.5":
                            for outcome in bet.get("values", []):
                                if outcome["value"] == "Over":
                                    result["over_25"] = float(outcome["odd"])
                return result
        except Exception:
            return None
    
    def extract_odds(self, match: Dict) -> Dict:
        # API-Football odds are pre-computed during fetch
        if "_precomputed_odds" in match:
            return match["_precomputed_odds"]
        return {"home_implied_prob": 0, "draw_implied_prob": 0, "away_implied_prob": 0, "over_25": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER 3: SHARP API
# ═══════════════════════════════════════════════════════════════════════════════

class SharpApiProvider(OddsProvider):
    """SharpAPI — 12 req/min free tier, real-time SSE streaming."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("SHARP_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.name = "SharpAPI"
    
    async def get_upcoming_matches(self, hours_ahead: int = 48) -> List[Dict]:
        all_matches = []
        
        async with aiohttp.ClientSession() as session:
            for league_id, league_name in SHARP_API_LEAGUES.items():
                try:
                    # SharpAPI endpoint for football matches with odds
                    async with session.get(
                        f"{SHARP_API_BASE}/football/matches",
                        headers=self.headers,
                        params={
                            "league_id": league_id,
                            "status": "not_started",
                        }
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"[{self.name}] Error {resp.status} for {league_name}")
                            continue
                        data = await resp.json()
                        
                        for match in data.get("matches", []):
                            all_matches.append({
                                "home_team": normalize_team_name(match.get("home_team", {}).get("name", "")),
                                "away_team": normalize_team_name(match.get("away_team", {}).get("name", "")),
                                "date": match.get("start_time", ""),
                                "league_name": league_name,
                                "league_id": league_id,
                                "bookmakers": match.get("odds", []),
                                "_sharp_odds": match.get("odds", {}),
                            })
                    
                    await asyncio.sleep(0.5)  # Respect rate limit (12 req/min)
                except Exception as e:
                    logger.debug(f"[{self.name}] Error ({league_name}): {e}")
        
        logger.info(f"[{self.name}]: {len(all_matches)} upcoming matches")
        return all_matches
    
    def extract_odds(self, match: Dict) -> Dict:
        # SharpAPI provides pre-computed odds
        if "_sharp_odds" in match:
            odds = match["_sharp_odds"]
            return {
                "home_implied_prob": odds.get("home_implied_prob", 0),
                "draw_implied_prob": odds.get("draw_implied_prob", 0),
                "away_implied_prob": odds.get("away_implied_prob", 0),
                "over_25": odds.get("over_25", 0),
            }
        return {"home_implied_prob": 0, "draw_implied_prob": 0, "away_implied_prob": 0, "over_25": 0}


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDER FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "odds_api": OddsApiProvider,
    "api_football": ApiFootballProvider,
    "sharp_api": SharpApiProvider,
}


def get_odds_provider() -> OddsProvider:
    """Get the configured odds provider based on ODDS_PROVIDER env var."""
    provider_name = os.environ.get("ODDS_PROVIDER", "odds_api").lower()
    provider_class = PROVIDERS.get(provider_name)
    
    if not provider_class:
        logger.warning(f"Unknown provider '{provider_name}', falling back to odds_api")
        provider_class = OddsApiProvider
    
    provider = provider_class()
    logger.info(f"Using odds provider: {provider.name}")
    return provider


# ═══════════════════════════════════════════════════════════════════════════════
# API-FOOTBALL CLIENT (Training Data)
# ═══════════════════════════════════════════════════════════════════════════════

class FootballDataClient:
    """API-Football client for historical/training data."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("API_FOOTBALL_KEY", "")
        self.headers = {"x-apisports-key": self.api_key}
    
    async def get_historical_results(self, league_id: int, season: int) -> pd.DataFrame:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_FOOTBALL_BASE}/fixtures",
                headers=self.headers,
                params={"league": league_id, "season": season}
            ) as resp:
                if resp.status != 200:
                    return pd.DataFrame()
                data = await resp.json()
        
        completed = []
        for f in data.get("response", []):
            if f["goals"]["home"] is not None and f["fixture"]["status"]["short"] in ("FT", "AET", "PEN"):
                completed.append({
                    "date": f["fixture"]["date"],
                    "league_id": f["league"]["id"],
                    "home_team": f["teams"]["home"]["name"],
                    "away_team": f["teams"]["away"]["name"],
                    "home_goals": f["goals"]["home"],
                    "away_goals": f["goals"]["away"],
                })
        
        df = pd.DataFrame(completed)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df
    
    async def get_training_data(self, league_ids: List[int] = None, seasons: List[int] = None) -> pd.DataFrame:
        leagues = league_ids or [39, 140, 61, 135, 78]
        seasons = seasons or [2024]
        all_data = []
        for league_id in leagues:
            for season in seasons:
                try:
                    df = await self.get_historical_results(league_id, season)
                    if not df.empty:
                        all_data.append(df)
                        logger.info(f"Training data: {len(df)} matches, league {league_id}, season {season}")
                except Exception as e:
                    logger.error(f"Error: league {league_id} season {season}: {e}")
                await asyncio.sleep(0.3)
        
        return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class DataManager:
    """Main data manager — uses configured odds provider + API-Football for training."""
    
    def __init__(self):
        self.odds_provider = get_odds_provider()
        self.api_football = FootballDataClient()
    
    async def get_todays_predictions_data(self) -> List[Dict]:
        """Get today's fixtures with odds for prediction."""
        upcoming = await self.odds_provider.get_upcoming_matches(hours_ahead=24)
        
        if not upcoming:
            logger.info(f"No upcoming matches from {self.odds_provider.name}")
            return []
        
        now = datetime.utcnow()
        today_matches = []
        for m in upcoming:
            try:
                date_str = m.get("date", "").replace("Z", "+00:00")
                if "+" not in date_str[-6:] and "-" not in date_str[-6:]:
                    date_str += "+00:00"
                match_time = datetime.fromisoformat(date_str)
                if now <= match_time <= now + timedelta(hours=24):
                    m["odds"] = self.odds_provider.extract_odds(m)
                    today_matches.append(m)
            except Exception as e:
                logger.debug(f"Error processing fixture: {e}")
        
        logger.info(f"Today's matches with odds: {len(today_matches)}")
        return today_matches
    
    async def get_upcoming_matches(self, hours_ahead: int = 24) -> List[Dict]:
        """Get upcoming matches for the next N hours."""
        upcoming = await self.odds_provider.get_upcoming_matches(hours_ahead=hours_ahead)
        
        if not upcoming:
            logger.info(f"No upcoming matches from {self.odds_provider.name}")
            return []
        
        now = datetime.utcnow()
        upcoming_matches = []
        parse_errors = 0
        
        for m in upcoming:
            try:
                date_str = m.get("date", "")
                if not date_str:
                    continue
                # Handle various ISO formats
                date_str = date_str.replace("Z", "+00:00")
                if "+" not in date_str[-6:] and "-" not in date_str[-6:]:
                    date_str += "+00:00"
                match_time = datetime.fromisoformat(date_str)
                
                if now <= match_time <= now + timedelta(hours=hours_ahead):
                    m["odds"] = self.odds_provider.extract_odds(m)
                    upcoming_matches.append(m)
            except Exception as e:
                parse_errors += 1
                logger.debug(f"Error processing fixture ({m.get('home_team', '?')} vs {m.get('away_team', '?')}): {e}")
        
        if parse_errors > 0:
            logger.warning(f"Failed to parse {parse_errors} fixture dates")
        
        # Fallback: if time filtering removed ALL matches, return all upcoming
        if len(upcoming_matches) == 0 and len(upcoming) > 0:
            logger.warning(f"Time filtering removed all {len(upcoming)} matches — using all available")
            for m in upcoming:
                m["odds"] = self.odds_provider.extract_odds(m)
                upcoming_matches.append(m)
        
        logger.info(f"Upcoming matches: {len(upcoming_matches)} (from {len(upcoming)} total)")
        return upcoming_matches
