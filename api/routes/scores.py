from concurrent.futures import as_completed

from fastapi import APIRouter, HTTPException, Query
from helpers.common import CACHE_TTL, STATS_PROXY, cache, executor
from helpers.logger import log_exceptions
from helpers.stats import (
    convert_et_to_cet,
    fetch_single_boxscore,
    fix_encoding,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
)
from nba_api.stats.endpoints import leaguestandings

router = APIRouter()


@router.get("/api/dates")
def get_date_labels():
    """Return display dates for day offsets 0-7 so the frontend can label date buttons accurately"""
    return {"dates": [get_display_date(i) for i in range(8)]}


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
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/scoreboard")
def get_scoreboard():
    """Get live scoreboard with game results and leading scorers"""
    # Check cache first
    cached = cache.get("scoreboard")
    if cached:  # pragma: no cover
        return cached

    try:
        games = []
        for game in get_cached_scoreboard():
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
                        "name": f"{home_team['teamCity']} {home_team['teamName']}",
                        "tricode": home_team["teamTricode"],
                        "score": home_team["score"],
                        "leader": {
                            "name": fix_encoding(home_leaders["name"])
                            if home_leaders["name"]
                            else "",
                            "points": home_leaders["points"],
                            "rebounds": home_leaders["rebounds"],
                            "assists": home_leaders["assists"],
                        },
                    },
                    "awayTeam": {
                        "name": f"{away_team['teamCity']} {away_team['teamName']}",
                        "tricode": away_team["teamTricode"],
                        "score": away_team["score"],
                        "leader": {
                            "name": fix_encoding(away_leaders["name"])
                            if away_leaders["name"]
                            else "",
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
    except Exception as e:  # pragma: no cover
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
                return get_cached_live_boxscore(gid)
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex)
                return {}

        results = executor.map(fetch_leaders_boxscore, game_ids)

        for bs in results:
            if not bs:  # pragma: no cover
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
        if all_players:
            max_vals = {key: 0 for key, _ in categories}
            max_players = {key: [] for key, _ in categories}
            for p in all_players:
                for key, _ in categories:
                    val = p[key]
                    if val > max_vals[key]:
                        max_vals[key] = val
                        max_players[key] = [{"name": p["name"], "team": p["team"]}]
                    elif val == max_vals[key]:
                        max_players[key].append({"name": p["name"], "team": p["team"]})
            for key, label in categories:
                leaders[key] = {
                    "label": label,
                    "value": max_vals[key],
                    "players": max_players[key],
                }

        result = {"leaders": leaders, "date": get_display_date(days_offset)}
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["leaders"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


def _fetch_standings_teams():
    """Return raw standings team rows, cached to avoid duplicate LeagueStandings calls."""
    cached = cache.get("raw_standings")
    if cached is not None:  # pragma: no cover
        return cached
    standings = leaguestandings.LeagueStandings(proxy=STATS_PROXY).get_dict()
    teams = standings["resultSets"][0]["rowSet"]
    cache.set("raw_standings", teams, CACHE_TTL["standings"])
    return teams


@router.get("/api/standings")
def get_standings():
    """Get current NBA standings by conference"""
    cached = cache.get("standings")
    if cached:
        return cached

    try:
        teams = _fetch_standings_teams()

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
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/playoffs")
def get_playoff_picture():
    """Get current playoff picture with projected final records"""
    cached = cache.get("playoffs")
    if cached:  # pragma: no cover
        return cached

    try:
        teams = _fetch_standings_teams()

        TOTAL_GAMES = 82
        east = []
        west = []

        for team in teams:
            win_pct = team[14] if team[14] is not None else 0
            wins = team[12] or 0
            losses = team[13] or 0
            rank = team[7] or 0
            games_played = wins + losses
            games_remaining = max(0, TOTAL_GAMES - games_played)
            projected_wins = round(wins + games_remaining * win_pct)
            projected_losses = TOTAL_GAMES - projected_wins

            if rank <= 6:
                status = "in"
            elif rank <= 10:
                status = "play-in"
            else:
                status = "out"

            team_data = {
                "rank": rank,
                "name": f"{team[3]} {team[4]}",
                "tricode": (team[3] or "")[:3].upper(),
                "wins": wins,
                "losses": losses,
                "winPct": round(win_pct, 3) if win_pct else 0,
                "gamesBack": team[37] if team[37] is not None else "-",
                "streak": team[36] or "-",
                "last10": team[19] or "0-0",
                "gamesRemaining": games_remaining,
                "projectedWins": projected_wins,
                "projectedLosses": projected_losses,
                "status": status,
            }

            if team[5] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        east.sort(key=lambda x: x["rank"] or 99)
        west.sort(key=lambda x: x["rank"] or 99)

        result = {"east": east, "west": west}
        cache.set("playoffs", result, CACHE_TTL["standings"])
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/doubledoubles")
def get_double_doubles(days_offset: int = Query(default=0, ge=0, le=7)):
    """Get players with double-doubles or triple-doubles for a given day"""
    cache_key = f"doubledoubles_{days_offset}"
    cached = cache.get(cache_key)
    if cached:  # pragma: no cover
        return cached

    try:
        if days_offset == 0:
            # Use live scoreboard for today
            game_ids = [g["gameId"] for g in get_cached_scoreboard()]
        else:
            game_ids = get_games_list(days_offset)

        double_doubles = []
        triple_doubles = []

        def fetch_dd_boxscore(gid):
            try:
                return get_cached_live_boxscore(gid)
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex)
                return {}

        boxscore_results = list(executor.map(fetch_dd_boxscore, game_ids))

        for bs in boxscore_results:
            if not bs:  # pragma: no cover
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
                        double_digit_cats = [
                            k for k, v in categories.items() if v >= 10
                        ]
                        n_cats = len(double_digit_cats)

                        if n_cats >= 2:
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

                            if n_cats >= 3:
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
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
