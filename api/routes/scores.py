import asyncio

from fastapi import APIRouter, Query
from nba_api.stats.endpoints import LeagueGameFinder, leaguestandings
from nba_api.stats.library.http import NBAStatsHTTP

from constants import (
    ET_SUFFIX,
    GH_GAME_CODE,
    GH_GAME_ET,
    GH_GAME_ID,
    GH_GAME_STATUS,
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
    ST_WIN_PCT,
    ST_WINS,
    STATUS_SCHEDULED,
)
from helpers.common import (
    CACHE_TTL,
    DAYS_OFFSET_MAX,
    DAYS_OFFSET_MIN,
    STATS_PROXY,
    STATS_TIMEOUT,
    TEAMS,
    cache,
)
from helpers.decorators import route_error_handler
from helpers.logger import log_exceptions
from helpers.stats import (
    _reset_nba_stats_http_session,
    _today_et,
    call_stats,
    convert_et_to_cet,
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
    get_wnba_current_season,
    scoreboard_date,
)

router = APIRouter()

_EMPTY_LEADER = {"name": "", "points": 0, "rebounds": 0, "assists": 0}

# Playoff status thresholds
PLAYOFF_SEED_IN = 6  # Seeds 1-6 get automatic playoff berth
PLAYOFF_SEED_PLAYIN = 10  # Seeds 7-10 make play-in tournament

# Series counts only change after a playoff game ends; cache longer than scoreboard.
_PLAYOFF_SERIES_TTL = 300

_TRICODE_TO_TEAM_ID = {tri: tid for tid, (tri, _) in TEAMS.items() if tid < 1611661000}


def _sort_by_rank(teams: list) -> list:
    """Sort teams by rank, placing unranked teams at the end."""
    return sorted(teams, key=lambda x: x.get("rank") or 99)


@router.get("/api/dates")
@route_error_handler("Failed to fetch date labels")
async def get_date_labels(league: str = "nba"):
    """Return display dates and game availability for day offsets 0-7"""
    league_id = "10" if league == "wnba" else "00"
    today_str = _today_et().isoformat()
    cache_key = f"dates_{league_id}_{today_str}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached

    def _sync():
        has_games = []
        for i in range(DAYS_OFFSET_MAX + 1):
            try:
                has_games.append(bool(get_games_list(i, league_id=league_id)))
            except Exception as ex:
                log_exceptions(ex)
                has_games.append(False)
        return {
            "dates": [get_display_date(i) for i in range(DAYS_OFFSET_MAX + 1)],
            "hasGames": has_games,
        }

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["leaders"])
    return result


@router.get("/api/boxscores")
@route_error_handler("Failed to fetch boxscores")
async def get_boxscores(
    days_offset: int = Query(default=1, ge=DAYS_OFFSET_MIN, le=DAYS_OFFSET_MAX),
    league: str = Query(default="nba"),
):
    """Get detailed box scores for games"""
    league_id = "10" if league == "wnba" else "00"
    cache_key = f"{league_id}:boxscores_{days_offset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        leaders_by_game = get_games_leaders_list(days_offset, league_id=league_id)
        boxscores_list = []
        for game_id, leaders_data in leaders_by_game.items():
            result = fetch_single_boxscore(game_id, leaders_data, league_id=league_id)
            if result is not None:
                boxscores_list.append(result)
        boxscores_list.sort(key=lambda x: x.get("gameId", ""))
        return {"boxscores": boxscores_list, "date": get_display_date(days_offset)}

    result = await asyncio.to_thread(_sync)
    ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["boxscores"]
    cache.set(cache_key, result, ttl)
    return result


@router.get("/api/scoreboard")
@route_error_handler("Failed to fetch scoreboard")
async def get_scoreboard(league: str = Query(default="nba")):
    """Get live scoreboard with game results and leading scorers.

    Uses ScoreboardV3 to show today's scheduled games. Once any game has
    started (gameStatus >= 2), switches to the live scoreboard API for
    real-time scores and leaders.
    """
    league_id = "10" if league == "wnba" else "00"
    sb_date = scoreboard_date()
    cache_key = f"{league_id}:scoreboard_{sb_date.isoformat()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        sb = get_scoreboard_v3_by_date(sb_date, league_id=league_id)
        games = _scoreboard_from_v3(sb)
        try:
            live_raw = get_cached_scoreboard(league_id=league_id)
            started_ids = {g["gameId"] for g in live_raw if g["gameStatus"] >= 2}
        except Exception:  # pragma: no cover
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
        if league_id == "00":
            try:
                series_wins, _ = _get_playoff_series_cached(
                    get_current_season(),
                )
                _attach_series_to_games(games, series_wins)
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex, "scoreboard_series_attach")
        display_date = sb_date.strftime("%B %d, %Y")
        return {"games": games, "date": display_date}

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["scoreboard"])
    return result


