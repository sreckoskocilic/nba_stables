import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query
from helpers.common import CACHE_TTL, SimpleCache
from helpers.logger import log_exceptions
from helpers.stats import fix_encoding, load_players_file, reformat_player_minutes
from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
    cumestatsteamgames,
)

router = APIRouter()
STATS_PROXY = os.environ.get("STATS_PROXY", None)
cache = SimpleCache()

@router.get("/api/players/search")
def search_players(q: str = Query(..., min_length=2)):
    """Search for players by name"""
    try:
        players = load_players_file()
        results = []
        query = q.lower()

        for player in players:
            if query in player[1].lower():
                results.append({"id": player[0], "name": player[1], "teamId": player[2]})

        return {"players": results[:20]}  # Limit to 20 results
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/stats")
def get_player_stats(ids: str = Query(..., description="Comma-separated player IDs")):
    """Get live stats for specific players"""
    try:
        player_ids = [int(pid.strip()) for pid in ids.split(",")]
        players_data = load_players_file()

        # Get team IDs for requested players
        team_ids = []
        for pid in player_ids:
            player = next((p for p in players_data if p[0] == pid), None)
            if player and player[2] and player[2] not in team_ids:
                team_ids.append(player[2])

        results = []

        for game in scoreboard.ScoreBoard().games.data:
            if game["homeTeam"]["teamId"] in team_ids or game["awayTeam"]["teamId"] in team_ids:
                try:
                    bs = boxscore.BoxScore(game_id=game["gameId"]).get_dict()
                except Exception:
                    # Ignore exception as the game hasn't started yet (No response from boxscore endpoint for provided gameId)
                    continue

                for team_key in ["homeTeam", "awayTeam"]:
                    team = bs["game"][team_key]
                    for player in team["players"]:
                        if player["personId"] in player_ids and player["status"] == "ACTIVE":
                            stats = player["statistics"]
                            try:
                                minutes = reformat_player_minutes(int(parse_duration(stats["minutes"]).total_seconds()))
                            except Exception as ex:
                                log_exceptions(ex)
                                minutes = "0:00"

                            results.append(
                                {
                                    "id": player["personId"],
                                    "name": fix_encoding(player["name"]),
                                    "team": team["teamTricode"],
                                    "minutes": minutes,
                                    "points": stats["points"],
                                    "threePointers": "{}/{}".format(
                                        stats["threePointersMade"],
                                        stats["threePointersAttempted"],
                                    ),
                                    "rebounds": stats["reboundsTotal"],
                                    "assists": stats["assists"],
                                    "blocks": stats["blocks"],
                                    "steals": stats["steals"],
                                    "turnovers": stats["turnovers"],
                                }
                            )

        return {"players": results}
    except ValueError as err:
        log_exceptions(err)
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/games/{game_id}/players")
def get_game_players(game_id: str):
    """Get all player stats for a specific game with advanced metrics"""
    try:
        bs = boxscore.BoxScore(game_id=game_id).get_dict()

        # Try to get advanced stats
        try:
            adv = boxscoreadvancedv3.BoxScoreAdvancedV3(
                game_id=game_id,
                proxy=STATS_PROXY,
            )
            adv_players = adv.player_stats.get_dict()["data"]
        except Exception as ex:
            log_exceptions(ex)
            adv_players = []

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
                        minutes = reformat_player_minutes(int(parse_duration(stats["minutes"]).total_seconds()))
                    except Exception as ex:
                        log_exceptions(ex)
                        minutes = "0:00"

                    # Find advanced stats
                    adv_stat = next((p for p in adv_players if p[6] == player["personId"]), None)

                    fgm = stats["fieldGoalsMade"]
                    fga = stats["fieldGoalsAttempted"]
                    tpm = stats["threePointersMade"]
                    fta = stats["freeThrowsAttempted"]
                    ftm = stats["freeThrowsMade"]
                    pts = stats["points"]

                    ts_denom = 2 * (fga + 0.44 * fta)

                    team_data["players"].append(
                        {
                            "id": player["personId"],
                            "name": fix_encoding(player["name"]),
                            "minutes": minutes,
                            "points": pts,
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
                            "plusMinus": (adv_stat[14] if adv_stat else stats.get("plusMinusPoints", 0)),
                            "efgPct": (round((fgm + 0.5 * tpm) / fga, 3) if fga > 0 else 0),
                            "tsPct": round(pts / ts_denom, 3) if ts_denom > 0 else 0,
                        }
                    )

            # Sort by minutes played (descending)
            team_data["players"].sort(key=lambda x: x["minutes"], reverse=True)
            teams.append(team_data)

        return {
            "gameId": game_id,
            "status": bs["game"]["gameStatusText"],
            "teams": teams,
        }
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
        players_data = load_players_file()
        player = next((p for p in players_data if p[0] == player_id), None)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        team_id = player[2]
        player_name = fix_encoding(player[1])

        cc = cumestatsteamgames.CumeStatsTeamGames(team_id=team_id, proxy=STATS_PROXY)
        game_rows = cc.cume_stats_team_games.get_dict()["data"][:n]

        def fetch_game_stats(gg):
            try:
                csp = boxscoretraditionalv3.BoxScoreTraditionalV3(
                    game_id=gg[1], proxy=STATS_PROXY
                )
                player_stats = csp.player_stats.get_dict()["data"]
                ss = next((x for x in player_stats if x[6] == player_id), None)
                if ss is not None:
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
            except Exception as ex:
                log_exceptions(ex)
                return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_game_stats, gg) for gg in game_rows]
            games = [r for f in futures for r in [f.result()] if r is not None]

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