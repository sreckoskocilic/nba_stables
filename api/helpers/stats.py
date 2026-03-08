import json
import os
import re
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from helpers.common import CACHE_TTL, SEASON_CUTOFF_DAY, SEASON_CUTOFF_MONTH, STATS_PROXY, STATS_TIMEOUT, cache
from helpers.logger import log_exceptions
from nba_api.live.nba.endpoints import boxscore as live_boxscore
from nba_api.live.nba.endpoints import scoreboard as live_scoreboard
from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
    scoreboardv3,
)

PLAYERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../static/players_with_teamid.json"
)

_TZ_ET = ZoneInfo("US/Eastern")
_TZ_CET = ZoneInfo("Europe/Berlin")


# Helper functions
def _today_et() -> date:
    """Return today's date in US/Eastern (NBA schedule timezone)."""
    return datetime.now(_TZ_ET).date()


def scoreboard_date() -> date:
    """Return the NBA game date for the scoreboard.

    Before 13:00 CET show yesterday's games (last night's results),
    after 13:00 CET show today's upcoming games.
    """
    now_cet = datetime.now(_TZ_CET)
    if now_cet.hour < 13:
        return now_cet.date() - timedelta(days=1)
    return now_cet.date()


def _target_date(days_offset: int = 0) -> date:
    return _today_et() - timedelta(days=days_offset)


def get_display_date(days_offset: int = 0) -> str:
    return _target_date(days_offset).strftime("%B %d, %Y")


def get_current_season() -> str:
    today = _today_et()
    # NBA regular season starts mid-October
    year = today.year if (today.month > SEASON_CUTOFF_MONTH or (today.month == SEASON_CUTOFF_MONTH and today.day >= SEASON_CUTOFF_DAY)) else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def convert_et_to_cet(time_str: str) -> str:
    """Convert NBA game time from US/Eastern to CET (e.g. '7:00 pm ET' -> '23:00 CET')"""
    try:
        m = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str.strip(), re.IGNORECASE)
        if not m:
            return time_str
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        now_et = datetime.now(_TZ_ET)
        et_dt = now_et.replace(hour=hour, minute=minute, second=0, microsecond=0)
        cet_dt = et_dt.astimezone(_TZ_CET)
        return cet_dt.strftime("%H:%M CET")
    except Exception as ex:  # pragma: no cover
        log_exceptions(ex)
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


_players_cache = None
_players_cache_mtime = 0
_players_dict_cache = None
_players_lock = threading.Lock()


def load_players_file():  # pragma: no cover
    global _players_cache, _players_cache_mtime, _players_dict_cache
    with _players_lock:
        try:
            mtime = os.path.getmtime(PLAYERS_FILE)
        except OSError:
            mtime = 0
        if _players_cache is None or mtime != _players_cache_mtime:
            with open(PLAYERS_FILE, "r") as f:
                _players_cache = json.load(f)
            _players_dict_cache = {p[0]: p for p in _players_cache}
            _players_cache_mtime = mtime
        return _players_cache


def load_players_dict():  # pragma: no cover
    """Return {player_id: player_row} dict for O(1) lookups."""
    load_players_file()
    return _players_dict_cache


def get_cached_scoreboard():  # pragma: no cover
    """Return cached live ScoreBoard().games.data."""
    cached = cache.get("raw_scoreboard")
    if cached is not None:  # pragma: no cover
        return cached
    data = live_scoreboard.ScoreBoard().games.data
    cache.set("raw_scoreboard", data, CACHE_TTL["scoreboard"])
    return data


def get_cached_live_boxscore(game_id):  # pragma: no cover
    """Return a cached live BoxScore response dict for the given game_id."""
    cache_key = f"raw_live_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = live_boxscore.BoxScore(game_id=game_id).get_dict()
    status = data.get("game", {}).get("gameStatusText", "")
    ttl = CACHE_TTL["historical"] if "Final" in status else CACHE_TTL["boxscores"]
    cache.set(cache_key, data, ttl)
    return data


def get_cached_scoreboard_v3(days_offset: int = 1):
    """Return a cached ScoreboardV3 object for the given days_offset."""
    target_date = _today_et() - timedelta(days=days_offset)
    return get_scoreboard_v3_by_date(target_date, historical=days_offset >= 2)


def get_scoreboard_v3_by_date(game_date: date, historical: bool = False):
    """Return a cached ScoreboardV3 object for a specific date."""
    date_str = game_date.strftime("%Y-%m-%d")
    cache_key = f"raw_scoreboard_v3_{date_str}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached
    sb = scoreboardv3.ScoreboardV3(
        game_date=date_str,
        proxy=STATS_PROXY,
        timeout=STATS_TIMEOUT,
    )
    ttl = CACHE_TTL["historical"] if historical else CACHE_TTL["scoreboard"]
    cache.set(cache_key, sb, ttl)
    return sb