def _live_leader(ld: dict) -> dict:
    """Build a scoreboard leader dict from a live-API leaders entry."""
    return {
        "name": fix_encoding(ld["name"]) if ld["name"] else "",
        "points": ld["points"],
        "rebounds": ld["rebounds"],
        "assists": ld["assists"],
    }


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
                    "leader": _live_leader(home_leaders),
                },
                "awayTeam": {
                    "name": f"{away_team['teamCity']} {away_team['teamName']}",
                    "tricode": away_team["teamTricode"],
                    "score": away_team["score"],
                    "leader": _live_leader(away_leaders),
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
        leader = {**_EMPTY_LEADER}
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
        if g[GH_GAME_STATUS] == STATUS_SCHEDULED and g[GH_STATUS_TEXT] == "TBD":
            continue
        game_id = g[GH_GAME_ID]
        game_code = g[GH_GAME_CODE]  # e.g. "20260307/ORLMIN"
        status_text = g[GH_STATUS_TEXT]
        if ET_SUFFIX in status_text:
            status_text = convert_et_to_cet(status_text)

        teams_str = game_code.split("/")[1] if "/" in game_code else ""
        away_tri = teams_str[:3]
        home_tri = teams_str[3:6]

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
    league: str = Query(default="nba"),
):
    """Get daily leaders across statistical categories"""
    league_id = "10" if league == "wnba" else "00"
    cache_key = f"{league_id}:leaders_{days_offset}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        game_ids = get_games_list(days_offset, league_id=league_id)
        all_players = []

        def fetch_leaders_boxscore(gid):
            try:
                return get_cached_live_boxscore(gid, league_id=league_id)
            except Exception as ex:
                log_exceptions(ex)
                return {}

        boxscore_results = [fetch_leaders_boxscore(gid) for gid in game_ids]

        for bs in boxscore_results:
            if not bs:
                continue
            try:
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
            except Exception as ex:
                log_exceptions(ex, "leaders_boxscore_parse")

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
    standings = call_stats(leaguestandings.LeagueStandings).get_dict()
    teams = standings["resultSets"][0]["rowSet"]
    cache.set("raw_standings", teams, CACHE_TTL["standings"])
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


_WS_TEAM_ID = 2
_WS_CITY = 3
_WS_NAME = 4
_WS_RANK = 8
_WS_WINS = 13
_WS_LOSSES = 14
_WS_WIN_PCT = 15
_WS_HOME = 18
_WS_AWAY = 19
_WS_L10 = 20
_WS_STREAK = 37


def _fetch_wnba_standings_teams() -> list:
    cached = cache.get("raw_standings_wnba")
    if cached is not None:  # pragma: no cover
        return cached
    try:
        resp = NBAStatsHTTP().send_api_request(
            endpoint="leaguestandingsv3",
            parameters={
                "LeagueID": "10",
                "Season": get_wnba_current_season(),
                "SeasonType": "Regular Season",
            },
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
        )
        teams = resp.get_dict()["resultSets"][0]["rowSet"]
    finally:
        _reset_nba_stats_http_session()
    cache.set("raw_standings_wnba", teams, CACHE_TTL["standings"])
    return teams


def _parse_wnba_team_row(team) -> dict:
    win_pct = team[_WS_WIN_PCT] if team[_WS_WIN_PCT] is not None else 0
    team_info = TEAMS.get(team[_WS_TEAM_ID])
    return {
        "teamId": team[_WS_TEAM_ID],
        "rank": team[_WS_RANK] or 0,
        "name": f"{team[_WS_CITY]} {team[_WS_NAME]}",
        "tricode": team_info[0] if team_info else (team[_WS_CITY] or "")[:3].upper(),
        "wins": team[_WS_WINS] or 0,
        "losses": team[_WS_LOSSES] or 0,
        "winPct": round(win_pct, 3) if win_pct else 0,
        "streak": team[_WS_STREAK] or "-",
        "last10": team[_WS_L10] or "0-0",
        "homeRecord": team[_WS_HOME] or "0-0",
        "awayRecord": team[_WS_AWAY] or "0-0",
    }


def _wnba_sorted_teams() -> list:
    """Return WNBA standings rows parsed and sorted by rank, then winPct, wins."""
    teams = _fetch_wnba_standings_teams()
    return sorted(
        [_parse_wnba_team_row(t) for t in teams],
        key=lambda t: (t["rank"], -t["winPct"], -t["wins"]),
    )


