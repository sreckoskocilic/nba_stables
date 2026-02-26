import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException, Query
from helpers.common import CACHE_TTL, SimpleCache
from helpers.logger import log_exceptions
from helpers.stats import (
    convert_et_to_cet,
    fetch_single_boxscore,
    fix_encoding,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
    load_players_file,
    reformat_player_minutes,
)
from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import boxscoreadvancedv3, leaguestandings

router = APIRouter()
STATS_PROXY = os.environ.get("STATS_PROXY", None)
cache = SimpleCache()

@router.get("/api/boxscores")
def get_boxscores(days_offset: int = Query(default=1, ge=0, le=7)):
    """Get detailed box scores for games"""
    cache_key = f"boxscores_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        # Use the helper function to get games with leaders
        leaders_by_game = get_games_leaders_list(days_offset)

        # Fetch all boxscores in parallel
        boxscores_list = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(fetch_single_boxscore, game_id, leaders_data): game_id
                for game_id, leaders_data in leaders_by_game.items()
                if leaders_data
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    boxscores_list.append(result)

        result = {"boxscores": boxscores_list, "date": get_display_date(days_offset)}
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


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
                except Exception as ex:
                    log_exceptions(ex)
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

@router.get("/api/scoreboard")
def get_scoreboard():
    """Get live scoreboard with game results and leading scorers"""
    # Check cache first
    cached = cache.get("scoreboard")
    if cached:
        return cached

    try:
        games = []
        for game in scoreboard.ScoreBoard().games.data:
            home_team = game["homeTeam"]
            away_team = game["awayTeam"]
            home_leaders = game["gameLeaders"]["homeLeaders"]
            away_leaders = game["gameLeaders"]["awayLeaders"]

            status_text = game["gameStatusText"]
            if "ET" in status_text:
                status_text = convert_et_to_cet(status_text)

            games.append(
                {
                    "gameId": game["gameId"],
                    "status": status_text,
                    "homeTeam": {
                        "name": "{} {}".format(home_team["teamCity"], home_team["teamName"]),
                        "tricode": home_team["teamTricode"],
                        "score": home_team["score"],
                        "leader": {
                            "name": fix_encoding(home_leaders["name"]) if home_leaders["name"] else "",
                            "points": home_leaders["points"],
                            "rebounds": home_leaders["rebounds"],
                            "assists": home_leaders["assists"],
                        },
                    },
                    "awayTeam": {
                        "name": "{} {}".format(away_team["teamCity"], away_team["teamName"]),
                        "tricode": away_team["teamTricode"],
                        "score": away_team["score"],
                        "leader": {
                            "name": fix_encoding(away_leaders["name"]) if away_leaders["name"] else "",
                            "points": away_leaders["points"],
                            "rebounds": away_leaders["rebounds"],
                            "assists": away_leaders["assists"],
                        },
                    },
                }
            )

        result = {"games": games, "date": get_display_date(0)}
        cache.set("scoreboard", result, CACHE_TTL["scoreboard"])
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/leaders")
def get_daily_leaders(days_offset: int = Query(default=1, ge=0, le=7)):
    """Get daily leaders across statistical categories"""
    cache_key = f"leaders_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        # Get game IDs using helper function
        game_ids = get_games_list(days_offset)

        all_players = []

        def fetch_leaders_boxscore(gid):
            try:
                return boxscore.BoxScore(game_id=gid).get_dict()
            except Exception as ex:
                log_exceptions(ex)
                return {}

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_leaders_boxscore, game_ids)

        for bs in results:
            if not bs:
                continue
            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                tricode = team["teamTricode"]

                for player in team["players"]:
                    if player["status"] == "ACTIVE":
                        stats = player["statistics"]
                        all_players.append(
                            {
                                "name": fix_encoding(player["name"]),
                                "team": tricode,
                                "points": stats["points"],
                                "rebounds": stats["reboundsTotal"],
                                "assists": stats["assists"],
                                "blocks": stats["blocks"],
                                "steals": stats["steals"],
                                "threePointers": stats["threePointersMade"],
                            }
                        )

        categories = [
            ("points", "Points"),
            ("rebounds", "Rebounds"),
            ("assists", "Assists"),
            ("blocks", "Blocks"),
            ("steals", "Steals"),
            ("threePointers", "3-Pointers"),
        ]

        leaders = {}
        for key, label in categories:
            if all_players:
                max_val = max(p[key] for p in all_players)
                top_players = [p for p in all_players if p[key] == max_val]
                leaders[key] = {
                    "label": label,
                    "value": max_val,
                    "players": [{"name": p["name"], "team": p["team"]} for p in top_players],
                }

        result = {"leaders": leaders, "date": get_display_date(days_offset)}
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["leaders"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/standings")
def get_standings():
    """Get current NBA standings by conference"""
    cached = cache.get("standings")
    if cached:
        return cached

    try:
        standings = leaguestandings.LeagueStandings(
            proxy=STATS_PROXY,
        ).get_dict()
        teams = standings["resultSets"][0]["rowSet"]

        east = []
        west = []

        for team in teams:
            # Indices based on API headers:
            # 4=TeamName, 5=Conference, 7=PlayoffRank, 12=WINS, 13=LOSSES,
            # 14=WinPCT, 17=HOME, 18=ROAD, 19=L10, 36=strCurrentStreak, 37=ConferenceGamesBack
            win_pct = team[14] if team[14] is not None else 0
            team_data = {
                "rank": team[7] or 0,
                "name": f"{team[3]} {team[4]}" or "",
                "tricode": (team[3] or "")[:3].upper(),  # TeamCity -> tricode
                "wins": team[12] or 0,
                "losses": team[13] or 0,
                "winPct": round(win_pct, 3) if win_pct else 0,
                "gamesBack": team[37] if team[37] is not None else "-",
                "streak": team[36] or "-",
                "last10": team[19] or "0-0",
                "homeRecord": team[17] or "0-0",
                "awayRecord": team[18] or "0-0",
            }

            if team[5] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        # Sort by rank
        east.sort(key=lambda x: x["rank"] or 99)
        west.sort(key=lambda x: x["rank"] or 99)

        result = {"east": east, "west": west}
        cache.set("standings", result, CACHE_TTL["standings"])
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/players/advanced")
def get_player_advanced_stats(
    ids: str = Query(..., description="Comma-separated player IDs"),
):
    """Get advanced stats for players including plus/minus, efficiency metrics"""
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
                game_id = game["gameId"]

                # Get live boxscore for basic stats
                try:
                    bs = boxscore.BoxScore(game_id=game_id).get_dict()
                except Exception as ex:
                    log_exceptions(ex)
                    continue

                # Get advanced stats
                try:
                    adv = boxscoreadvancedv3.BoxScoreAdvancedV3(
                        game_id=game_id,
                        proxy=STATS_PROXY,
                    )
                    adv_players = adv.player_stats.get_dict()["data"]
                except Exception as ex:
                    log_exceptions(ex)
                    adv_players = []

                for team_key in ["homeTeam", "awayTeam"]:
                    team = bs["game"][team_key]
                    for player in team["players"]:
                        if player["personId"] in player_ids and player["status"] == "ACTIVE":
                            stats = player["statistics"]

                            # Find advanced stats for this player
                            adv_stat = next(
                                (p for p in adv_players if p[6] == player["personId"]),
                                None,
                            )

                            try:
                                minutes = reformat_player_minutes(int(parse_duration(stats["minutes"]).total_seconds()))
                            except Exception as ex:
                                log_exceptions(ex)
                                minutes = "0:00"

                            # Calculate efficiency metrics
                            pts = stats["points"]
                            fgm = stats["fieldGoalsMade"]
                            fga = stats["fieldGoalsAttempted"]
                            tpm = stats["threePointersMade"]
                            fta = stats["freeThrowsAttempted"]
                            ftm = stats["freeThrowsMade"]
                            reb = stats["reboundsTotal"]
                            ast = stats["assists"]
                            stl = stats["steals"]
                            blk = stats["blocks"]
                            tov = stats["turnovers"]

                            # True Shooting %: PTS / (2 * (FGA + 0.44 * FTA))
                            ts_denom = 2 * (fga + 0.44 * fta)
                            ts_pct = round(pts / ts_denom, 3) if ts_denom > 0 else 0

                            # Effective FG%: (FGM + 0.5 * 3PM) / FGA
                            efg_pct = round((fgm + 0.5 * tpm) / fga, 3) if fga > 0 else 0

                            # Check for double-double / triple-double
                            double_digits = sum(1 for x in [pts, reb, ast, stl, blk] if x >= 10)

                            player_result = {
                                "id": player["personId"],
                                "name": fix_encoding(player["name"]),
                                "team": team["teamTricode"],
                                "minutes": minutes,
                                "points": pts,
                                "rebounds": reb,
                                "assists": ast,
                                "steals": stl,
                                "blocks": blk,
                                "turnovers": tov,
                                "fg": f"{fgm}/{fga}",
                                "fgPct": round(fgm / fga, 3) if fga > 0 else 0,
                                "threePt": f"{tpm}/{stats['threePointersAttempted']}",
                                "ft": f"{ftm}/{fta}",
                                "ftPct": round(ftm / fta, 3) if fta > 0 else 0,
                                "efgPct": efg_pct,
                                "tsPct": ts_pct,
                                "plusMinus": (adv_stat[14] if adv_stat else stats.get("plusMinusPoints", 0)),
                                "isDoubleDouble": double_digits >= 2,
                                "isTripleDouble": double_digits >= 3,
                            }

                            results.append(player_result)

        return {"players": results}
    except ValueError as err:
        log_exceptions(err)
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/doubledoubles")
def get_double_doubles(days_offset: int = Query(default=0, ge=0, le=7)):
    """Get players with double-doubles or triple-doubles for a given day"""
    cache_key = f"doubledoubles_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        if days_offset == 0:
            # Use live scoreboard for today
            game_ids = [g["gameId"] for g in scoreboard.ScoreBoard().games.data]
        else:
            game_ids = get_games_list(days_offset)

        double_doubles = []
        triple_doubles = []

        def fetch_dd_boxscore(gid):
            try:
                return boxscore.BoxScore(game_id=gid).get_dict()
            except Exception as ex:
                log_exceptions(ex)
                return {}

        with ThreadPoolExecutor(max_workers=10) as executor:
            boxscore_results = list(executor.map(fetch_dd_boxscore, game_ids))

        for bs in boxscore_results:
            if not bs:
                continue
            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                tricode = team["teamTricode"]

                for player in team["players"]:
                    if player["status"] == "ACTIVE":
                        stats = player["statistics"]
                        pts = stats["points"]
                        reb = stats["reboundsTotal"]
                        ast = stats["assists"]
                        stl = stats["steals"]
                        blk = stats["blocks"]

                        categories = {
                            "pts": pts,
                            "reb": reb,
                            "ast": ast,
                            "stl": stl,
                            "blk": blk,
                        }
                        double_digit_cats = [k for k, v in categories.items() if v >= 10]

                        if len(double_digit_cats) >= 2:
                            player_data = {
                                "name": fix_encoding(player["name"]),
                                "team": tricode,
                                "points": pts,
                                "rebounds": reb,
                                "assists": ast,
                                "steals": stl,
                                "blocks": blk,
                                "categories": double_digit_cats,
                            }

                            if len(double_digit_cats) >= 3:
                                triple_doubles.append(player_data)
                            else:
                                double_doubles.append(player_data)

        result = {
            "tripleDoubles": triple_doubles,
            "doubleDoubles": double_doubles,
            "date": get_display_date(days_offset),
        }
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))