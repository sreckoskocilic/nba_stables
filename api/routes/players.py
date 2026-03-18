import asyncio
import re
from datetime import date
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Path, Query
from helpers.common import CACHE_TTL, STATS_PROXY, STATS_TIMEOUT, cache, executor
from helpers.logger import log_exceptions
from helpers.stats import (
    _with_retry,
    fix_encoding,
    get_cached_boxscore_v3,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    get_current_season,
    load_players_dict,
    load_players_file,
    reformat_player_minutes,
)
from isodate import parse_duration
from nba_api.stats.endpoints import (
    playercareerstats,
    playergamelog,
)

router = APIRouter()


@lru_cache(maxsize=128)
def _normalize_game_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str)[:10]).isoformat()
    except Exception:  # pragma: no cover
        return date_str


@router.get("/api/players/search")
def search_players(q: str = Query(..., min_length=2, max_length=100)):
    """Search for players by name"""
    try:
        cleaned = " ".join(q.split())
        if not cleaned:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        if not re.match(r"^[\w\s.'-]+$", cleaned):
            raise HTTPException(status_code=400, detail="Invalid characters in query")

        players = load_players_file()
        results = []
        query = cleaned.lower()
        players_with_lower = [(p, p[1].lower()) for p in players]

        for player, player_lower in players_with_lower:
            if query in player_lower:
                results.append(
                    {"id": player[0], "name": player[1], "teamId": player[2]}
                )

        return {"players": results[:20]}  # Limit to 20 results
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to search players")


@router.get("/api/players/stats")
async def get_player_stats(
    ids: str = Query(..., description="Comma-separated player IDs"),
):
    """Get live stats for specific players"""
    ids_clean = ",".join(pid.strip() for pid in ids.split(",") if pid.strip())
    players_ids = {int(pid) for pid in ids_clean.split(",") if pid.isdigit()}

    if not players_ids:
        return {"players": []}

    if len(players_ids) > 25:
        raise HTTPException(status_code=400, detail="Too many player IDs (max 25)")

    ids_normalized = ",".join(str(x) for x in sorted(players_ids))
    cache_key = f"player_stats_{ids_normalized}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        results = []
        # Use all games on the scoreboard to avoid missing players with stale team IDs.
        # Cost is low (max ~15 games) and keeps traded/free-agent players visible.
        relevant_game_ids = [game["gameId"] for game in get_cached_scoreboard()]

        def fetch_player_boxscore(game_id):  # pragma: no cover
            try:
                return get_cached_live_boxscore(game_id)
            except Exception as ex:
                log_exceptions(ex, f"game_id={game_id}")
                return None

        # executor.map keeps submission overhead low and maintains order
        boxscores = list(executor.map(fetch_player_boxscore, relevant_game_ids))

        for bs in boxscores:
            if not bs:  # pragma: no cover
                continue
            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                for player in team["players"]:
                    if (
                        player["personId"] in players_ids
                        and player["status"] == "ACTIVE"
                    ):
                        stats = player["statistics"]
                        try:
                            minutes = reformat_player_minutes(
                                int(parse_duration(stats["minutes"]).total_seconds())
                            )
                        except Exception as ex:  # pragma: no cover
                            log_exceptions(ex)
                            minutes = "0:00"

                        pts = stats["points"]
                        fgm = stats["fieldGoalsMade"]
                        fga = stats["fieldGoalsAttempted"]
                        tpm = stats["threePointersMade"]
                        ftm = stats["freeThrowsMade"]
                        fta = stats["freeThrowsAttempted"]
                        reb = stats["reboundsTotal"]
                        ast = stats["assists"]
                        blk = stats["blocks"]
                        stl = stats["steals"]
                        tov = stats["turnovers"]

                        double_digits = sum(
                            1 for x in [pts, reb, ast, stl, blk] if x >= 10
                        )

                        results.append(
                            {
                                "id": player["personId"],
                                "name": fix_encoding(player["name"]),
                                "team": team["teamTricode"],
                                "minutes": minutes,
                                "points": pts,
                                "fg": f"{fgm}/{fga}",
                                "fgPct": round(fgm / fga, 3) if fga > 0 else 0,
                                "threePointers": f"{tpm}/{stats['threePointersAttempted']}",
                                "ft": f"{ftm}/{fta}",
                                "ftPct": round(ftm / fta, 3) if fta > 0 else 0,
                                "rebounds": reb,
                                "assists": ast,
                                "blocks": blk,
                                "steals": stl,
                                "turnovers": tov,
                                "fouls": stats["foulsPersonal"],
                                "isDoubleDouble": double_digits >= 2,
                                "isTripleDouble": double_digits >= 3,
                            }
                        )

        return {"players": results}

    try:
        result = await asyncio.to_thread(_sync)
        cache.set(cache_key, result, CACHE_TTL["player_stats"])
        return result
    except ValueError as err:  # pragma: no cover
        log_exceptions(err)
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch player stats")


