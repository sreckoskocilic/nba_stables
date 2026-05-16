import re
import threading
import time
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

import requests
from isodate import parse_duration

from constants import (
    CAP_DISPLAY_LAST_COMMA_FIRST,
    CAP_PERSON_ID,
    CAP_TEAM_ID,
    GH_GAME_ID,
    GH_GAME_STATUS,
    GL_AST,
    GL_GAME_ID,
    GL_PLAYER_NAME,
    GL_PTS,
    GL_REB,
    GL_TEAM_ID,
    STATUS_SCHEDULED,
)
from helpers.common import (
    CACHE_TTL,
    SEASON_CUTOFF_DAY,
    SEASON_CUTOFF_MONTH,
    STATS_PROXY,
    STATS_TIMEOUT,
    cache,
)
from helpers.logger import log_exceptions
from nba_api.live.nba.endpoints import boxscore as live_boxscore
from nba_api.live.nba.endpoints import scoreboard as live_scoreboard
from nba_api.live.nba.library.http import NBALiveHTTP
from nba_api.library.http import NBAHTTP
from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
    commonallplayers,
    scoreboardv3,
)
from nba_api.stats.library.http import NBAStatsHTTP

# CDN now requires Referer header (returns 403 without it)
NBALiveHTTP.headers["Referer"] = "https://www.nba.com/"


def _reset_nba_stats_http_session() -> None:
    """Close and discard nba_api's cached Session (NBAStatsHTTP / NBAHTTP).

    Reusing one keep-alive connection across multiple stats.nba.com calls can hang
    subsequent requests in the same process (see nba_api issue #633).
    """
    # Reset NBAHTTP (live) session
    try:
        sess = NBAHTTP._session
        if sess is not None:  # pragma: no cover
            sess.close()
    except Exception:  # pragma: no cover
        pass
    NBAHTTP._session = None

    # Reset NBAStatsHTTP session
    try:
        stats_sess = NBAStatsHTTP._session
        if stats_sess is not None:
            stats_sess.close()
    except Exception:  # pragma: no cover
        pass
    if "_session" in NBAStatsHTTP.__dict__:
        NBAStatsHTTP._session = None


_TZ_ET = ZoneInfo("US/Eastern")
_TZ_CET = ZoneInfo("Europe/Berlin")
_ET_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.IGNORECASE)


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


@lru_cache(maxsize=32)
def _display_date_cached(days_offset: int, today: date) -> str:
    return (today - timedelta(days=days_offset)).strftime("%B %d, %Y")


def get_display_date(days_offset: int = 0) -> str:
    return _display_date_cached(days_offset, _today_et())


def get_current_season() -> str:
    today = _today_et()
    # NBA regular season starts mid-October
    year = (
        today.year
        if (
            today.month > SEASON_CUTOFF_MONTH
            or (today.month == SEASON_CUTOFF_MONTH and today.day >= SEASON_CUTOFF_DAY)
        )
        else today.year - 1
    )
    return f"{year}-{str(year + 1)[-2:]}"


def get_wnba_current_season() -> str:
    today = _today_et()
    year = today.year if today.month >= 5 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def convert_et_to_cet(time_str: str) -> str:
    """Convert NBA game time from US/Eastern to CET (e.g. '7:00 pm ET' -> '23:00 CET')"""
    try:
        m = _ET_TIME_RE.match(time_str.strip())
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


def parse_iso_minutes(iso_str: str) -> str:
    """Parse an ISO-8601 duration (e.g. 'PT30M37.00S') to 'MM:SS'. Returns '0:00' on failure."""
    try:
        return reformat_player_minutes(int(parse_duration(iso_str).total_seconds()))
    except Exception as ex:  # pragma: no cover
        log_exceptions(ex)
        return "0:00"


def parse_minutes(mm_ss: str) -> tuple[int, int]:
    """Parse 'MM:SS' string to (minutes, seconds) tuple for sorting."""
    try:
        parts = mm_ss.split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return (0, 0)