def find_category_leaders(items, categories):
    """Track per-category max values across a list of player dicts.

    items:      list of dicts, each containing numeric values for every category key
                plus any extra fields (name, team, etc.) to carry into results
    categories: list of (key, label) tuples

    Returns (max_vals dict, max_entries dict) where max_entries values are
    lists of the full item dicts that share the maximum value.
    """
    max_vals = {key: 0 for key, _ in categories}
    max_entries = {key: [] for key, _ in categories}
    for item in items:
        for key, _ in categories:
            val = item.get(key) or 0
            if val > max_vals[key]:
                max_vals[key] = val
                max_entries[key] = [item]
            elif val == max_vals[key] and val != 0:
                max_entries[key].append(item)
    return max_vals, max_entries


def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_set = set()
    try:
        sb = get_cached_scoreboard_v3(days_offset)
        games = sb.game_header.get_dict()
        for g in games["data"]:
            if g[2] > 1:
                g_set.add(g[0])
    except Exception as ex:
        log_exceptions(ex)
    return list(g_set)


def get_games_leaders_list(days_offset: int = 1):
    """Get games with their leaders"""
    g_dict = {}
    try:
        sb = get_cached_scoreboard_v3(days_offset)
        games = sb.game_header.get_dict()
        leaders = sb.game_leaders.get_dict()

        # Get game IDs
        for g in games["data"]:
            if g[2] > 1:
                game_id = g[0]
                g_dict[game_id] = []

        for ld in leaders["data"]:
            game_id = ld[0]
            if game_id in g_dict:
                team_id = ld[1]
                pts_player = fix_encoding(ld[4])
                pts = ld[9]
                reb = ld[10]
                ast = ld[11]
                g_dict[game_id].append([pts_player, pts, reb, ast, team_id])
    except Exception as ex:
        log_exceptions(ex)
    return g_dict


def get_cached_boxscore_v3(game_id):
    """Return a cached BoxScoreTraditionalV3 response for the given game_id."""
    cache_key = f"raw_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached
    bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(
        game_id=game_id,
        proxy=STATS_PROXY,
        timeout=STATS_TIMEOUT,
    )
    cache.set(cache_key, bs_stats, CACHE_TTL["historical"])
    return bs_stats


def fetch_single_boxscore(game_id, leaders_data):
    """Fetch boxscore for a single game (for parallel execution)"""
    game_box = {}
    try:
        bs_stats = get_cached_boxscore_v3(game_id)

        team_stats = bs_stats.team_stats.get_dict()["data"]
        game_box = {"gameId": game_id, "teams": []}
        leaders_by_team = {ld[4]: ld for ld in leaders_data if len(ld) > 4}

        # BoxScoreTraditionalV3 team_stats column indices
        _TEAM_ID = 1
        _CITY = 2
        _NAME = 3
        _FGM = 7
        _FGA = 8
        _FG_PCT = 9
        _TPM = 10
        _TPA = 11
        _TP_PCT = 12
        _FTM = 13
        _FTA = 14
        _FT_PCT = 15
        _OREB = 16
        _REB = 18
        _AST = 19
        _STL = 20
        _BLK = 21
        _TOV = 22
        _PF = 23
        _PTS = 24

        for i, team in enumerate(team_stats):
            leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
            team_id = team[_TEAM_ID]
            ld = leaders_by_team.get(team_id)
            if ld:
                leader = {
                    "name": ld[0],
                    "points": ld[1],
                    "rebounds": ld[2],
                    "assists": ld[3],
                }

            game_box["teams"].append(
                {
                    "name": f"{team[_CITY]} {team[_NAME]}",
                    "score": team[_PTS],
                    "stats": {
                        "fg": f"{team[_FGM]}/{team[_FGA]}",
                        "fgPct": team[_FG_PCT],
                        "threePt": f"{team[_TPM]}/{team[_TPA]}",
                        "threePtPct": team[_TP_PCT],
                        "ft": f"{team[_FTM]}/{team[_FTA]}",
                        "ftPct": team[_FT_PCT],
                        "rebounds": team[_REB],
                        "offRebounds": team[_OREB],
                        "assists": team[_AST],
                        "steals": team[_STL],
                        "blocks": team[_BLK],
                        "turnovers": team[_TOV],
                        "fouls": team[_PF],
                    },
                    "leader": leader,
                }
            )

        return game_box
    except Exception as ex:
        # Ignore exception as the game hasn't started yet (No response from boxscore endpoint for provided gameId)
        log_exceptions(ex)
        return game_box
