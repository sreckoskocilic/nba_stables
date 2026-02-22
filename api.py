"""
NBA Stables REST API
FastAPI backend for live NBA statistics
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import requests
import uvicorn
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from nba_api.stats.endpoints import (
    boxscoreadvancedv3,
    boxscoretraditionalv3,
    leaguestandings,
    scoreboardv2,
)

from common.http import NBA_STATS_HEADERS

# SOCKS5 proxy for stats.nba.com (Cloudflare WARP on the host)
STATS_PROXY = os.environ.get("STATS_PROXY", None)

app = FastAPI(
    title="NBA Stables API",
    description="Live NBA statistics API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PLAYERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "players_with_teamid.json"
)
CBS_INJURIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cbs_injuries.json"
)


# Simple in-memory cache
class SimpleCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry["expires"]:
                return entry["data"]
            del self._cache[key]
        return None

    def set(self, key: str, data: Any, ttl_seconds: int):
        self._cache[key] = {"data": data, "expires": time.time() + ttl_seconds}

    def clear(self):
        self._cache.clear()


cache = SimpleCache()

# Cache TTLs (in seconds)
CACHE_TTL = {
    "scoreboard": 30,  # 30 seconds - live scores change frequently
    "boxscores": 60,  # 1 minute
    "leaders": 300,  # 5 minutes
    "standings": 3600,  # 1 hour - doesn't change often
    "player_stats": 30,  # 30 seconds
    "historical": 86400,  # 24 hours - days_offset >= 2 never changes
    "injuries": 7200,  # 2 hours - injury reports don't change often, avoid rate limits
}


# Helper functions
def get_date_str(days_offset: int = 0) -> str:
    target_date = date.today() - timedelta(days=days_offset)
    return target_date.strftime("%Y-%m-%d")


def get_display_date(days_offset: int = 0) -> str:
    target_date = date.today() - timedelta(days=days_offset)
    return target_date.strftime("%B %d, %Y")


def convert_et_to_cet(time_str: str) -> str:
    """Convert NBA game time from US/Eastern to CET (e.g. '7:00 pm ET' -> '23:00 CET')"""
    import re

    try:
        m = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str.strip(), re.IGNORECASE)
        if not m:
            return time_str
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        now = datetime.now()
        naive_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        et_dt = naive_dt.replace(tzinfo=ZoneInfo("US/Eastern"))
        cet_dt = et_dt.astimezone(ZoneInfo("Europe/Berlin"))
        return cet_dt.strftime("%H:%M CET")
    except Exception:
        return time_str


def reformat_player_minutes(total_seconds: int) -> str:
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def fix_encoding(s: str) -> str:
    """Fix nba_api mojibake: UTF-8 bytes decoded as Latin-1"""
    try:
        return s.encode("iso-8859-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def load_players_file():
    with open(PLAYERS_FILE, "r") as f:
        return json.load(f)


def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_dict = []
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv2.ScoreboardV2(
            game_date=target_date.strftime("%Y-%m-%d"),
            headers=NBA_STATS_HEADERS,
            proxy=STATS_PROXY,
        )
        games = sb.game_header.get_dict()
        for g in games["data"]:
            g_dict.append(g[2])  # game_id is at index 2
    except Exception:
        pass
    return list(set(g_dict))


def get_games_leaders_list(days_offset: int = 1):
    """Get games with their leaders"""
    g_dict = {}
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv2.ScoreboardV2(
            game_date=target_date.strftime("%Y-%m-%d"),
            headers=NBA_STATS_HEADERS,
            proxy=STATS_PROXY,
        )
        games = sb.game_header.get_dict()
        leaders = sb.team_leaders.get_dict()

        # Get game IDs
        for g in games["data"]:
            game_id = g[2]
            g_dict[game_id] = []

        # Leaders structure: GAME_ID, TEAM_ID, TEAM_CITY, TEAM_NICKNAME, TEAM_ABBREVIATION,
        # PTS_PLAYER_ID, PTS_PLAYER_NAME, PTS, REB_PLAYER_ID, REB_PLAYER_NAME, REB,
        # AST_PLAYER_ID, AST_PLAYER_NAME, AST
        for ld in leaders["data"]:
            game_id = ld[0]
            if game_id in g_dict:
                team_id = ld[1] if len(ld) > 1 else 0
                pts_player = fix_encoding(ld[6]) if len(ld) > 6 else ""
                pts = ld[7] if len(ld) > 7 else 0
                reb = ld[10] if len(ld) > 10 else 0
                ast = ld[13] if len(ld) > 13 else 0
                g_dict[game_id].append([pts_player, pts, reb, ast, team_id])
    except Exception:
        pass
    return g_dict


# API Endpoints


@app.get("/api/scoreboard")
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
                        "name": "{} {}".format(
                            home_team["teamCity"], home_team["teamName"]
                        ),
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
                        "name": "{} {}".format(
                            away_team["teamCity"], away_team["teamName"]
                        ),
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def fetch_single_boxscore(game_id, leaders_data):
    """Fetch boxscore for a single game (for parallel execution)"""
    try:
        bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id,
            headers=NBA_STATS_HEADERS,
            proxy=STATS_PROXY,
        )
        if bs_stats is None:
            return None

        team_stats = bs_stats.team_stats.get_dict()["data"]
        game_box = {"gameId": game_id, "teams": []}

        for i, team in enumerate(team_stats):
            leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
            team_id = team[1]  # TEAM_ID from boxscore
            ld = next((l for l in leaders_data if len(l) > 4 and l[4] == team_id), None)
            if ld:
                leader = {
                    "name": ld[0],
                    "points": ld[1],
                    "rebounds": ld[2],
                    "assists": ld[3],
                }

            game_box["teams"].append(
                {
                    "name": "{} {}".format(team[2], team[3]),
                    "score": team[-2],
                    "stats": {
                        "fg": "{}/{}".format(team[7], team[8]),
                        "fgPct": team[9],
                        "threePt": "{}/{}".format(team[10], team[11]),
                        "threePtPct": team[12],
                        "ft": "{}/{}".format(team[13], team[14]),
                        "ftPct": team[15],
                        "rebounds": team[18],
                        "offRebounds": team[16],
                        "assists": team[19],
                        "steals": team[20],
                        "blocks": team[21],
                        "turnovers": team[22],
                        "fouls": team[23],
                    },
                    "leader": leader,
                }
            )

        return game_box
    except Exception:
        return None


@app.get("/api/boxscores")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/players/search")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/players/stats")
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
            if (
                game["homeTeam"]["teamId"] in team_ids
                or game["awayTeam"]["teamId"] in team_ids
            ):
                try:
                    bs = boxscore.BoxScore(game_id=game["gameId"]).get_dict()
                except Exception:
                    continue

                for team_key in ["homeTeam", "awayTeam"]:
                    team = bs["game"][team_key]
                    for player in team["players"]:
                        if (
                            player["personId"] in player_ids
                            and player["status"] == "ACTIVE"
                        ):
                            stats = player["statistics"]
                            try:
                                minutes = reformat_player_minutes(
                                    int(
                                        parse_duration(stats["minutes"]).total_seconds()
                                    )
                                )
                            except Exception:
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leaders")
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
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_leaders_boxscore, game_ids)

        for bs in results:
            if bs is None:
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
                    "players": [
                        {"name": p["name"], "team": p["team"]} for p in top_players
                    ],
                }

        result = {"leaders": leaders, "date": get_display_date(days_offset)}
        ttl = CACHE_TTL["historical"] if days_offset >= 2 else CACHE_TTL["leaders"]
        cache.set(cache_key, result, ttl)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/standings")
def get_standings():
    """Get current NBA standings by conference"""
    cached = cache.get("standings")
    if cached:
        return cached

    try:
        standings = leaguestandings.LeagueStandings(
            headers=NBA_STATS_HEADERS,
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
                "name": team[4] or "",
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/players/advanced")
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
            if (
                game["homeTeam"]["teamId"] in team_ids
                or game["awayTeam"]["teamId"] in team_ids
            ):
                game_id = game["gameId"]

                # Get live boxscore for basic stats
                try:
                    bs = boxscore.BoxScore(game_id=game_id).get_dict()
                except Exception:
                    continue

                # Get advanced stats
                try:
                    adv = boxscoreadvancedv3.BoxScoreAdvancedV3(
                        game_id=game_id,
                        headers=NBA_STATS_HEADERS,
                        proxy=STATS_PROXY,
                    )
                    adv_players = adv.player_stats.get_dict()["data"]
                except Exception:
                    adv_players = []

                for team_key in ["homeTeam", "awayTeam"]:
                    team = bs["game"][team_key]
                    for player in team["players"]:
                        if (
                            player["personId"] in player_ids
                            and player["status"] == "ACTIVE"
                        ):
                            stats = player["statistics"]

                            # Find advanced stats for this player
                            adv_stat = next(
                                (p for p in adv_players if p[6] == player["personId"]),
                                None,
                            )

                            try:
                                minutes = reformat_player_minutes(
                                    int(
                                        parse_duration(stats["minutes"]).total_seconds()
                                    )
                                )
                            except Exception:
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
                            efg_pct = (
                                round((fgm + 0.5 * tpm) / fga, 3) if fga > 0 else 0
                            )

                            # Check for double-double / triple-double
                            double_digits = sum(
                                1 for x in [pts, reb, ast, stl, blk] if x >= 10
                            )

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
                                "plusMinus": (
                                    adv_stat[14]
                                    if adv_stat
                                    else stats.get("plusMinusPoints", 0)
                                ),
                                "isDoubleDouble": double_digits >= 2,
                                "isTripleDouble": double_digits >= 3,
                            }

                            results.append(player_result)

        return {"players": results}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid player IDs format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/doubledoubles")
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
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            boxscore_results = list(executor.map(fetch_dd_boxscore, game_ids))

        for bs in boxscore_results:
            if bs is None:
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/games/{game_id}/players")
def get_game_players(game_id: str):
    """Get all player stats for a specific game with advanced metrics"""
    try:
        bs = boxscore.BoxScore(game_id=game_id).get_dict()

        # Try to get advanced stats
        try:
            adv = boxscoreadvancedv3.BoxScoreAdvancedV3(
                game_id=game_id,
                headers=NBA_STATS_HEADERS,
                proxy=STATS_PROXY,
            )
            adv_players = adv.player_stats.get_dict()["data"]
        except Exception:
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
                        minutes = reformat_player_minutes(
                            int(parse_duration(stats["minutes"]).total_seconds())
                        )
                    except Exception:
                        minutes = "0:00"

                    # Find advanced stats
                    adv_stat = next(
                        (p for p in adv_players if p[6] == player["personId"]), None
                    )

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
                            "plusMinus": (
                                adv_stat[14]
                                if adv_stat
                                else stats.get("plusMinusPoints", 0)
                            ),
                            "efgPct": (
                                round((fgm + 0.5 * tpm) / fga, 3) if fga > 0 else 0
                            ),
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "date": get_display_date(0)}


def scrape_cbs_injuries():
    """Scrape CBS Sports and save to JSON file"""
    url = "https://www.cbssports.com/nba/injuries/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")
    team_sections = soup.find_all("div", class_="TableBaseWrapper")
    injuries_by_team = []

    for team_section in team_sections:
        team_name_el = team_section.find("div", class_="TeamLogoNameLockup-name")
        if not team_name_el:
            continue

        team_name = team_name_el.get_text(strip=True)
        players = []

        rows = team_section.find_all("tr", class_="TableBase-bodyTr")
        for row in rows:
            cells = row.find_all("td", class_="TableBase-bodyTd")
            name_el = row.find("span", class_="CellPlayerName--long")
            date_el = row.find("span", class_="CellGameDate")

            if name_el and len(cells) >= 5:
                players.append(
                    {
                        "name": name_el.get_text(strip=True),
                        "updated": date_el.get_text(strip=True) if date_el else "",
                        "injury": (
                            cells[3].get_text(strip=True) if len(cells) > 3 else ""
                        ),
                        "status": (
                            cells[4].get_text(strip=True) if len(cells) > 4 else ""
                        ),
                    }
                )

        if players:
            injuries_by_team.append({"team": team_name, "players": players})

    result = {
        "injuries": injuries_by_team,
        "source": "CBS Sports",
        "lastUpdated": get_display_date(0),
    }
    with open(CBS_INJURIES_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


@app.on_event("startup")
async def startup_scrape_cbs():
    """On startup, try to scrape CBS injuries (works locally, fails silently on prod)"""
    try:
        scrape_cbs_injuries()
    except Exception:
        pass


@app.get("/api/injuries")
def get_injuries():
    """Get NBA injury report from CBS Sports"""
    cached = cache.get("injuries")
    if cached:
        return cached

    try:
        if not os.path.exists(CBS_INJURIES_FILE):
            raise HTTPException(
                status_code=503, detail="CBS injuries data not available"
            )
        with open(CBS_INJURIES_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)
        cache.set("injuries", result, CACHE_TTL["injuries"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/sitemap.xml")
async def serve_sitemap():
    """Serve sitemap.xml"""
    sitemap_path = os.path.join(static_dir, "sitemap.xml")
    if os.path.exists(sitemap_path):
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="Sitemap not found")


@app.get("/about")
async def serve_about():
    """Serve the about page"""
    about_path = os.path.join(static_dir, "about.html")
    if os.path.exists(about_path):
        return FileResponse(about_path)
    raise HTTPException(status_code=404, detail="Page not found")


@app.get("/")
async def serve_frontend():
    """Serve the frontend"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "NBA Stables API", "docs": "/docs"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
