import asyncio
from datetime import date
from concurrent.futures import as_completed

from fastapi import APIRouter, HTTPException, Query
from helpers.common import (
    CACHE_TTL,
    DAYS_OFFSET_MAX,
    DAYS_OFFSET_MIN,
    STATS_PROXY,
    STATS_TIMEOUT,
    TEAMS,
    cache,
    executor,
)
from helpers.logger import log_exceptions
from helpers.stats import (
    _with_retry,
    convert_et_to_cet,
    fetch_single_boxscore,
    find_category_leaders,
    fix_encoding,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
    get_scoreboard_v3_by_date,
    scoreboard_date,
)
from nba_api.stats.endpoints import leaguestandings

router = APIRouter()


@router.get("/api/dates")
async def get_date_labels():
    """Return display dates and game availability for day offsets 0-7"""
    cached = cache.get("dates")
    if cached:  # pragma: no cover
        return cached

    def _sync():
        def _has_games(i):
            try:
                return len(get_games_list(i)) > 0
            except Exception as ex:
                log_exceptions(ex)
                return False

        has_games = list(executor.map(_has_games, range(8)))
        return {"dates": [get_display_date(i) for i in range(8)], "hasGames": has_games}

    result = await asyncio.to_thread(_sync)
    cache.set("dates", result, CACHE_TTL["leaders"])
    return result