@router.get("/api/standings")
@route_error_handler("Failed to fetch standings")
async def get_standings(league: str = Query(default="nba")):
    """Get current standings by conference"""
    league_id = "10" if league == "wnba" else "00"
    cache_key = f"{league_id}:standings"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        if league_id == "10":
            all_teams = _wnba_sorted_teams()
            if all_teams:
                top = all_teams[0]
                for t in all_teams:
                    diff = (
                        (top["wins"] - t["wins"]) + (t["losses"] - top["losses"])
                    ) / 2
                    t["gamesBack"] = "-" if diff == 0 else diff
            return {"all": all_teams}

        teams = _fetch_standings_teams()
        east, west = [], []
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
    cache.set(cache_key, result, CACHE_TTL["standings"])
    return result


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
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
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

            for team_pts in games.values():
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
    except Exception as ex:
        log_exceptions(ex, "playin_data_fetch")
    finally:
        _reset_nba_stats_http_session()

    return result


def _get_playoff_series_cached(
    season: str,
    league_id: str = "00",
) -> tuple[dict, dict]:
    """Cached wrapper around _fetch_playoff_series_data.

    Returns (pair_wins, pair_games). Series counts only update when a playoff
    game ends, so we cache longer than the scoreboard.
    """
    cache_key = f"playoff_series_{league_id}_{season}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    result = _fetch_playoff_series_data(season, league_id)
    cache.set(cache_key, result, _PLAYOFF_SERIES_TTL)
    return result


def _attach_series_to_games(games: list[dict], series_data: dict) -> None:
    """Mutate scoreboard `games` to include a `series` field on playoff games.

    `series` shape: {"home": <home_wins>, "away": <away_wins>}.
    Games whose team pair is not in series_data are left untouched.
    """
    if not series_data:
        return
    for game in games:
        home_tri = (game.get("homeTeam") or {}).get("tricode") or ""
        away_tri = (game.get("awayTeam") or {}).get("tricode") or ""
        home_id = _TRICODE_TO_TEAM_ID.get(home_tri)
        away_id = _TRICODE_TO_TEAM_ID.get(away_tri)
        if not home_id or not away_id:
            continue
        lo, hi = sorted((home_id, away_id))
        wins = series_data.get(f"{lo}_{hi}")
        if not wins:
            continue
        game["series"] = {
            "home": wins.get(str(home_id), 0),
            "away": wins.get(str(away_id), 0),
        }


def _fetch_playoff_series_data(
    season: str,
    league_id: str = "00",
) -> tuple[dict, dict]:
    """Return playoff series win counts and per-game details.

    Returns (pair_wins, pair_games) where both are keyed by sorted team-ID
    pair "<lower_id>_<higher_id>".
    pair_wins: {"<id1>": wins, "<id2>": wins}
    pair_games: [{"gameId", "date", "teams": {tid: {"pts", "wl", "matchup"}}}]
    Falls back to ({}, {}) on any error or before playoffs start.
    """
    try:
        data = LeagueGameFinder(
            season_nullable=season,
            season_type_nullable="Playoffs",
            league_id_nullable=league_id,
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
        ).get_dict()["resultSets"][0]
        headers = data["headers"]
        gid_idx = headers.index("GAME_ID")
        tid_idx = headers.index("TEAM_ID")
        wl_idx = headers.index("WL")
        pts_idx = headers.index("PTS")
        date_idx = headers.index("GAME_DATE")
        matchup_idx = headers.index("MATCHUP")

        game_teams: dict = {}
        for row in data["rowSet"]:
            gid = row[gid_idx]
            game_teams.setdefault(gid, set()).add(row[tid_idx])

        game_rows: dict = {}
        for row in data["rowSet"]:
            gid = row[gid_idx]
            game_rows.setdefault(gid, []).append(row)

        pair_wins: dict = {}
        pair_games: dict = {}

        for gid, rows in game_rows.items():
            teams = game_teams.get(gid, set())
            if len(teams) != 2:
                continue
            pair = tuple(sorted(teams))
            key = f"{pair[0]}_{pair[1]}"
            entry = pair_wins.setdefault(
                key,
                {str(pair[0]): 0, str(pair[1]): 0},
            )

            # Prefer WL, fall back to higher PTS. LeagueGameFinder lags on
            # setting WL for a just-finished game while scores are already in.
            winner_tid = next((r[tid_idx] for r in rows if r[wl_idx] == "W"), None)
            if winner_tid is None and len(rows) == 2:
                a, b = rows
                pa, pb = a[pts_idx], b[pts_idx]
                if (
                    isinstance(pa, (int, float))
                    and isinstance(pb, (int, float))
                    and pa != pb
                ):
                    winner_tid = a[tid_idx] if pa > pb else b[tid_idx]
            if winner_tid is not None:
                entry[str(winner_tid)] = entry.get(str(winner_tid), 0) + 1

            game_detail: dict = {"gameId": gid, "date": rows[0][date_idx], "teams": {}}
            for r in rows:
                game_detail["teams"][r[tid_idx]] = {
                    "pts": r[pts_idx],
                    "wl": r[wl_idx],
                    "matchup": r[matchup_idx],
                }
            pair_games.setdefault(key, []).append(game_detail)

        for games in pair_games.values():
            games.sort(key=lambda g: g["date"])

        return pair_wins, pair_games
    except Exception as ex:
        log_exceptions(ex, f"playoff_series_fetch season={season}")
        return {}, {}
    finally:
        _reset_nba_stats_http_session()


