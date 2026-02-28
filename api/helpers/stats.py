import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from helpers.common import STATS_PROXY
from helpers.logger import log_exceptions
from nba_api.stats.endpoints import boxscoretraditionalv3, scoreboardv3

PLAYERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../static/players_with_teamid.json")

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
    except Exception as ex:
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

def load_players_file(): # pragma: no cover
    global _players_cache, _players_cache_mtime, _players_dict_cache
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


def load_players_dict(): # pragma: no cover
    """Return {player_id: player_row} dict for O(1) lookups."""
    load_players_file()
    return _players_dict_cache


def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_dict = []
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv3.ScoreboardV3(
            game_date=target_date.strftime("%Y-%m-%d"),
            proxy=STATS_PROXY,
        )
        games = sb.game_header.get_dict()
        for g in games["data"]:
            if g[2] > 1:
                g_dict.append(g[0])
    except Exception as ex:
        log_exceptions(ex)
        pass
    return list(set(g_dict))


def get_games_leaders_list(days_offset: int = 1):
    """Get games with their leaders"""
    g_dict = {}
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv3.ScoreboardV3(
            game_date=target_date.strftime("%Y-%m-%d"),
            proxy=STATS_PROXY,
        )
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
        pass
    return g_dict

def fetch_single_boxscore(game_id, leaders_data):
    """Fetch boxscore for a single game (for parallel execution)"""
    game_box = {}
    try:
        bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(
            game_id=game_id,
            proxy=STATS_PROXY,
        )

        team_stats = bs_stats.team_stats.get_dict()["data"]
        game_box = {"gameId": game_id, "teams": []}

        for i, team in enumerate(team_stats):
            leader = {"name": "", "points": 0, "rebounds": 0, "assists": 0}
            team_id = team[1]  # TEAM_ID from boxscore
            ld = next((leader for leader in leaders_data if len(leader) > 4 and leader[4] == team_id), None)
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
        # Ignore exception as the game hasn't started yet (No response from boxscore endpoint for provided gameId)
        return game_box