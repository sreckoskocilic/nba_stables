from fastapi import APIRouter, HTTPException
from helpers.common import CACHE_TTL, STATS_PROXY, cache
from helpers.logger import log_exceptions
from helpers.stats import get_current_season
from nba_api.stats.endpoints import leaguedashplayerstats, playergamelog

router = APIRouter()


@router.get("/api/season/doubles")
def get_season_doubles():
    """Get top 10 players by double-doubles and triple-doubles this season"""
    cached = cache.get("season_doubles")
    if cached:
        return cached

    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            per_mode_detailed="Totals",
            proxy=STATS_PROXY,
        )
        data = stats.get_dict()
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]

        h = {k: i for i, k in enumerate(headers)}

        dd_list = []
        td_list = []
        for row in rows:
            player_id = row[h["PLAYER_ID"]]
            name = row[h["PLAYER_NAME"]]
            team = row[h["TEAM_ABBREVIATION"]]
            dd2 = row[h["DD2"]] or 0
            td3 = row[h["TD3"]] or 0

            if dd2 > 0:
                dd_list.append(
                    {"name": name, "team": team, "playerId": player_id, "count": dd2}
                )
            if td3 > 0:
                td_list.append(
                    {"name": name, "team": team, "playerId": player_id, "count": td3}
                )

        dd_list.sort(key=lambda x: x["count"], reverse=True)
        td_list.sort(key=lambda x: x["count"], reverse=True)
        dd_list = dd_list[:30]
        td_list = td_list[:20]

        for i, p in enumerate(dd_list):
            p["rank"] = i + 1
        for i, p in enumerate(td_list):
            p["rank"] = i + 1

        result = {"doubleDoubles": dd_list, "tripleDoubles": td_list}
        cache.set("season_doubles", result, CACHE_TTL["season_leaders"])
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/season/triple-double-games/{player_id}")
def get_triple_double_games(player_id: int):
    """Get individual triple-double games for a player this season"""
    cache_key = f"td_games_{player_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        season = get_current_season()
        log = playergamelog.PlayerGameLog(
            player_id=player_id,
            season=season,
            proxy=STATS_PROXY,
        )
        data = log.get_dict()
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]

        h = {k: i for i, k in enumerate(headers)}
        player_name = ""

        games = []
        for row in rows:
            pts = row[h["PTS"]] or 0
            reb = row[h["REB"]] or 0
            ast = row[h["AST"]] or 0
            stl = row[h["STL"]] or 0
            blk = row[h["BLK"]] or 0

            double_digit = sum(1 for v in [pts, reb, ast, stl, blk] if v >= 10)
            if double_digit >= 3:
                games.append(
                    {
                        "date": row[h["GAME_DATE"]],
                        "matchup": row[h["MATCHUP"]],
                        "points": pts,
                        "rebounds": reb,
                        "assists": ast,
                        "steals": stl,
                        "blocks": blk,
                    }
                )

        result = {"playerId": player_id, "playerName": player_name, "games": games}
        cache.set(cache_key, result, CACHE_TTL["season_leaders"])
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