def _build_finals_data(
    east: list,
    west: list,
    pair_wins: dict,
    pair_games: dict,
) -> dict:
    """Build Finals section from playoff series data.

    Identifies the cross-conference pair (Finals) or conference champions
    if the Finals haven't started yet.
    """
    east_ids = {t["teamId"] for t in east}
    west_ids = {t["teamId"] for t in west}
    teams_by_id = {t["teamId"]: t for t in east + west}

    def _team_summary(team: dict) -> dict:
        return {
            "teamId": team["teamId"],
            "name": team["name"],
            "tricode": team.get("tricode", ""),
        }

    def _find_conf_champion(conf_ids: set) -> dict | None:
        wins_count: dict = {}
        for key, wins in pair_wins.items():
            t1, t2 = (int(x) for x in key.split("_"))
            if t1 not in conf_ids or t2 not in conf_ids:
                continue
            for tid in (t1, t2):
                if wins.get(str(tid), 0) >= 4:
                    wins_count[tid] = wins_count.get(tid, 0) + 1
        for tid, count in wins_count.items():
            if count >= 3:
                return teams_by_id.get(tid)
        return None

    finals_key = None
    for key in pair_wins:
        t1, t2 = (int(x) for x in key.split("_"))
        if (t1 in east_ids) != (t2 in east_ids):
            finals_key = key
            break

    if finals_key:
        t1, t2 = (int(x) for x in finals_key.split("_"))
        east_tid = t1 if t1 in east_ids else t2
        west_tid = t1 if t1 in west_ids else t2
        east_team = teams_by_id.get(east_tid)
        west_team = teams_by_id.get(west_tid)
        wins = pair_wins[finals_key]
        games_raw = pair_games.get(finals_key, [])
        games = []
        for g in games_raw:
            gt = g["teams"]
            tids = list(gt.keys())
            if len(tids) != 2:
                continue
            t_a, t_b = tids
            mu_a = gt[t_a].get("matchup", "")
            is_home_a = " vs. " in mu_a
            home_tid = t_a if is_home_a else t_b
            away_tid = t_b if is_home_a else t_a
            home_info = TEAMS.get(home_tid, ("???", "Unknown"))
            away_info = TEAMS.get(away_tid, ("???", "Unknown"))
            games.append(
                {
                    "gameId": g["gameId"],
                    "date": g["date"],
                    "home": {
                        "tricode": home_info[0],
                        "score": gt[home_tid]["pts"],
                    },
                    "away": {
                        "tricode": away_info[0],
                        "score": gt[away_tid]["pts"],
                    },
                }
            )
        return {
            "east": _team_summary(east_team) if east_team else None,
            "west": _team_summary(west_team) if west_team else None,
            "seriesScore": wins,
            "games": games,
        }

    east_champ = _find_conf_champion(east_ids)
    west_champ = _find_conf_champion(west_ids)
    return {
        "east": _team_summary(east_champ) if east_champ else None,
        "west": _team_summary(west_champ) if west_champ else None,
        "seriesScore": {},
        "games": [],
    }


@router.get("/api/playoffs")
@route_error_handler("Failed to fetch playoff picture")
async def get_playoff_picture(league: str = Query(default="nba")):
    """Get current playoff picture with projected final records"""
    league_id = "10" if league == "wnba" else "00"
    cache_key = f"{league_id}:playoffs"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        if league_id == "10":
            all_teams = _wnba_sorted_teams()
            for t in all_teams:
                t["status"] = "in" if 1 <= t["rank"] <= 8 else "out"
            series_results, _ = _get_playoff_series_cached(
                get_wnba_current_season(),
                league_id="10",
            )
            return {"all": all_teams, "seriesResults": series_results}

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
        series_results, series_games = _get_playoff_series_cached(get_current_season())

        finals = _build_finals_data(
            east_sorted,
            west_sorted,
            series_results,
            series_games,
        )

        return {
            "east": east_sorted,
            "west": west_sorted,
            "playinActual": playin_actual,
            "seriesResults": series_results,
            "finals": finals,
        }

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["playoffs"])
    return result
