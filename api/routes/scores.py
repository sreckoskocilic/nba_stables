import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from constants import (
    ET_SUFFIX,
    GH_GAME_CODE,
    GH_GAME_ET,
    GH_GAME_ID,
    GH_STATUS_TEXT,
    GL_AST,
    GL_GAME_ID,
    GL_PLAYER_NAME,
    GL_PTS,
    GL_REB,
    GL_TEAM_ID,
    LS_GAME_ID,
    LS_SCORE,
    LS_TEAM_CITY,
    LS_TEAM_ID,
    LS_TEAM_NAME,
    LS_TRICODE,
    NBA_REGULAR_SEASON_GAMES,
    ST_AWAY_RECORD,
    ST_CITY,
    ST_CONF,
    ST_GAMES_BACK,
    ST_HOME_RECORD,
    ST_L10,
    ST_LOSSES,
    ST_NAME,
    ST_RANK,
    ST_STREAK,
    ST_TEAM_ID,
    ST_WINS,
    ST_WIN_PCT,
)
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
from helpers.decorators import route_error_handler
from helpers.logger import log_exceptions
from helpers.stats import (
    convert_et_to_cet,
    today_cet,
    with_retry,
    fetch_single_boxscore,
    find_category_leaders,
    fix_encoding,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    get_current_season,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
    get_scoreboard_v3_by_date,
    scoreboard_date,
)
from nba_api.stats.endpoints import leaguestandings, LeagueGameFinder

router = APIRouter()

_EMPTY_LEADER = {"name": "", "points": 0, "rebounds": 0, "assists": 0}

# Playoff status thresholds
PLAYOFF_SEED_IN = 6  # Seeds 1-6 get automatic playoff berth
PLAYOFF_SEED_PLAYIN = 10  # Seeds 7-10 make play-in tournament


def _sort_by_rank(teams: list) -> list:
    """Sort teams by rank, placing unranked teams at the end."""
    return sorted(teams, key=lambda x: x.get("rank") or 99)


@router.get("/api/dates")
@route_error_handler("Failed to fetch date labels")
async def get_date_labels():
    """Return display dates and game availability for day offsets 0-7"""
    cached = cache.get("dates")
    if cached is not None:  # pragma: no cover
        return cached

    async def _check_games(i):
        try:
            return bool(await asyncio.to_thread(get_games_list, i))
        except Exception as ex:
            log_exceptions(ex)
            return False

    has_games = list(
        await asyncio.gather(*[_check_games(i) for i in range(DAYS_OFFSET_MAX + 1)])
    )
    result = {
        "dates": [get_display_date(i) for i in range(DAYS_OFFSET_MAX + 1)],
        "hasGames": has_games,
    }
    cache.set("dates", result, CACHE_TTL["leaders"])
    return result


