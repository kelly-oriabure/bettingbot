"""
Data fetching from football APIs.

Priority:
1. The Odds API: current fixtures + odds (free: 500/month)
2. API-Football: training data only (free plan lacks current season)
"""

import os
import asyncio
import aiohttp
import httpx
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

ODDS_API_LEAGUES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "Champions League",
    "soccer_netherlands_eredivisie": "Eredivisie",
    "soccer_portugal_primeira_liga": "Primeira Liga",
    "soccer_turkey_super_league": "Turkish Super League",
    "soccer_brazil_campeonato": "Brasileirao",
    "soccer_china_superleague": "Chinese Super League",
    "soccer_scotland_premiership": "Scottish Premiership",
}

LEAGUE_IDS = {
    39: "Premier League", 140: "La Liga", 61: "Ligue 1",
    135: "Bundesliga", 78: "Serie A", 848: "Brasileirao",
}

# Team name mapping: API name -> Model name
# The Odds API returns full team names, but the Dixon-Coles model uses shorter names
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
    "Reims": "Reims",
    "Rennes": "Rennes",
    "Saint Etienne": "Saint Etienne",
    "Strasbourg": "Strasbourg",
    "Toulouse": "Toulouse",
}

def normalize_team_name(name: str) -> str:
    """Normalize team name from API to model format."""
    return TEAM_NAME_MAP.get(name, name)


class OddsApiClient:
    """Primary source for current fixtures + odds."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ODDS_API_KEY", "")
    
    async def get_upcoming_matches(self, hours_ahead: int = 48) -> List[Dict]:
        """Get upcoming matches across all leagues."""
        all_matches = []
        
        async with httpx.AsyncClient() as client:
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
                    
                    if r.status_code == 429:
                        logger.warning("Odds API rate limit reached")
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
                    
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"Odds API error ({league_name}): {e}")
        
        logger.info(f"Odds API: {len(all_matches)} upcoming matches")
        return all_matches
    
    def extract_odds(self, match: Dict) -> Dict:
        """Extract average odds from match data."""
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


class FootballDataClient:
    """API-Football client — training data only (free plan lacks current season)."""
    
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


class DataManager:
    """Main data manager — combines both APIs."""
    
    def __init__(self):
        self.odds_api = OddsApiClient()
        self.api_football = FootballDataClient()
    
    async def get_todays_predictions_data(self) -> List[Dict]:
        """Get today's fixtures with odds for prediction."""
        upcoming = await self.odds_api.get_upcoming_matches(hours_ahead=24)
        
        if not upcoming:
            logger.info("No upcoming matches from Odds API")
            return []
        
        # Filter to matches within next 24 hours
        now = datetime.utcnow()
        today_matches = []
        for m in upcoming:
            try:
                match_time = datetime.fromisoformat(m["date"].replace("Z", "+00:00"))
                if now <= match_time <= now + timedelta(hours=24):
                    m["odds"] = self.odds_api.extract_odds(m)
                    today_matches.append(m)
            except:
                pass
        
        logger.info(f"Today's matches: {len(today_matches)}")
        return today_matches
