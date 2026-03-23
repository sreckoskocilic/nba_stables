import asyncio

import requests
from fastapi import APIRouter, HTTPException
from helpers.common import CACHE_TTL, TEAMS, cache
from helpers.logger import log_exceptions
from helpers.stats import _with_retry, load_players_dict

router = APIRouter()

NBA_PLAYER_MOVEMENT_URL = (
    "https://stats.nba.com/js/data/playermovement/NBA_Player_Movement.json"
)

_NBA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

_session = requests.Session()
_session.headers.update(_NBA_HEADERS)


@router.get("/api/trades")
async def get_trades():
    """Get NBA player movement transactions with resolved team and player names"""
    cached = cache.get("trades")
    if cached is not None:
        return cached

    def _sync():
        resp = _with_retry(lambda: _session.get(NBA_PLAYER_MOVEMENT_URL, timeout=10))
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

            tricode, team_name = TEAMS.get(team_id, ("", "Unknown Team"))

            player_row = players_dict.get(player_id)
            player_name = (
                player_row[1]
                if player_row
                else (
                    row.get("PLAYER_SLUG", "").replace("-", " ").title()
                    or "Unknown Player"
                )
            )

            transactions.append(
                {
                    "date": date_key,
                    "teamTricode": tricode,
                    "teamName": team_name,
                    "playerName": player_name,
                    "type": row.get("Transaction_Type", ""),
                    "description": row.get("TRANSACTION_DESCRIPTION", ""),
                }
            )

        transactions.sort(key=lambda x: x["date"], reverse=True)
        return {"transactions": transactions, "total": len(transactions)}

    try:
        result = await asyncio.to_thread(_sync)
        cache.set("trades", result, CACHE_TTL["trades"])
        return result
    except requests.RequestException as e:
        log_exceptions(e)
        raise HTTPException(
            status_code=503, detail="Failed to fetch player movement data"
        )
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch trades")
