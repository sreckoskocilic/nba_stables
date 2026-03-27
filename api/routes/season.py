import asyncio
import heapq

from fastapi import APIRouter, Path, Query
from helpers.common import CACHE_TTL, STATS_PROXY, STATS_TIMEOUT, cache
from helpers.decorators import route_error_handler
from helpers.stats import (
    _with_retry,
    count_double_digits,
    find_category_leaders,
    fix_encoding,
    get_current_season,
    load_players_dict,
)
from nba_api.stats.endpoints import leaguedashplayerstats, leaguegamelog, playergamelog

router = APIRouter()


@router.get("/api/season/highs")
@route_error_handler("Failed to fetch season highs")
async def get_season_highs(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
):
    """Get season single-game highs for each statistical category"""
    resolved_season = season or get_current_season()
    cache_key = f"season_highs_{resolved_season}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        log = _with_retry(
            lambda: leaguegamelog.LeagueGameLog(
                season=resolved_season,
                player_or_team_abbreviation="P",
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            )
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

        players = []
        for row in rows:
            entry = {
                "name": fix_encoding(row[h["PLAYER_NAME"]]),
                "team": row[h["TEAM_ABBREVIATION"]],
                "date": row[h["GAME_DATE"]],
                "matchup": row[h["MATCHUP"]],
            }
            for col, key, _ in categories:
                entry[key] = row[h[col]] or 0
            players.append(entry)

        cat_keys = [(key, label) for _, key, label in categories]
        max_vals, max_entries = find_category_leaders(players, cat_keys)

        _display_fields = {"name", "team", "date", "matchup"}
        highs = {}
        for _, key, label in categories:
            highs[key] = {
                "label": label,
                "value": max_vals[key],
                "players": [
                    {k: v for k, v in e.items() if k in _display_fields}
                    for e in max_entries[key]
                ],
            }

        return {"highs": highs, "season": resolved_season}

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if season else CACHE_TTL["season_leaders"]
    cache.set(cache_key, result, ttl)
    return result


@router.get("/api/season/doubles")
@route_error_handler("Failed to fetch season doubles")
async def get_season_doubles(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
):
    """Get top 10 players by double-doubles and triple-doubles this season"""
    resolved_season = season or get_current_season()
    cache_key = f"season_doubles_{resolved_season}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        stats = _with_retry(
            lambda: leaguedashplayerstats.LeagueDashPlayerStats(
                per_mode_detailed="Totals",
                season=resolved_season,
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            )
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

        top_dd = heapq.nlargest(30, dd_list, key=lambda x: x["count"])
        top_td = heapq.nlargest(20, td_list, key=lambda x: x["count"])
        dd_list = [{**p, "rank": i + 1} for i, p in enumerate(top_dd)]
        td_list = [{**p, "rank": i + 1} for i, p in enumerate(top_td)]

        return {"doubleDoubles": dd_list, "tripleDoubles": td_list}

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if season else CACHE_TTL["season_leaders"]
    cache.set(cache_key, result, ttl)
    return result


@router.get("/api/season/triple-double-games/{player_id}")
@route_error_handler("Failed to fetch triple-double games")
async def get_triple_double_games(player_id: int = Path(..., gt=0)):
    """Get individual triple-double games for a player this season"""
    cache_key = f"td_games_{player_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        season = get_current_season()
        log = _with_retry(
            lambda: playergamelog.PlayerGameLog(
                player_id=player_id,
                season=season,
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            )
        )
        data = log.get_dict()
        headers = data["resultSets"][0]["headers"]
        rows = data["resultSets"][0]["rowSet"]

        h = {k: i for i, k in enumerate(headers)}
        players_dict = load_players_dict()
        player_row = players_dict.get(player_id) if players_dict else None
        player_name = fix_encoding(player_row[1]) if player_row else ""

        games = []
        for row in rows:
            pts = row[h["PTS"]] or 0
            reb = row[h["REB"]] or 0
            ast = row[h["AST"]] or 0
            stl = row[h["STL"]] or 0
            blk = row[h["BLK"]] or 0

            double_digit = count_double_digits(pts, reb, ast, stl, blk)
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

        return {"playerId": player_id, "playerName": player_name, "games": games}

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["historical"])
    return result