@lru_cache(maxsize=1024)
def fix_encoding(s: str) -> str:
    """Fix nba_api mojibake: UTF-8 bytes decoded as Latin-1"""
    try:
        return s.encode("iso-8859-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def count_double_digits(pts: int, reb: int, ast: int, stl: int, blk: int) -> int:
    """Count how many of the five stat categories are in double digits (>= 10)."""
    return sum(1 for v in (pts, reb, ast, stl, blk) if v >= 10)


def with_retry(fn, attempts: int = 3, delay: float = 0.2):
    """Run `fn` with exponential backoff retry for transient errors.

    On transient errors (Timeout, ConnectionError), resets nba_api's cached
    session before backoff to mitigate nba_api issue #633.
    """
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            requests.RequestException,
        ) as ex:  # pragma: no cover - retry logic for network issues
            last_err = ex
            _reset_nba_stats_http_session()
            if i == attempts - 1:
                break
            time.sleep(delay * (2**i))
    if last_err:
        raise last_err


_players_cache: dict[str, list] = {}
_players_dict_cache: dict[str, dict] = {}
_players_cache_lower: dict[str, list] = {}
_players_cache_expires: dict[str, float] = {}
_players_lock = threading.Lock()


def _fetch_players(league_id: str = "00") -> list:
    """Fetch active players with their current team IDs from the NBA stats API."""
    try:
        is_current = 0 if league_id == "10" else 1
        cap = with_retry(
            lambda: commonallplayers.CommonAllPlayers(
                is_only_current_season=is_current,
                league_id=league_id,
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            )
        )
        data = cap.common_all_players.get_dict()
        players = []

        current_year = str(get_wnba_current_season()[:4]) if league_id == "10" else None

        for row in data.get("data", []):
            if is_current == 0 and row[3] != 1 and row[5] != current_year:
                continue
            person_id = row[CAP_PERSON_ID]
            name_raw = row[CAP_DISPLAY_LAST_COMMA_FIRST]

            # Convert "Last, First" to "First Last" for friendlier search
            if "," in name_raw:
                last, first = [part.strip() for part in name_raw.split(",", 1)]
                name = f"{first} {last}"
            else:
                name = name_raw

            team_id = row[CAP_TEAM_ID] if len(row) > CAP_TEAM_ID else None
            players.append([person_id, fix_encoding(name), team_id])

        return players
    finally:
        _reset_nba_stats_http_session()


def load_players_file(league_id: str = "00") -> list:  # pragma: no cover
    """Return cached list of active players fetched from the NBA stats API."""
    with _players_lock:
        if league_id in _players_cache and time.time() < _players_cache_expires.get(
            league_id, 0
        ):
            return _players_cache[league_id]

        try:
            _players_cache[league_id] = _fetch_players(league_id)
            _players_dict_cache[league_id] = {
                p[0]: p for p in _players_cache[league_id]
            }
            _players_cache_lower[league_id] = [
                (p, p[1].lower()) for p in _players_cache[league_id]
            ]
            _players_cache_expires[league_id] = time.time() + CACHE_TTL["players"]
        except Exception as ex:
            log_exceptions(ex)
            if _players_cache.get(league_id):
                _players_cache_expires[league_id] = time.time() + 300
                return _players_cache[league_id]
            _players_cache[league_id] = []
            _players_dict_cache[league_id] = {}
            _players_cache_lower[league_id] = []
            _players_cache_expires[league_id] = time.time() + 300

        return _players_cache[league_id]


def load_players_dict(league_id: str = "00") -> dict:  # pragma: no cover
    """Return {player_id: player_row} dict for O(1) lookups."""
    load_players_file(league_id)
    return _players_dict_cache.get(league_id, {})


def load_players_with_lower(league_id: str = "00") -> list:  # pragma: no cover
    """Return cached list of (player_row, lowercase_name) tuples."""
    load_players_file(league_id)
    return _players_cache_lower.get(league_id, [])


_WNBA_LIVE_BASE = "https://cdn.wnba.com/static/json/liveData"
_WNBA_LIVE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.wnba.com/",
    "Accept": "application/json",
}


