import requests
from fastapi import APIRouter, HTTPException
from helpers.common import CACHE_TTL, cache
from helpers.logger import log_exceptions
from helpers.stats import load_players_dict

router = APIRouter()

NBA_PLAYER_MOVEMENT_URL = "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"

_NBA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# NBA team ID → (tricode, full name)
_TEAMS = {
    1610612737: ("ATL", "Atlanta Hawks"),
    1610612738: ("BOS", "Boston Celtics"),
    1610612751: ("BKN", "Brooklyn Nets"),
    1610612766: ("CHA", "Charlotte Hornets"),
    1610612741: ("CHI", "Chicago Bulls"),
    1610612739: ("CLE", "Cleveland Cavaliers"),
    1610612742: ("DAL", "Dallas Mavericks"),
    1610612743: ("DEN", "Denver Nuggets"),
    1610612765: ("DET", "Detroit Pistons"),
    1610612744: ("GSW", "Golden State Warriors"),
    1610612745: ("HOU", "Houston Rockets"),
    1610612754: ("IND", "Indiana Pacers"),
    1610612746: ("LAC", "LA Clippers"),
    1610612747: ("LAL", "Los Angeles Lakers"),
    1610612763: ("MEM", "Memphis Grizzlies"),
    1610612748: ("MIA", "Miami Heat"),
    1610612749: ("MIL", "Milwaukee Bucks"),
    1610612750: ("MIN", "Minnesota Timberwolves"),
    1610612740: ("NOP", "New Orleans Pelicans"),
    1610612752: ("NYK", "New York Knicks"),
    1610612760: ("OKC", "Oklahoma City Thunder"),
    1610612753: ("ORL", "Orlando Magic"),
    1610612755: ("PHI", "Philadelphia 76ers"),
    1610612756: ("PHX", "Phoenix Suns"),
    1610612757: ("POR", "Portland Trail Blazers"),
    1610612758: ("SAC", "Sacramento Kings"),
    1610612759: ("SAS", "San Antonio Spurs"),
    1610612761: ("TOR", "Toronto Raptors"),
    1610612762: ("UTA", "Utah Jazz"),
    1610612764: ("WAS", "Washington Wizards"),
}


@router.get("/api/trades")
def get_trades():
    """Get NBA player movement transactions with resolved team and player names"""
    cached = cache.get("trades")
    if cached:
        return cached

    try:
        resp = requests.get(NBA_PLAYER_MOVEMENT_URL, headers=_NBA_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("NBA_Player_Movement", {}).get("rows", [])
        players_dict = load_players_dict()

        transactions = []
        for row in rows:
            team_id = int(row.get("TEAM_ID") or 0)
            player_id = int(row.get("PLAYER_ID") or 0)
            date_raw = row.get("TRANSACTION_DATE", "")
            date_key = date_raw[:10] if date_raw else ""

            tricode, team_name = _TEAMS.get(team_id, ("", "Unknown Team"))

            player_row = players_dict.get(player_id)
            player_name = player_row[1] if player_row else row.get("PLAYER_SLUG", "").replace("-", " ").title()

            transactions.append({
                "date": date_key,
                "teamTricode": tricode,
                "teamName": team_name,
                "playerName": player_name,
                "type": row.get("Transaction_Type", ""),
                "description": row.get("TRANSACTION_DESCRIPTION", ""),
            })

        transactions.sort(key=lambda x: x["date"], reverse=True)
        result = {"transactions": transactions, "total": len(transactions)}
        cache.set("trades", result, CACHE_TTL["standings"])  # 1 hour cache
        return result
    except requests.RequestException as e:
        log_exceptions(e)
        raise HTTPException(status_code=503, detail="Failed to fetch player movement data")
    except Exception as e: # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