@router.get("/api/games/{game_id}/players")
async def get_game_players(
    game_id: str = Path(..., pattern=r"^00[12]\d{7}$"),
):
    """Get all player stats for a specific game with advanced metrics"""
    cache_key = f"game_players_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        bs = get_cached_live_boxscore(game_id)

        teams = []

        for team_key in ["homeTeam", "awayTeam"]:
            team = bs["game"][team_key]
            team_data = {
                "name": f"{team['teamCity']} {team['teamName']}",
                "tricode": team["teamTricode"],
                "score": team["score"],
                "players": [],
            }

            for player in team["players"]:
                if player["status"] == "ACTIVE":
                    stats = player["statistics"]

                    try:
                        minutes = reformat_player_minutes(
                            int(parse_duration(stats["minutes"]).total_seconds())
                        )
                    except Exception as ex:  # pragma: no cover
                        log_exceptions(ex)
                        minutes = "0:00"

                    fgm = stats["fieldGoalsMade"]
                    fga = stats["fieldGoalsAttempted"]
                    tpm = stats["threePointersMade"]
                    ftm = stats["freeThrowsMade"]
                    fta = stats["freeThrowsAttempted"]

                    team_data["players"].append(
                        {
                            "id": player["personId"],
                            "name": fix_encoding(player["name"]),
                            "minutes": minutes,
                            "points": stats["points"],
                            "rebounds": stats["reboundsTotal"],
                            "offRebounds": stats["reboundsOffensive"],
                            "defRebounds": stats["reboundsDefensive"],
                            "assists": stats["assists"],
                            "steals": stats["steals"],
                            "blocks": stats["blocks"],
                            "turnovers": stats["turnovers"],
                            "fouls": stats["foulsPersonal"],
                            "fg": f"{fgm}/{fga}",
                            "fgPct": round(fgm / fga, 3) if fga > 0 else 0,
                            "threePt": f"{tpm}/{stats['threePointersAttempted']}",
                            "ft": f"{ftm}/{fta}",
                            "ftPct": round(ftm / fta, 3) if fta > 0 else 0,
                        }
                    )

            # Sort by minutes played (descending)
            team_data["players"].sort(
                key=lambda x: tuple(int(p) for p in x["minutes"].split(":")),
                reverse=True,
            )
            teams.append(team_data)

        game_status = bs["game"]["gameStatusText"]
        return {
            "gameId": game_id,
            "status": game_status,
            "teams": teams,
        }, game_status

    try:
        result, game_status = await asyncio.to_thread(_sync)
        ttl = (
            CACHE_TTL["historical"]
            if "Final" in game_status
            else CACHE_TTL["boxscores"]
        )
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch game players")