def _fetch_wnba_live_scoreboard() -> list:  # pragma: no cover
    url = f"{_WNBA_LIVE_BASE}/scoreboard/todaysScoreboard_10.json"
    r = requests.get(
        url,
        headers=_WNBA_LIVE_HEADERS,
        timeout=STATS_TIMEOUT,
        proxies=({"https": STATS_PROXY} if STATS_PROXY else None),
    )
    r.raise_for_status()
    return r.json()["scoreboard"]["games"]


def get_cached_scoreboard(league_id: str = "00") -> Any:  # pragma: no cover
    """Return cached live ScoreBoard().games.data."""
    sb_key = f"raw_scoreboard_{league_id}_{scoreboard_date().isoformat()}"
    cached = cache.get(sb_key)
    if cached is not None:  # pragma: no cover
        return cached
    try:
        if league_id == "10":
            data = with_retry(_fetch_wnba_live_scoreboard)
        else:

            def _fetch():
                sb = live_scoreboard.ScoreBoard(
                    proxy=STATS_PROXY, timeout=STATS_TIMEOUT, get_request=False
                )
                sb.endpoint_url = f"scoreboard/todaysScoreboard_{league_id}.json"
                sb.get_request()
                return sb.games.data

            data = with_retry(_fetch)
    finally:
        _reset_nba_stats_http_session()
    cache.set(sb_key, data, CACHE_TTL["scoreboard"])
    return data


def _fetch_wnba_live_boxscore(game_id: str) -> dict:  # pragma: no cover
    url = f"{_WNBA_LIVE_BASE}/boxscore/boxscore_{game_id}.json"
    r = requests.get(
        url,
        headers=_WNBA_LIVE_HEADERS,
        timeout=STATS_TIMEOUT,
        proxies=({"https": STATS_PROXY} if STATS_PROXY else None),
    )
    r.raise_for_status()
    return r.json()


def get_cached_live_boxscore(
    game_id: str,
    league_id: str = "00",
) -> dict | None:  # pragma: no cover
    """Return a cached live BoxScore response dict for the given game_id."""
    cache_key = f"raw_live_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        if league_id == "10":
            data = with_retry(lambda: _fetch_wnba_live_boxscore(game_id))
        else:
            data = with_retry(
                lambda: live_boxscore.BoxScore(
                    game_id=game_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
                ).get_dict(),
            )
    finally:
        _reset_nba_stats_http_session()
    status = data.get("game", {}).get("gameStatusText", "")
    ttl = (
        CACHE_TTL["historical"]
        if status.startswith("Final")
        else CACHE_TTL["boxscores"]
    )
    cache.set(cache_key, data, ttl)
    return data


def get_cached_scoreboard_v3(days_offset: int = 1, league_id: str = "00") -> Any:
    """Return a cached ScoreboardV3 object for the given days_offset."""
    target_date = _today_et() - timedelta(days=days_offset)
    return get_scoreboard_v3_by_date(
        target_date, historical=days_offset >= 2, league_id=league_id
    )


def get_scoreboard_v3_by_date(
    game_date: date, historical: bool = False, league_id: str = "00"
) -> Any:
    """Return a cached ScoreboardV3 object for a specific date."""
    date_str = game_date.strftime("%Y-%m-%d")
    cache_key = f"raw_scoreboard_v3_{league_id}_{date_str}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached
    try:
        sb = with_retry(
            lambda: scoreboardv3.ScoreboardV3(
                game_date=date_str,
                league_id=league_id,
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            ),
        )
        ttl = CACHE_TTL["historical"] if historical else CACHE_TTL["scoreboard"]
        cache.set(cache_key, sb, ttl)
        return sb
    finally:
        _reset_nba_stats_http_session()


# Compact leaders list indices (from get_games_leaders_list: [name, pts, reb, ast, team_id])
_CL_PLAYER_NAME = 0
_CL_PTS = 1
_CL_REB = 2
_CL_AST = 3
_CL_TEAM_ID = 4


def find_category_leaders(
    items: list[dict], categories: list[tuple[str, str]]
) -> tuple[dict[str, int], dict[str, list[dict]]]:
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


