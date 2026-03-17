import re
import threading
import time
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

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
from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
    commonallplayers,
    scoreboardv3,
)

_TZ_ET = ZoneInfo("US/Eastern")
_TZ_CET = ZoneInfo("Europe/Berlin")
_ET_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)", re.IGNORECASE)


# Helper functions
@lru_cache(maxsize=1)
def _today_et_cached(now: datetime) -> date:
    return now.astimezone(_TZ_ET).date()


def _today_et() -> date:
    """Return today's date in US/Eastern (NBA schedule timezone)."""
    return _today_et_cached(datetime.now(_TZ_ET))


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


@lru_cache(maxsize=1024)
def fix_encoding(s: str) -> str:
    """Fix nba_api mojibake: UTF-8 bytes decoded as Latin-1"""
    try:
        return s.encode("iso-8859-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _with_retry(fn, attempts: int = 3, delay: float = 0.2):
    """Run `fn` with exponential backoff retry."""
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as ex:  # pragma: no cover
            last_err = ex
            if i == attempts - 1:
                break
            time.sleep(delay * (2**i))
    if last_err:
        raise last_err


_players_cache = None
_players_dict_cache = None
_players_cache_expires = 0
_players_lock = threading.Lock()


def _fetch_players():
    """Fetch active players with their current team IDs from the NBA stats API."""
    cap = commonallplayers.CommonAllPlayers(
        is_only_current_season=1, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
    )
    data = cap.common_all_players.get_dict()
    players = []

    # Column indices within the `common_all_players` dataset
    _PERSON_ID = 0
    _DISPLAY_LAST_COMMA_FIRST = 1
    _TEAM_ID = 7

    for row in data.get("data", []):
        person_id = row[_PERSON_ID]
        name_raw = row[_DISPLAY_LAST_COMMA_FIRST]

        # Convert "Last, First" to "First Last" for friendlier search
        if "," in name_raw:
            last, first = [part.strip() for part in name_raw.split(",", 1)]
            name = f"{first} {last}"
        else:
            name = name_raw

        team_id = row[_TEAM_ID] if len(row) > _TEAM_ID else None
        players.append([person_id, fix_encoding(name), team_id])

    return players


def load_players_file():  # pragma: no cover
    """Return cached list of active players fetched from the NBA stats API."""
    global _players_cache, _players_dict_cache, _players_cache_expires
    with _players_lock:
        if _players_cache and time.time() < _players_cache_expires:
            return _players_cache

        try:
            _players_cache = _fetch_players()
            _players_dict_cache = {p[0]: p for p in _players_cache}
            _players_cache_expires = time.time() + CACHE_TTL["players"]
        except Exception as ex:
            log_exceptions(ex)
            # Keep serving the previous cache if available (stale-while-error).
            if _players_cache:
                _players_cache_expires = time.time() + 300  # short extension
                return _players_cache
            # Fallback to an empty cache if there is nothing to serve.
            _players_cache = []
            _players_dict_cache = {}
            _players_cache_expires = time.time() + 300

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
    data = _with_retry(
        lambda: (
            live_scoreboard.ScoreBoard(
                proxy=STATS_PROXY, timeout=STATS_TIMEOUT
            ).games.data
        ),
    )
    cache.set("raw_scoreboard", data, CACHE_TTL["scoreboard"])
    return data


def get_cached_live_boxscore(game_id):  # pragma: no cover
    """Return a cached live BoxScore response dict for the given game_id."""
    cache_key = f"raw_live_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = _with_retry(
        lambda: live_boxscore.BoxScore(
            game_id=game_id, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
        ).get_dict(),
    )
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
    sb = _with_retry(
        lambda: scoreboardv3.ScoreboardV3(
            game_date=date_str,
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
        ),
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


def get_cached_boxscore_v3(game_id, historical=True):
    """Return a cached BoxScoreTraditionalV3 response for the given game_id."""
    cache_key = f"raw_boxscore_{game_id}"
    cached = cache.get(cache_key)
    if cached is not None:  # pragma: no cover
        return cached
    bs_stats = _with_retry(
        lambda: boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id,
            proxy=STATS_PROXY,
            timeout=STATS_TIMEOUT,
        ),
    )
    ttl = CACHE_TTL["historical"] if historical else CACHE_TTL["boxscores"]
    cache.set(cache_key, bs_stats, ttl)
    return bs_stats


def fetch_single_boxscore(game_id, leaders_data):
    """Fetch boxscore for a single game (for parallel execution)"""
    game_box = {}
    try:
        data = get_cached_live_boxscore(game_id)
        game = data.get("game", {})
        game_box = {"gameId": game_id, "teams": []}
        leaders_by_team = {ld[4]: ld for ld in leaders_data if len(ld) > 4}

        for team_key in ["homeTeam", "awayTeam"]:
            team = game[team_key]
            team_id = team["teamId"]
            s = team["statistics"]

            leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
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
        # Ignore exception as the game hasn't started yet (No response from boxscore endpoint for provided gameId)
        log_exceptions(ex)
        return game_box
