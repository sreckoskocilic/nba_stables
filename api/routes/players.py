from fastapi import APIRouter, HTTPException, Query
from helpers.common import CACHE_TTL, STATS_PROXY, cache, executor
from helpers.logger import log_exceptions
from helpers.stats import (
    fix_encoding,
    load_players_dict,
    load_players_file,
    reformat_player_minutes,
)
from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
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
                results.append({"id": player[0], "name": player[1], "teamId": player[2]})

        return {"players": results[:20]}  # Limit to 20 results
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/stats")
def get_player_stats(ids: str = Query(..., description="Comma-separated player IDs")):
    """Get live stats for specific players"""

    try:
        players_ids = []
        for pid in ids.split(","):
            if pid.strip().isdigit():
                players_ids.append(int(pid.strip()))

        if not players_ids:
            return {"players": []}
        players_dict = load_players_dict()

        # Get team IDs for requested players
        team_ids = []
        for pid in players_ids:
            player = players_dict.get(pid)
            if player and player[2] and player[2] not in team_ids:
                team_ids.append(player[2])

        results = []
        relevant_game_ids = [
            game["gameId"]
            for game in scoreboard.ScoreBoard().games.data
            if game["homeTeam"]["teamId"] in team_ids or game["awayTeam"]["teamId"] in team_ids
        ]

        def fetch_player_boxscore(game_id):
            try:
                return boxscore.BoxScore(game_id=game_id).get_dict()
            except Exception:
                return None

        boxscores = list(executor.map(fetch_player_boxscore, relevant_game_ids))

        for bs in boxscores:
            if not bs:
                continue
            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                for player in team["players"]:
                    if player["personId"] in players_ids and player["status"] == "ACTIVE":
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
        adv_by_pid = {p[6]: p for p in adv_players} if adv_players else {}

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
                    adv_stat = adv_by_pid.get(player["personId"])

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
                csp = boxscoretraditionalv3.BoxScoreTraditionalV3(
                    game_id=gg[1], proxy=STATS_PROXY
                )
                player_stats = csp.player_stats.get_dict()["data"]
                ss = next((x for x in player_stats if x[6] == player_id), None)
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
            except Exception as ex:
                log_exceptions(ex)
                return None

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


@router.get("/api/players/{player_id}/season-avg")
def get_player_season_avg(player_id: int):
    """Get current season averages for a player"""
    cache_key = f"season_avg_{player_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        career = playercareerstats.PlayerCareerStats(player_id=player_id, proxy=STATS_PROXY)
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

        cache.set(cache_key, result, CACHE_TTL["standings"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