def get_games_list(days_offset: int = 1, league_id: str = "00") -> list:
    """Get list of game IDs for a given date offset"""
    g_set = set()
    try:
        sb = get_cached_scoreboard_v3(days_offset, league_id=league_id)
        games = sb.game_header.get_dict()
        for g in games["data"]:
            if g[GH_GAME_STATUS] > STATUS_SCHEDULED:
                g_set.add(g[GH_GAME_ID])
    except Exception as ex:
        log_exceptions(ex)
    return list(g_set)


def get_games_leaders_list(days_offset: int = 1, league_id: str = "00") -> dict:
    """Get games with their leaders"""
    g_dict = {}
    try:
        sb = get_cached_scoreboard_v3(days_offset, league_id=league_id)
        games = sb.game_header.get_dict()
        leaders = sb.game_leaders.get_dict()

        # Get game IDs
        for g in games["data"]:
            if g[GH_GAME_STATUS] > STATUS_SCHEDULED:
                g_dict[g[GH_GAME_ID]] = []

        for ld in leaders["data"]:
            game_id = ld[GL_GAME_ID]
            if game_id in g_dict:
                g_dict[game_id].append(
                    [
                        fix_encoding(ld[GL_PLAYER_NAME]),
                        ld[GL_PTS],
                        ld[GL_REB],
                        ld[GL_AST],
                        ld[GL_TEAM_ID],
                    ]
                )
    except Exception as ex:
        log_exceptions(ex)
    return g_dict


def get_cached_boxscore_v3(game_id: str, historical: bool = True) -> Any:
    """Return a cached BoxScoreTraditionalV3 response for the given game_id."""
    cache_key = f"raw_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached
    try:
        bs_stats = with_retry(
            lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=game_id,
                proxy=STATS_PROXY,
                timeout=STATS_TIMEOUT,
            ),
        )
        ttl = CACHE_TTL["historical"] if historical else CACHE_TTL["boxscores"]
        cache.set(cache_key, bs_stats, ttl)
        return bs_stats
    finally:
        _reset_nba_stats_http_session()


def fetch_single_boxscore(
    game_id: str,
    leaders_data: list,
    league_id: str = "00",
) -> dict | None:
    """Fetch boxscore for a single game"""
    game_box = None
    try:
        data = get_cached_live_boxscore(game_id, league_id=league_id)
        game = data.get("game", {})
        game_box = {"gameId": game_id, "teams": []}
        leaders_by_team = {
            ld[_CL_TEAM_ID]: ld for ld in leaders_data if len(ld) > _CL_TEAM_ID
        }

        for team_key in ["homeTeam", "awayTeam"]:
            team = game[team_key]
            team_id = team["teamId"]
            s = team["statistics"]

            leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
            ld = leaders_by_team.get(team_id)
            if ld:
                leader = {
                    "name": ld[_CL_PLAYER_NAME],
                    "points": ld[_CL_PTS],
                    "rebounds": ld[_CL_REB],
                    "assists": ld[_CL_AST],
                }

            game_box["teams"].append(
                {
                    "name": f"{team['teamCity']} {team['teamName']}",
                    "score": team["score"],
                    "stats": {
                        "fg": f"{s['fieldGoalsMade']}/{s['fieldGoalsAttempted']}",
                        "fgPct": s["fieldGoalsPercentage"],
                        "threePt": f"{s['threePointersMade']}/{s['threePointersAttempted']}",
                        "threePtPct": s["threePointersPercentage"],
                        "ft": f"{s['freeThrowsMade']}/{s['freeThrowsAttempted']}",
                        "ftPct": s["freeThrowsPercentage"],
                        "rebounds": s["reboundsTotal"],
                        "offRebounds": s["reboundsOffensive"],
                        "assists": s["assists"],
                        "steals": s["steals"],
                        "blocks": s["blocks"],
                        "turnovers": s["turnovers"],
                        "fouls": s["foulsPersonal"],
                    },
                    "leader": leader,
                }
            )

        return game_box
    except Exception as ex:
        log_exceptions(ex)
        return game_box