@router.get("/api/boxscores")
async def get_boxscores(
    days_offset: int = Query(default=1, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get detailed box scores for games"""
    cache_key = f"boxscores_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    def _sync():
        leaders_by_game = get_games_leaders_list(days_offset)
        boxscores_list = []
        futures = {
            executor.submit(fetch_single_boxscore, game_id, leaders_data): game_id
            for game_id, leaders_data in leaders_by_game.items()
        }
        for future in as_completed(futures):
            game_id = futures[future]
            try:
                result = future.result()
                if result:
                    boxscores_list.append(result)
            except Exception as ex:
                log_exceptions(ex, f"game_id={game_id}")
        boxscores_list.sort(key=lambda x: x.get("gameId", ""))
        return {"boxscores": boxscores_list, "date": get_display_date(days_offset)}

    try:
        result = await asyncio.to_thread(_sync)
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch boxscores")


@router.get("/api/scoreboard")
async def get_scoreboard():
    """Get live scoreboard with game results and leading scorers.

    Uses ScoreboardV3 to show today's scheduled games. Once any game has
    started (gameStatus >= 2), switches to the live scoreboard API for
    real-time scores and leaders.
    """
    cached = cache.get("scoreboard")
    if cached:
        return cached

    def _sync():
        sb_date = scoreboard_date()
        sb = get_scoreboard_v3_by_date(sb_date)
        header = sb.game_header.get_dict()
        started_ids = {g[0] for g in header["data"] if g[2] >= 2}
        games = _scoreboard_from_v3(sb)
        if started_ids:
            try:
                live_by_id = {g["gameId"]: g for g in _scoreboard_from_live()}
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex, "scoreboard_live_merge")
                live_by_id = {}
            games = [
                live_by_id.get(g["gameId"], g) if g["gameId"] in started_ids else g
                for g in games
            ]
        display_date = sb_date.strftime("%B %d, %Y")
        return {"games": games, "date": display_date}

    try:
        result = await asyncio.to_thread(_sync)
        cache.set("scoreboard", result, CACHE_TTL["scoreboard"])
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch scoreboard")


def _scoreboard_from_live():
    """Build scoreboard game list from the live API (in-progress / finished games)."""
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
                "gameEt": game.get("gameEt", ""),
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
    return games


def _build_team(row, team_id, game_id, leaders_by):
    """Build a team dict for the scoreboard from a V3 line_score row."""
    if not row:
        return {
            "name": "",
            "tricode": "",
            "score": 0,
            "leader": {"name": "", "points": 0, "rebounds": 0, "assists": 0},
        }
    ld = leaders_by.get((game_id, team_id))
    leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
    if ld:
        leader = {
            "name": fix_encoding(ld[4]) if ld[4] else "",
            "points": ld[9] or 0,
            "rebounds": ld[10] or 0,
            "assists": ld[11] or 0,
        }
    return {
        "name": f"{row[2]} {row[3]}",
        "tricode": row[4],
        "score": row[8] or 0,
        "leader": leader,
    }


def _scoreboard_from_v3(sb):
    """Build scoreboard game list from ScoreboardV3 (scheduled / pre-game)."""
    header = sb.game_header.get_dict()
    line_score = sb.line_score.get_dict()

    # Build team lookup from line_score: {(gameId, teamId): row}
    team_rows = {(row[0], row[1]): row for row in line_score["data"]}

    # Build leaders lookup
    leaders_data = sb.game_leaders.get_dict()
    leaders_by = {(ld[0], ld[1]): ld for ld in leaders_data["data"]}

    games = [None] * len(header["data"])
    for idx, g in enumerate(header["data"]):
        game_id = g[0]
        game_code = g[1]  # e.g. "20260307/ORLMIN"
        status_text = g[3]
        if "ET" in status_text:
            status_text = convert_et_to_cet(status_text)

        # Parse teams from gameCode: away(3) + home(3)
        teams_str = game_code.split("/")[1] if "/" in game_code else ""
        away_tri = teams_str[:3]
        home_tri = teams_str[3:]

        # Build tricode→(row, team_id) lookup for this game
        game_teams = {
            row[4]: (row, tid)
            for (gid, tid), row in team_rows.items()
            if gid == game_id
        }
        home_row, home_team_id = game_teams.get(home_tri, (None, None))
        away_row, away_team_id = game_teams.get(away_tri, (None, None))

        games[idx] = {
            "gameId": game_id,
            "status": status_text,
            "gameEt": g[7] or "",
            "homeTeam": _build_team(home_row, home_team_id, game_id, leaders_by),
            "awayTeam": _build_team(away_row, away_team_id, game_id, leaders_by),
        }

    return games


@router.get("/api/leaders")
async def get_daily_leaders(
    days_offset: int = Query(default=1, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get daily leaders across statistical categories"""
    cache_key = f"leaders_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    def _sync():
        game_ids = get_games_list(days_offset)
        all_players = []

        def fetch_leaders_boxscore(gid):
            try:
                return get_cached_live_boxscore(gid)
            except Exception as ex:
                log_exceptions(ex)
                return {}

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
        if all_players:
            max_vals, max_entries = find_category_leaders(all_players, categories)
            for key, label in categories:
                leaders[key] = {
                    "label": label,
                    "value": max_vals[key],
                    "players": [
                        {"name": p["name"], "team": p["team"]} for p in max_entries[key]
                    ],
                }
        return {"leaders": leaders, "date": get_display_date(days_offset)}

    try:
        result = await asyncio.to_thread(_sync)
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["leaders"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch daily leaders")


def _fetch_standings_teams():
    """Return raw standings team rows, cached to avoid duplicate LeagueStandings calls."""
    cached = cache.get("raw_standings")
    if cached is not None:  # pragma: no cover
        return cached
    standings = _with_retry(
        lambda: leaguestandings.LeagueStandings(
            proxy=STATS_PROXY, timeout=STATS_TIMEOUT
        ).get_dict()
    )
    teams = standings["resultSets"][0]["rowSet"]
    cache.set("raw_standings", teams, CACHE_TTL["standings"])
    return teams


def _parse_team_row(team):
    """Extract common fields from a raw LeagueStandings row."""
    # Indices: 2=TeamID, 3=CityName, 4=TeamName, 7=PlayoffRank, 12=WINS, 13=LOSSES,
    # 14=WinPCT, 19=L10, 36=strCurrentStreak, 37=ConferenceGamesBack
    win_pct = team[14] if team[14] is not None else 0
    team_info = TEAMS.get(team[2])
    return {
        "rank": team[7] or 0,
        "name": f"{team[3]} {team[4]}",
        "tricode": team_info[0] if team_info else (team[3] or "")[:3].upper(),
        "wins": team[12] or 0,
        "losses": team[13] or 0,
        "winPct": round(win_pct, 3) if win_pct else 0,
        "gamesBack": team[37] if team[37] is not None else "-",
        "streak": team[36] or "-",
        "last10": team[19] or "0-0",
    }


@router.get("/api/standings")
async def get_standings():
    """Get current NBA standings by conference"""
    cached = cache.get("standings")
    if cached:
        return cached

    def _sync():
        teams = _fetch_standings_teams()

        east = []
        west = []

        for team in teams:
            team_data = _parse_team_row(team)
            team_data["homeRecord"] = team[17] or "0-0"
            team_data["awayRecord"] = team[18] or "0-0"

            if team[5] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        east.sort(key=lambda x: x["rank"] or 99)
        west.sort(key=lambda x: x["rank"] or 99)

        return {"east": east, "west": west}

    try:
        result = await asyncio.to_thread(_sync)
        cache.set("standings", result, CACHE_TTL["standings"])
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch standings")


@router.get("/api/playoffs")
async def get_playoff_picture():
    """Get current playoff picture with projected final records"""
    cached = cache.get("playoffs")
    if cached:  # pragma: no cover
        return cached

    def _sync():
        teams = _fetch_standings_teams()

        TOTAL_GAMES = 82
        east = []
        west = []

        for team in teams:
            team_data = _parse_team_row(team)
            win_pct = team_data["winPct"]
            wins = team_data["wins"]
            losses = team_data["losses"]
            rank = team_data["rank"]
            games_played = wins + losses
            games_remaining = max(0, TOTAL_GAMES - games_played)
            projected_wins = round(wins + games_remaining * win_pct)
            projected_losses = TOTAL_GAMES - projected_wins

            if 1 <= rank <= 6:
                status = "in"
            elif rank <= 10:
                status = "play-in"
            else:
                status = "out"

            team_data.update(
                {
                    "gamesRemaining": games_remaining,
                    "projectedWins": projected_wins,
                    "projectedLosses": projected_losses,
                    "status": status,
                }
            )

            if team[5] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        east.sort(key=lambda x: x["rank"] or 99)
        west.sort(key=lambda x: x["rank"] or 99)

        return {"east": east, "west": west}

    try:
        result = await asyncio.to_thread(_sync)
        cache.set("playoffs", result, CACHE_TTL["standings"])
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch playoff picture")


@router.get("/api/doubledoubles")
async def get_double_doubles(
    days_offset: int = Query(default=0, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get players with double-doubles or triple-doubles for a given day"""
    cache_key = f"doubledoubles_{days_offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    def _sync():
        if days_offset == 0:
            sb_date = scoreboard_date()
            today_local = date.today()
            if sb_date == today_local:
                game_ids = [g["gameId"] for g in get_cached_scoreboard()]
            else:
                offset = (today_local - sb_date).days
                game_ids = get_games_list(offset if offset > 0 else 1)
        else:
            game_ids = get_games_list(days_offset)

        double_doubles = []
        triple_doubles = []

        def fetch_dd_boxscore(gid):
            try:
                return get_cached_live_boxscore(gid)
            except Exception as ex:
                log_exceptions(ex, f"doubledoubles gid={gid}")
                return {}

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

        return {
            "tripleDoubles": triple_doubles,
            "doubleDoubles": double_doubles,
            "date": get_display_date(days_offset),
        }

    try:
        result = await asyncio.to_thread(_sync)
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        log_exceptions(e)
        raise HTTPException(status_code=500, detail="Failed to fetch double-doubles")
