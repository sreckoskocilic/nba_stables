import asyncio
import json
import re
from datetime import date

from constants import (
    BS_AST,
    BS_BLK,
    BS_FG3A,
    BS_FG3M,
    BS_FGA,
    BS_FGM,
    BS_FTA,
    BS_FTM,
    BS_MINUTES,
    BS_PF,
    BS_PLAYER_ID,
    BS_PTS,
    BS_REB,
    BS_STL,
    PGL_GAME_DATE,
    PGL_GAME_ID,
    PGL_MATCHUP,
)
from fastapi import APIRouter, HTTPException, Path, Query
from helpers.common import CACHE_TTL, STATS_PROXY, STATS_TIMEOUT, cache, executor
from helpers.decorators import route_error_handler
from helpers.logger import log_exceptions
from helpers.stats import (
    _reset_nba_stats_http_session,
    _today_et,
    count_double_digits,
    find_category_leaders,
    fix_encoding,
    get_cached_boxscore_v3,
    get_cached_live_boxscore,
    get_cached_scoreboard,
    get_current_season,
    load_players_dict,
    load_players_with_lower,
    parse_iso_minutes,
    parse_minutes,
    with_retry,
)
from nba_api.stats.endpoints import (
    commonplayerinfo,
    playercareerstats,
    playergamelog,
)

router = APIRouter()


def _normalize_game_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str)[:10]).isoformat()
    except ValueError:  # pragma: no cover
        return date_str