@router.get("/api/boxscores")
@route_error_handler("Failed to fetch boxscores")
async def get_boxscores(
    days_offset: int = Query(default=1, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get detailed box scores for games"""
    cache_key = f"boxscores_{days_offset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        leaders_by_game = get_games_leaders_list(days_offset)
        results = list(
            executor.map(
                fetch_single_boxscore,
                leaders_by_game.keys(),
                leaders_by_game.values(),
                timeout=STATS_TIMEOUT,
            )
        )
        boxscores_list = [r for r in results if r is not None]
        boxscores_list.sort(key=lambda x: x.get("gameId", ""))
        return {"boxscores": boxscores_list, "date": get_display_date(days_offset)}

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
    cache.set(cache_key, result, ttl)
    return result


@router.get("/api/scoreboard")
@route_error_handler("Failed to fetch scoreboard")
async def get_scoreboard():
    """Get live scoreboard with game results and leading scorers.

    Uses ScoreboardV3 to show today's scheduled games. Once any game has
    started (gameStatus >= 2), switches to the live scoreboard API for
    real-time scores and leaders.
    """
    cache_key = "scoreboard"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        sb_date = scoreboard_date()
        sb = get_scoreboard_v3_by_date(sb_date)
        games = _scoreboard_from_v3(sb)
        try:
            live_raw = get_cached_scoreboard()
            started_ids = {g["gameId"] for g in live_raw if g["gameStatus"] >= 2}
        except Exception as ex:  # pragma: no cover
            log_exceptions(ex, "scoreboard_live_merge")
            started_ids = set()
        if started_ids:
            try:
                live_by_id = {g["gameId"]: g for g in _scoreboard_from_live(live_raw)}
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex, "scoreboard_live_merge")
                live_by_id = {}
            games = [
                live_by_id.get(g["gameId"], g) if g["gameId"] in started_ids else g
                for g in games
            ]
        display_date = sb_date.strftime("%B %d, %Y")
        return {"games": games, "date": display_date}

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["scoreboard"])
    return result


def _scoreboard_from_live(raw_games) -> list[dict]:
    """Build scoreboard game list from the live API (in-progress / finished games)."""
    games = []
    for game in raw_games:
        home_team = game["homeTeam"]
        away_team = game["awayTeam"]
        home_leaders = game["gameLeaders"]["homeLeaders"]
        away_leaders = game["gameLeaders"]["awayLeaders"]

        status_text = game["gameStatusText"]
        if ET_SUFFIX in status_text:
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


def _build_team(row, team_id, game_id, leaders_by) -> dict:
    """Build a team dict for the scoreboard from a V3 line_score row."""
    ld = leaders_by.get((game_id, team_id))
    if ld:
        leader = {
            "name": fix_encoding(ld[GL_PLAYER_NAME]) if ld[GL_PLAYER_NAME] else "",
            "points": ld[GL_PTS] or 0,
            "rebounds": ld[GL_REB] or 0,
            "assists": ld[GL_AST] or 0,
        }
    else:
        leader = _EMPTY_LEADER
    if not row:
        return {
            "name": "",
            "tricode": "",
            "score": 0,
            "leader": leader,
        }
    return {
        "name": f"{row[LS_TEAM_CITY]} {row[LS_TEAM_NAME]}",
        "tricode": row[LS_TRICODE],
        "score": row[LS_SCORE] or 0,
        "leader": leader,
    }


def _scoreboard_from_v3(sb) -> list[dict]:
    """Build scoreboard game list from ScoreboardV3 (scheduled / pre-game)."""
    header = sb.game_header.get_dict()
    line_score = sb.line_score.get_dict()

    # Build tricode→(row, team_id) lookup grouped by game_id
    teams_by_game: dict[str, dict[str, tuple]] = {}
    for row in line_score["data"]:
        gid = row[LS_GAME_ID]
        teams_by_game.setdefault(gid, {})[row[LS_TRICODE]] = (row, row[LS_TEAM_ID])

    # Build leaders lookup
    leaders_data = sb.game_leaders.get_dict()
    leaders_by = {(ld[GL_GAME_ID], ld[GL_TEAM_ID]): ld for ld in leaders_data["data"]}

    games = []
    for g in header["data"]:
        game_id = g[GH_GAME_ID]
        game_code = g[GH_GAME_CODE]  # e.g. "20260307/ORLMIN"
        status_text = g[GH_STATUS_TEXT]
        if ET_SUFFIX in status_text:
            status_text = convert_et_to_cet(status_text)

        # Parse teams from gameCode: away(3) + home(3)
        teams_str = game_code.split("/")[1] if "/" in game_code else ""
        away_tri = teams_str[:3]
        home_tri = teams_str[3:]

        game_teams = teams_by_game.get(game_id, {})
        home_row, home_team_id = game_teams.get(home_tri, (None, None))
        away_row, away_team_id = game_teams.get(away_tri, (None, None))

        games.append(
            {
                "gameId": game_id,
                "status": status_text,
                "gameEt": g[GH_GAME_ET] or "",
                "homeTeam": _build_team(home_row, home_team_id, game_id, leaders_by),
                "awayTeam": _build_team(away_row, away_team_id, game_id, leaders_by),
            }
        )

    return games


@router.get("/api/leaders")
@route_error_handler("Failed to fetch daily leaders")
async def get_daily_leaders(
    days_offset: int = Query(default=1, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get daily leaders across statistical categories"""
    cache_key = f"leaders_{days_offset}"
    cached = cache.get(cache_key)
    if cached is not None:
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

        try:
            for bs in executor.map(
                fetch_leaders_boxscore, game_ids, timeout=STATS_TIMEOUT
            ):
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
        except TimeoutError as ex:
            log_exceptions(ex, "leaders_boxscore_timeout")

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

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["leaders"]
    cache.set(cache_key, result, ttl)
    return result


def _fetch_standings_teams() -> list:
    """Return raw standings team rows, cached to avoid duplicate LeagueStandings calls."""
    cached = cache.get("raw_standings")
    if cached is not None:  # pragma: no cover
        return cached
    standings = with_retry(
        lambda: leaguestandings.LeagueStandings(
            proxy=STATS_PROXY, timeout=STATS_TIMEOUT
        ).get_dict()
    )
    teams = standings["resultSets"][0]["rowSet"]
    cache.set("raw_standings", teams, CACHE_TTL["standings"] // 2)
    return teams


def _parse_team_row(team) -> dict:
    """Extract common fields from a raw LeagueStandings row."""
    win_pct = team[ST_WIN_PCT] if team[ST_WIN_PCT] is not None else 0
    team_info = TEAMS.get(team[ST_TEAM_ID])
    return {
        "teamId": team[ST_TEAM_ID],
        "rank": team[ST_RANK] or 0,
        "name": f"{team[ST_CITY]} {team[ST_NAME]}",
        "tricode": team_info[0] if team_info else (team[ST_CITY] or "")[:3].upper(),
        "wins": team[ST_WINS] or 0,
        "losses": team[ST_LOSSES] or 0,
        "winPct": round(win_pct, 3) if win_pct else 0,
        "gamesBack": team[ST_GAMES_BACK] if team[ST_GAMES_BACK] is not None else "-",
        "streak": team[ST_STREAK] or "-",
        "last10": team[ST_L10] or "0-0",
    }


@router.get("/api/standings")
@route_error_handler("Failed to fetch standings")
async def get_standings(request: Request):
    """Get current NBA standings by conference"""
    cache_key = "standings"
    cached, etag = cache.get_with_etag(cache_key)
    if cached is not None:
        client_etag = request.headers.get("If-None-Match")
        if client_etag and client_etag == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(content=cached, headers={"ETag": etag or ""})

    def _sync():
        teams = _fetch_standings_teams()

        east = []
        west = []

        for team in teams:
            team_data = _parse_team_row(team)
            team_data["homeRecord"] = team[ST_HOME_RECORD] or "0-0"
            team_data["awayRecord"] = team[ST_AWAY_RECORD] or "0-0"

            if team[ST_CONF] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        return {"east": _sort_by_rank(east), "west": _sort_by_rank(west)}

    result = await asyncio.to_thread(_sync)
    etag = cache.set_with_etag(cache_key, result, CACHE_TTL["standings"])
    return JSONResponse(content=result, headers={"ETag": etag})


def _fetch_playin_data(east_playin: list, west_playin: list) -> dict:
    """Derive play-in results from completed play-in games via LeagueGameFinder.

    Returns playinActual dict with east/west keys, each containing:
    - seed7TeamId: winner of the 7v8 game (once G1 is complete)
    - seed8TeamId: winner of G3 (once all 3 games are complete)
    - gameScores: {"<id1>_<id2>": {"<id1>": pts, "<id2>": pts}, ...}
    Falls back to empty dicts on any error or before play-in starts.
    """
    season = get_current_season()
    result: dict = {"east": {"gameScores": {}}, "west": {"gameScores": {}}}

    if not east_playin or not west_playin:
        return result

    try:
        data = LeagueGameFinder(
            season_nullable=season,
            season_type_nullable="PlayIn",
            league_id_nullable="00",
        ).get_dict()["resultSets"][0]

        headers = data["headers"]
        rows = data["rowSet"]
        team_id_idx = headers.index("TEAM_ID")
        pts_idx = headers.index("PTS")
        game_id_idx = headers.index("GAME_ID")

        games: dict = {}
        for row in rows:
            gid = row[game_id_idx]
            if gid not in games:
                games[gid] = {}
            games[gid][row[team_id_idx]] = row[pts_idx]

        def process_conf(conf_playin: list) -> dict:
            if len(conf_playin) < 4:
                return {"gameScores": {}}
            id_to_seed = {t["teamId"]: t["rank"] for t in conf_playin}
            all_ids = set(id_to_seed)
            conf: dict = {
                "gameScores": {},
                "initialSeeds": {str(tid): seed for tid, seed in id_to_seed.items()},
            }
            g1_winner = g1_loser = g2_winner = None

            for gid, team_pts in games.items():
                t_ids = set(team_pts)
                if not t_ids.issubset(all_ids) or len(t_ids) != 2:
                    continue
                s1, s2 = (id_to_seed[t] for t in sorted(t_ids))
                seeds = {s1, s2}
                sorted_ids = sorted(t_ids)
                key = f"{sorted_ids[0]}_{sorted_ids[1]}"
                conf["gameScores"][key] = {str(k): v for k, v in team_pts.items()}
                winner = max(team_pts, key=team_pts.get)
                loser = min(team_pts, key=team_pts.get)
                if seeds == {7, 8}:
                    g1_winner, g1_loser = winner, loser
                elif seeds == {9, 10}:
                    g2_winner, _g2_loser = winner, loser

            if g1_winner:
                conf["seed7TeamId"] = g1_winner
            if g1_loser:
                conf["g1LoserTeamId"] = g1_loser
            if g2_winner:
                conf["g2WinnerTeamId"] = g2_winner
            if g1_loser and g2_winner:
                g3_ids = {g1_loser, g2_winner}
                for team_pts in games.values():
                    if set(team_pts) == g3_ids:
                        conf["g3WinnerTeamId"] = max(team_pts, key=team_pts.get)
                        break

            return conf

        result["east"] = process_conf(east_playin)
        result["west"] = process_conf(west_playin)
    except Exception:
        pass

    return result


def _fetch_playoff_series_data(season: str) -> dict:
    """Return current playoff series win counts keyed by sorted team-ID pair.

    Uses only LeagueGameFinder (same as play-in). Infers series matchups by
    grouping team pairs that have played each other in the playoffs.
    Returns dict mapping "<lower_id>_<higher_id>" → {"<id1>": wins, "<id2>": wins}.
    Falls back to {} on any error or before playoffs start.
    """
    try:
        data = LeagueGameFinder(
            season_nullable=season,
            season_type_nullable="Playoffs",
            league_id_nullable="00",
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
        ).get_dict()["resultSets"][0]
        headers = data["headers"]
        gid_idx = headers.index("GAME_ID")
        tid_idx = headers.index("TEAM_ID")
        wl_idx = headers.index("WL")

        game_teams: dict = {}
        for row in data["rowSet"]:
            gid = row[gid_idx]
            game_teams.setdefault(gid, set()).add(row[tid_idx])

        pair_wins: dict = {}
        for row in data["rowSet"]:
            if row[wl_idx] != "W":
                continue
            gid = row[gid_idx]
            teams = game_teams.get(gid, set())
            if len(teams) != 2:
                continue
            pair = tuple(sorted(teams))
            key = f"{pair[0]}_{pair[1]}"
            entry = pair_wins.setdefault(key, {str(pair[0]): 0, str(pair[1]): 0})
            entry[str(row[tid_idx])] = entry.get(str(row[tid_idx]), 0) + 1

        return pair_wins
    except Exception:
        return {}


@router.get("/api/playoffs")
@route_error_handler("Failed to fetch playoff picture")
async def get_playoff_picture(request: Request):
    """Get current playoff picture with projected final records"""
    cache_key = "playoffs"
    cached, etag = cache.get_with_etag(cache_key)
    if cached is not None:
        client_etag = request.headers.get("If-None-Match")
        if client_etag and client_etag == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(content=cached, headers={"ETag": etag or ""})

    def _sync():
        teams = _fetch_standings_teams()

        east = []
        west = []

        for team in teams:
            team_data = _parse_team_row(team)
            win_pct = team_data["winPct"]
            wins = team_data["wins"]
            losses = team_data["losses"]
            rank = team_data["rank"]
            games_played = wins + losses

            games_remaining = max(0, NBA_REGULAR_SEASON_GAMES - games_played)
            projected_wins = round(wins + games_remaining * win_pct)
            projected_losses = NBA_REGULAR_SEASON_GAMES - projected_wins

            # Determine status
            if 1 <= rank <= PLAYOFF_SEED_IN:
                status = "in"
            elif rank <= PLAYOFF_SEED_PLAYIN:
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

            if team[ST_CONF] == "East":
                east.append(team_data)
            else:
                west.append(team_data)

        east_sorted = _sort_by_rank(east)
        west_sorted = _sort_by_rank(west)
        playin_actual = _fetch_playin_data(east_sorted[6:10], west_sorted[6:10])
        series_results = _fetch_playoff_series_data(get_current_season())

        return {
            "east": east_sorted,
            "west": west_sorted,
            "playinActual": playin_actual,
            "seriesResults": series_results,
        }

    result = await asyncio.to_thread(_sync)
    etag = cache.set_with_etag(cache_key, result, CACHE_TTL["playoffs"])
    return JSONResponse(content=result, headers={"ETag": etag})


@router.get("/api/doubledoubles")
@route_error_handler("Failed to fetch double-doubles")
async def get_double_doubles(
    days_offset: int = Query(default=0, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
):
    """Get players with double-doubles or triple-doubles for a given day"""
    cache_key = f"doubledoubles_{days_offset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        if days_offset == 0:
            sb_date = scoreboard_date()
            cet_today = today_cet()
            if sb_date == cet_today:
                game_ids = [g["gameId"] for g in get_cached_scoreboard()]
            else:
                offset = (cet_today - sb_date).days
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

        try:
            boxscore_results = list(
                executor.map(fetch_dd_boxscore, game_ids, timeout=STATS_TIMEOUT)
            )
        except TimeoutError as ex:
            log_exceptions(ex, "dd_boxscore_timeout")
            boxscore_results = []

        for bs in boxscore_results:
            if not bs:
                continue
            for team_key in ["homeTeam", "awayTeam"]:
                team = bs["game"][team_key]
                tricode = team["teamTricode"]

                for player in team["players"]:
                    if player["status"] == "ACTIVE":
                        stats = player["statistics"]
                        pts = stats.get("points") or 0
                        reb = stats.get("reboundsTotal") or 0
                        ast = stats.get("assists") or 0
                        stl = stats.get("steals") or 0
                        blk = stats.get("blocks") or 0

                        # Build player data with stats in one dict
                        player_data = {
                            "name": fix_encoding(player["name"]),
                            "team": tricode,
                            "points": pts,
                            "rebounds": reb,
                            "assists": ast,
                            "steals": stl,
                            "blocks": blk,
                        }

                        # Determine double/triple doubles
                        double_digit_cats = [
                            name
                            for name, val in (
                                ("points", pts),
                                ("rebounds", reb),
                                ("assists", ast),
                                ("steals", stl),
                                ("blocks", blk),
                            )
                            if val >= 10
                        ]
                        n_cats = len(double_digit_cats)

                        if n_cats >= 2:
                            player_data["categories"] = double_digit_cats
                            if n_cats >= 3:
                                triple_doubles.append(player_data)
                            else:
                                double_doubles.append(player_data)

        return {
            "tripleDoubles": triple_doubles,
            "doubleDoubles": double_doubles,
            "date": get_display_date(days_offset),
        }

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
    cache.set(cache_key, result, ttl)
    return result
