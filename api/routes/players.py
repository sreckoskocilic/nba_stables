from fastapi import APIRouter, HTTPException, Query
from helpers.common import CACHE_TTL, STATS_PROXY, cache, executor
from helpers.logger import log_exceptions
from helpers.stats import (
    fix_encoding,
    get_cached_boxscore_v3,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    load_players_dict,
    load_players_file,
    reformat_player_minutes,
)
from isodate import parse_duration
from nba_api.stats.endpoints import (
    cumestatsteamgames,
    playercareerstats,
)

router = APIRouter()


@router.get("/api/players/search")
def search_players(q: str = Query(..., min_length=2)):
    """Search for players by name"""
    try:
        players = load_players_file()
        results = []
        query = q.lower()

        for player in players:
            if query in player[1].lower():
                results.append(
                    {"id": player[0], "name": player[1], "teamId": player[2]}
                )

        return {"players": results[:20]}  # Limit to 20 results
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/stats")
def get_player_stats(ids: str = Query(..., description="Comma-separated player IDs")):
    """Get live stats for specific players"""
    players_ids = set()
    for pid in ids.split(","):
        if pid.strip().isdigit():
            players_ids.add(int(pid.strip()))

    if not players_ids:
        return {"players": []}

    cache_key = f"player_stats_{','.join(str(x) for x in sorted(players_ids))}"
    cached = cache.get(cache_key)
    if cached:  # pragma: no cover
        return cached

    try:
        players_dict = load_players_dict()

        # Get team IDs for requested players
        team_ids = set()
        for pid in players_ids:
            player = players_dict.get(pid)
            if player and player[2]:
                team_ids.add(player[2])

        results = []
        relevant_game_ids = [
            game["gameId"]
            for game in get_cached_scoreboard()
            if game["homeTeam"]["teamId"] in team_ids
            or game["awayTeam"]["teamId"] in team_ids
        ]

        def fetch_player_boxscore(game_id):  # pragma: no cover
            try:
                return get_cached_live_boxscore(game_id)
            except Exception:
                return None

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

        result = {"players": results}
        cache.set(cache_key, result, CACHE_TTL["player_stats"])
        return result
    except ValueError as err:  # pragma: no cover
        log_exceptions(err)
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/games/{game_id}/players")
def get_game_players(game_id: str):
    """Get all player stats for a specific game with advanced metrics"""
    cache_key = f"game_players_{game_id}"
    cached = cache.get(cache_key)
    if cached:  # pragma: no cover
        return cached

    try:
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
            team_data["players"].sort(key=lambda x: tuple(int(p) for p in x["minutes"].split(":")), reverse=True)
            teams.append(team_data)

        game_status = bs["game"]["gameStatusText"]
        result = {
            "gameId": game_id,
            "status": game_status,
            "teams": teams,
        }
        ttl = CACHE_TTL["historical"] if "Final" in game_status else 60
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/{player_id}/last-n-games")
def get_last_n_games_stats(
    player_id: int,
    n: int = Query(default=5, ge=1, le=15),
):
    """Get last N games stats for a specific player"""
    cache_key = f"last_n_games_{player_id}_{n}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        players_dict = load_players_dict()
        player = players_dict.get(player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        team_id = player[2]
        player_name = fix_encoding(player[1])

        cc = cumestatsteamgames.CumeStatsTeamGames(team_id=team_id, proxy=STATS_PROXY)
        game_rows = cc.cume_stats_team_games.get_dict()["data"][:n]

        def fetch_game_stats(gg):
            try:
                csp = get_cached_boxscore_v3(gg[1])
                player_stats_dict = {
                    x[6]: x for x in csp.player_stats.get_dict()["data"]
                }
                ss = player_stats_dict.get(player_id)
                if ss is not None and ss[14] != "":
                    return {
                        "matchup": gg[0],
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
                    return {"matchup": gg[0], "gameId": gg[1], "dnp": True}
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex)
                return None

        futures = [executor.submit(fetch_game_stats, gg) for gg in game_rows]

        def _get_result(f):
            try:
                return f.result(timeout=30)
            except TimeoutError:  # pragma: no cover
                return None

        games = [r for r in (_get_result(f) for f in futures) if r is not None]

        result = {
            "playerId": player_id,
            "playerName": player_name,
            "games": games,
        }
        cache.set(cache_key, result, CACHE_TTL["historical"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/{player_id}/season-avg")
def get_player_season_avg(player_id: int):
    """Get current season averages for a player"""
    cache_key = f"season_avg_{player_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        career = playercareerstats.PlayerCareerStats(
            player_id=player_id, proxy=STATS_PROXY
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

        result = {
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

        cache.set(cache_key, result, CACHE_TTL["season_leaders"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