@router.get("/api/players/search")
@route_error_handler("Failed to search players")
async def search_players(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    """Search for players by name with pagination"""
    cleaned = " ".join(q.split())
    if not cleaned:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if not re.match(r"^[\w\s.'-]+$", cleaned):
        raise HTTPException(status_code=400, detail="Invalid characters in query")

    def _sync():
        players = load_players_with_lower()
        results = []
        query = cleaned.lower()

        total = 0

        for player, player_lower in players:
            if query in player_lower:
                if total >= offset and len(results) < limit:
                    results.append(
                        {"id": player[0], "name": player[1], "teamId": player[2]}
                    )
                total += 1

        return {"players": results, "total": total, "limit": limit, "offset": offset}

    return await asyncio.to_thread(_sync)


@router.get("/api/players/stats")
@route_error_handler("Failed to fetch player stats")
async def get_player_stats(
    ids: str = Query(...),
):
    """Get live stats for specific players"""
    players_ids = {
        int(pid) for pid in (p.strip() for p in ids.split(",")) if pid.isdigit()
    }

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
        try:
            relevant_game_ids = [game["gameId"] for game in get_cached_scoreboard()]
        except Exception as ex:
            log_exceptions(ex, "player_tracker_scoreboard")
            relevant_game_ids = []

        def fetch_player_boxscore(game_id):  # pragma: no cover
            try:
                return get_cached_live_boxscore(game_id)
            except json.JSONDecodeError:
                return None
            except Exception as ex:
                log_exceptions(ex, f"game_id={game_id}")
                return None

        # executor.map keeps submission overhead low and maintains order
        try:
            boxscores = list(
                executor.map(
                    fetch_player_boxscore, relevant_game_ids, timeout=STATS_TIMEOUT
                )
            )
        except TimeoutError as ex:
            log_exceptions(ex, "player_tracker_timeout")
            boxscores = []

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
                        minutes = parse_iso_minutes(stats["minutes"])

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

                        double_digits = count_double_digits(pts, reb, ast, stl, blk)

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

    result = await asyncio.to_thread(_sync)
    cache.set(cache_key, result, CACHE_TTL["player_stats"])
    return result


@router.get("/api/games/{game_id}/players")
@route_error_handler("Failed to fetch game players")
async def get_game_players(
    game_id: str = Path(..., pattern=r"^00[1245]\d{7}$"),
):
    """Get all player stats for a specific game with advanced metrics"""
    cache_key = f"game_players_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _sync():
        bs = get_cached_live_boxscore(game_id)
        game = bs["game"]

        teams = []
        all_active = []

        for team_key in ["homeTeam", "awayTeam"]:
            team = game[team_key]
            tricode = team["teamTricode"]
            periods = [
                {"period": p.get("period"), "score": p.get("score", 0)}
                for p in team.get("periods", [])
            ]
            team_data = {
                "name": f"{team['teamCity']} {team['teamName']}",
                "tricode": tricode,
                "score": team["score"],
                "periods": periods,
                "players": [],
            }

            for player in team["players"]:
                if player["status"] == "ACTIVE":
                    stats = player["statistics"]
                    minutes = parse_iso_minutes(stats["minutes"])

                    fgm = stats["fieldGoalsMade"]
                    fga = stats["fieldGoalsAttempted"]
                    tpm = stats["threePointersMade"]
                    ftm = stats["freeThrowsMade"]
                    fta = stats["freeThrowsAttempted"]
                    pts = stats["points"]
                    reb = stats["reboundsTotal"]
                    ast = stats["assists"]
                    stl = stats["steals"]
                    blk = stats["blocks"]
                    name = fix_encoding(player["name"])

                    team_data["players"].append(
                        {
                            "id": player["personId"],
                            "name": name,
                            "minutes": minutes,
                            "points": pts,
                            "rebounds": reb,
                            "offRebounds": stats["reboundsOffensive"],
                            "defRebounds": stats["reboundsDefensive"],
                            "assists": ast,
                            "steals": stl,
                            "blocks": blk,
                            "turnovers": stats["turnovers"],
                            "fouls": stats["foulsPersonal"],
                            "fg": f"{fgm}/{fga}",
                            "fgPct": round(fgm / fga, 3) if fga > 0 else 0,
                            "threePt": f"{tpm}/{stats['threePointersAttempted']}",
                            "ft": f"{ftm}/{fta}",
                            "ftPct": round(ftm / fta, 3) if fta > 0 else 0,
                        }
                    )

                    all_active.append(
                        {
                            "name": name,
                            "team": tricode,
                            "points": pts,
                            "rebounds": reb,
                            "assists": ast,
                            "steals": stl,
                            "blocks": blk,
                            "threePointers": tpm,
                        }
                    )

            # Sort by minutes played (descending)
            team_data["players"].sort(
                key=lambda x: parse_minutes(x["minutes"]),
                reverse=True,
            )
            teams.append(team_data)

        categories = [
            ("points", "PTS"),
            ("rebounds", "REB"),
            ("assists", "AST"),
            ("steals", "STL"),
            ("blocks", "BLK"),
            ("threePointers", "3 PT"),
        ]
        top_performers = {}
        if all_active:
            max_vals, max_entries = find_category_leaders(all_active, categories)
            for key, label in categories:
                top_performers[key] = {
                    "label": label,
                    "value": max_vals[key],
                    "players": [
                        {"name": p["name"], "team": p["team"]} for p in max_entries[key]
                    ],
                }

        arena_data = game.get("arena") or {}
        arena_name = arena_data.get("arenaName") or ""
        arena_city = arena_data.get("arenaCity") or ""
        arena = f"{arena_name}, {arena_city}".rstrip(", ") if arena_name else arena_city

        officials = []
        for o in game.get("officials") or []:
            name = o.get("name")
            if not name:
                first = o.get("firstName", "")
                last = o.get("familyName", "")
                name = f"{first} {last}".strip()
            if name:
                officials.append({"name": name})

        return {
            "gameId": game_id,
            "status": game["gameStatusText"],
            "arena": arena,
            "attendance": game.get("attendance") or 0,
            "officials": officials,
            "topPerformers": top_performers,
            "teams": teams,
        }

    result = await asyncio.to_thread(_sync)
    ttl = (
        CACHE_TTL["historical"]
        if result["status"].startswith("Final")
        else CACHE_TTL["boxscores"]
    )
    cache.set(cache_key, result, ttl)
    return result


@router.get("/api/players/{player_id}/last-n-games")
@route_error_handler("Failed to fetch last N games")
async def get_last_n_games_stats(
    player_id: int = Path(..., gt=0),
    n: int = Query(default=5, ge=1, le=15),
):
    """Get last N games stats for a specific player"""
    cache_key = f"last_n_games_{player_id}_{n}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    _not_found = object()
    _unavailable = object()

    def _sync():
        players_dict = load_players_dict()
        player = players_dict.get(player_id)
        if not player:
            return _not_found

        player_name = fix_encoding(player[1])

        # Load player game log (works for all players including traded/free agents)
        season = get_current_season()
        raw_cache_key = f"player_games_raw_{player_id}_{season}"
        game_rows_all = cache.get(raw_cache_key)
        if game_rows_all is None:
            try:
                pgl = with_retry(
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
                return _unavailable
            finally:
                _reset_nba_stats_http_session()
            game_rows_all = [
                [row[PGL_MATCHUP], row[PGL_GAME_ID], row[PGL_GAME_DATE]] for row in data
            ]
            cache.set(raw_cache_key, game_rows_all, CACHE_TTL["season_leaders"])

        if not game_rows_all:
            return _unavailable

        game_rows = game_rows_all[:n]

        def fetch_game_stats(gg):
            try:
                csp = get_cached_boxscore_v3(gg[1])
                player_stats_dict = {
                    x[BS_PLAYER_ID]: x for x in csp.player_stats.get_dict()["data"]
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
                            summary_map = dict(zip(hdrs, data[0]))
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

                if ss is not None and ss[BS_MINUTES] != "":
                    return {
                        "matchup": matchup_display,
                        "gameId": gg[1],
                        "minutes": ss[BS_MINUTES],
                        "points": ss[BS_PTS],
                        "fg": f"{ss[BS_FGM]}/{ss[BS_FGA]}",
                        "threePointers": f"{ss[BS_FG3M]}/{ss[BS_FG3A]}",
                        "ft": f"{ss[BS_FTM]}/{ss[BS_FTA]}",
                        "rebounds": ss[BS_REB],
                        "assists": ss[BS_AST],
                        "blocks": ss[BS_BLK],
                        "steals": ss[BS_STL],
                        "fouls": ss[BS_PF],
                        "dnp": False,
                    }
                else:
                    return {"matchup": matchup_display, "gameId": gg[1], "dnp": True}
            except Exception as ex:  # pragma: no cover
                log_exceptions(ex, f"player_id={player_id} game_id={gg[1]}")
                return None

        try:
            games = [
                r
                for r in executor.map(
                    fetch_game_stats, game_rows, timeout=STATS_TIMEOUT
                )
                if r is not None
            ]
        except TimeoutError as ex:
            log_exceptions(ex, f"player_games_timeout player_id={player_id}")
            games = []

        return {
            "playerId": player_id,
            "playerName": player_name,
            "games": games,
        }

    result = await asyncio.to_thread(_sync)
    if result is _not_found:
        raise HTTPException(status_code=404, detail="Player not found")
    if result is _unavailable:
        raise HTTPException(
            status_code=503, detail="Player game data temporarily unavailable"
        )
    cache.set(cache_key, result, CACHE_TTL["season_leaders"])
    return result


@router.get("/api/players/{player_id}/season-avg")
@route_error_handler("Failed to fetch season averages")
async def get_player_season_avg(player_id: int = Path(..., gt=0)):
    """Get current season averages for a player"""
    cache_key = f"season_avg_{player_id}_{get_current_season()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    _no_data = object()

    def _sync():
        try:
            career = with_retry(
                lambda: playercareerstats.PlayerCareerStats(
                    player_id=player_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
                )
            )
        finally:
            _reset_nba_stats_http_session()
        season_data = career.season_totals_regular_season.get_dict()
        headers = season_data["headers"]
        rows = season_data["data"]

        if not rows:
            return _no_data

        h = {k: i for i, k in enumerate(headers)}
        target_season = rows[-1][h["SEASON_ID"]]
        season_rows = [r for r in rows if r[h["SEASON_ID"]] == target_season]
        tot = [r for r in season_rows if r[h["TEAM_ABBREVIATION"]] == "TOT"]
        row = tot[0] if tot else season_rows[-1]
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

    result = await asyncio.to_thread(_sync)
    if result is _no_data:
        raise HTTPException(status_code=404, detail="No season data found")
    cache.set(cache_key, result, CACHE_TTL["season_leaders"])
    return result


def _calc_age(birthdate_str: str | None) -> int | None:
    if not birthdate_str:
        return None
    try:
        bd = date.fromisoformat(birthdate_str[:10])
        today = _today_et()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except ValueError:
        return None


@router.get("/api/players/{player_id}/profile")
@route_error_handler("Failed to fetch player profile")
async def get_player_profile(player_id: int = Path(..., gt=0)):
    """Get player profile: bio + career season-by-season."""
    cache_key = f"player_profile_{player_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    _not_found = object()

    def _fetch_bio():
        try:
            info = with_retry(
                lambda: commonplayerinfo.CommonPlayerInfo(
                    player_id=player_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
                )
            )
        finally:
            _reset_nba_stats_http_session()
        data = info.common_player_info.get_dict()
        if not data["data"]:
            return None
        h = {k: i for i, k in enumerate(data["headers"])}
        row = data["data"][0]

        def g(key):
            return row[h[key]] if key in h else None

        return {
            "name": fix_encoding(g("DISPLAY_FIRST_LAST") or ""),
            "team": g("TEAM_ABBREVIATION") or "",
            "teamName": f"{g('TEAM_CITY') or ''} {g('TEAM_NAME') or ''}".strip(),
            "jersey": g("JERSEY") or "",
            "position": g("POSITION") or "",
            "height": g("HEIGHT") or "",
            "weight": g("WEIGHT") or "",
            "age": _calc_age(g("BIRTHDATE")),
            "country": g("COUNTRY") or "",
            "draftYear": g("DRAFT_YEAR") or "",
            "draftNumber": g("DRAFT_NUMBER") or "",
            "school": g("SCHOOL") or "",
            "experience": g("SEASON_EXP"),
        }

    def _fetch_career():
        try:
            career = with_retry(
                lambda: playercareerstats.PlayerCareerStats(
                    player_id=player_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
                )
            )
        finally:
            _reset_nba_stats_http_session()
        season_dict = career.season_totals_regular_season.get_dict()
        sh = {k: i for i, k in enumerate(season_dict["headers"])}
        career_rows = []
        for row in season_dict["data"]:
            gp = row[sh["GP"]] or 1

            def avg(key):
                return round((row[sh[key]] or 0) / gp, 1)

            def pct(key):
                v = row[sh[key]]
                return round(v * 100, 1) if v else 0.0

            career_rows.append(
                {
                    "season": row[sh["SEASON_ID"]],
                    "team": row[sh["TEAM_ABBREVIATION"]] or "",
                    "gp": gp,
                    "minutes": avg("MIN"),
                    "points": avg("PTS"),
                    "rebounds": avg("REB"),
                    "assists": avg("AST"),
                    "steals": avg("STL"),
                    "blocks": avg("BLK"),
                    "fgPct": pct("FG_PCT"),
                    "fg3Pct": pct("FG3_PCT"),
                    "ftPct": pct("FT_PCT"),
                }
            )
        return career_rows

    def _sync():
        bio_future = executor.submit(_fetch_bio)
        career_future = executor.submit(_fetch_career)
        try:
            bio = bio_future.result(timeout=STATS_TIMEOUT)
        except Exception as ex:
            log_exceptions(ex, f"profile_bio player_id={player_id}")
            bio = None
        try:
            career = career_future.result(timeout=STATS_TIMEOUT)
        except Exception as ex:
            log_exceptions(ex, f"profile_career player_id={player_id}")
            career = []

        if bio is None and not career:
            return _not_found

        return {
            "playerId": player_id,
            "bio": bio or {},
            "career": career,
        }

    result = await asyncio.to_thread(_sync)
    if result is _not_found:
        raise HTTPException(status_code=404, detail="Player not found")
    cache.set(cache_key, result, CACHE_TTL["season_leaders"])
    return result