@router.get("/api/players/{player_id}/last-n-games")
async def get_last_n_games_stats(
    player_id: int = Path(..., gt=0),
    n: int = Query(default=5, ge=1, le=15),
):
    """Get last N games stats for a specific player"""
    cache_key = f"last_n_games_{player_id}_{n}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        players_dict = load_players_dict()
        player = players_dict.get(player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        player_name = fix_encoding(player[1])

        # Load player game log (works for all players including traded/free agents)
        raw_cache_key = f"player_games_raw_{player_id}"
        game_rows_all = cache.get(raw_cache_key)
        if game_rows_all is None:
            season = get_current_season()
            try:
                pgl = _with_retry(
                    lambda: playergamelog.PlayerGameLog(
                        player_id=player_id,
                        season=season,
                        proxy=STATS_PROXY,
                        timeout=STATS_TIMEOUT,
                    )
                )
                data = pgl.player_game_log.get_dict()["data"]
            except Exception as e:
                log_exceptions(e)
                raise HTTPException(
                    status_code=503, detail="Player game data temporarily unavailable"
                )
            # Columns: SEASON_ID, PLAYER_ID, GAME_ID, GAME_DATE, MATCHUP, ...
            _GAME_ID = 2
            _GAME_DATE = 3
            _MATCHUP = 4
            game_rows_all = [
                [row[_MATCHUP], row[_GAME_ID], row[_GAME_DATE]] for row in data
            ]
            cache.set(raw_cache_key, game_rows_all, CACHE_TTL["historical"])

        if not game_rows_all:
            raise HTTPException(
                status_code=503, detail="Player game data temporarily unavailable"
            )

        game_rows = game_rows_all[:n]

        def fetch_game_stats(gg):
            try:
                csp = get_cached_boxscore_v3(gg[1])
                player_stats_dict = {
                    x[6]: x for x in csp.player_stats.get_dict()["data"]
                }
                ss = player_stats_dict.get(player_id)

                # Derive game date for display (prefer data from inputs, then boxscore)
                game_date = _normalize_game_date(gg[2] if len(gg) > 2 else None)
                if not game_date:
                    try:
                        summary = csp.game_summary.get_dict()
                        hdrs = summary.get("headers", [])
                        data = summary.get("data", [[]])
                        if data and hdrs:
                            summary_map = {
                                hdrs[i]: data[0][i] for i in range(len(hdrs))
                            }
                            game_date = summary_map.get(
                                "GAME_DATE_EST"
                            ) or summary_map.get("GAME_DATE")
                            game_date = _normalize_game_date(game_date)
                    except Exception as ex:  # pragma: no cover
                        log_exceptions(ex)

                matchup_raw = gg[0]
                matchup_parts = matchup_raw.split(" ", 1)
                if (
                    not game_date
                    and len(matchup_parts) == 2
                    and len(matchup_parts[0]) == 10
                ):
                    game_date = matchup_parts[0]
                    matchup_display = matchup_parts[1]
                else:
                    matchup_display = matchup_raw

                if game_date:
                    matchup_display = f"{game_date} — {matchup_display}"

                if ss is not None and ss[14] != "":
                    return {
                        "matchup": matchup_display,
                        "gameId": gg[1],
                        "minutes": ss[14],
                        "points": ss[32],
                        "fg": f"{ss[15]}/{ss[16]}",
                        "threePointers": f"{ss[18]}/{ss[19]}",
                        "ft": f"{ss[21]}/{ss[22]}",
                        "rebounds": ss[26],
                        "assists": ss[27],
                        "blocks": ss[28],
                        "steals": ss[29],
                        "fouls": ss[31],
                        "dnp": False,
                    }
                else:
                    return {"matchup": matchup_display, "gameId": gg[1], "dnp": True}
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex, f"player_id={player_id} game_id={gg[1]}")
                return None

        futures = [executor.submit(fetch_game_stats, gg) for gg in game_rows]

        def _get_result(f):
            try:
                return f.result(timeout=30)
            except TimeoutError:  # pragma: no cover
                return None

        games = [r for r in (_get_result(f) for f in futures) if r is not None]

        return {
            "playerId": player_id,
            "playerName": player_name,
            "games": games,
        }

    try:
        result = await asyncio.to_thread(_sync)
        cache.set(cache_key, result, CACHE_TTL["historical"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch last N games")


@router.get("/api/players/{player_id}/season-avg")
async def get_player_season_avg(player_id: int = Path(..., gt=0)):
    """Get current season averages for a player"""
    cache_key = f"season_avg_{player_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        career = playercareerstats.PlayerCareerStats(
            player_id=player_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
        )
        season_data = career.season_totals_regular_season.get_dict()
        headers = season_data["headers"]
        rows = season_data["data"]

        if not rows:
            raise HTTPException(status_code=404, detail="No season data found")

        row = rows[-1]
        h = {k: i for i, k in enumerate(headers)}
        gp = row[h["GP"]] or 1

        def avg(key):
            return round((row[h[key]] or 0) / gp, 1)

        def pct(key):
            val = row[h[key]]
            return round(val * 100, 1) if val else 0.0

        return {
            "season": row[h["SEASON_ID"]],
            "gp": gp,
            "minutes": avg("MIN"),
            "points": avg("PTS"),
            "rebounds": avg("REB"),
            "assists": avg("AST"),
            "steals": avg("STL"),
            "blocks": avg("BLK"),
            "turnovers": avg("TOV"),
            "fouls": avg("PF"),
            "fgm": round((row[h["FGM"]] or 0) / gp, 1),
            "fga": round((row[h["FGA"]] or 0) / gp, 1),
            "fgPct": pct("FG_PCT"),
            "fg3m": round((row[h["FG3M"]] or 0) / gp, 1),
            "fg3a": round((row[h["FG3A"]] or 0) / gp, 1),
            "fg3Pct": pct("FG3_PCT"),
            "ftm": round((row[h["FTM"]] or 0) / gp, 1),
            "fta": round((row[h["FTA"]] or 0) / gp, 1),
            "ftPct": pct("FT_PCT"),
        }

    try:
        result = await asyncio.to_thread(_sync)
        cache.set(cache_key, result, CACHE_TTL["season_leaders"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch season averages")
