from fastapi import APIRouter, HTTPException
from helpers.common import CACHE_TTL, STATS_PROXY, cache
from helpers.logger import log_exceptions
from helpers.stats import fix_encoding, get_current_season
from nba_api.stats.endpoints import leaguedashplayerstats, leaguegamelog, playergamelog

router = APIRouter()


@router.get("/api/season/highs")
def get_season_highs():
    """Get season single-game highs for each statistical category"""
    cached = cache.get("season_highs")
    if cached:
        return cached

    try:
        season = get_current_season()
        log = leaguegamelog.LeagueGameLog(
            season=season,
            player_or_team_abbreviation="P",
            proxy=STATS_PROXY,
        )
        data = log.get_dict()
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]
        h = {k: i for i, k in enumerate(headers)}

        categories = [
            ("PTS", "points", "Points"),
            ("REB", "rebounds", "Rebounds"),
            ("AST", "assists", "Assists"),
            ("BLK", "blocks", "Blocks"),
            ("STL", "steals", "Steals"),
            ("FG3M", "threePointers", "3-Pointers"),
            ("FGM", "fgm", "FG Made"),
            ("FTM", "ftm", "FT Made"),
            ("FTA", "fta", "FT Attempted"),
            ("OREB", "oreb", "Off. Rebounds"),
            ("DREB", "dreb", "Def. Rebounds"),
            ("TOV", "turnovers", "Turnovers"),
        ]

        max_vals = {key: 0 for _, key, _ in categories}
        max_entries = {key: [] for _, key, _ in categories}

        for row in rows:
            name = fix_encoding(row[h["PLAYER_NAME"]])
            team = row[h["TEAM_ABBREVIATION"]]
            game_date = row[h["GAME_DATE"]]
            matchup = row[h["MATCHUP"]]
            for col, key, _ in categories:
                val = row[h[col]] or 0
                if val > max_vals[key]:
                    max_vals[key] = val
                    max_entries[key] = [{"name": name, "team": team, "date": game_date, "matchup": matchup}]
                elif val == max_vals[key] and val != 0:
                    max_entries[key].append({"name": name, "team": team, "date": game_date, "matchup": matchup})

        highs = {}
        for _, key, label in categories:
            highs[key] = {
                "label": label,
                "value": max_vals[key],
                "players": max_entries[key],
            }

        result = {"highs": highs, "season": season}
        cache.set("season_highs", result, CACHE_TTL["season_leaders"])
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


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
