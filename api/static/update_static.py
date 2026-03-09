import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from helpers.common import STATS_PROXY, STATS_TIMEOUT
from helpers.logger import log_exceptions
from helpers.stats import get_games_list
from nba_api.stats.endpoints import boxscoretraditionalv3

PLAYERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "players_with_teamid.json"
)

# BoxScoreTraditionalV3 player_stats column indices
_TEAM_ID = 1
_PLAYER_ID = 6
_COMMENT = 12  # empty string means player actually played (not DNP)


def update_players():
    date_offset = 1

    with open(PLAYERS_FILE, "r") as file:
        players_with_teamid = json.load(file)

    players_dict = {p[0]: p for p in players_with_teamid}
    changed = False

    for game in get_games_list(date_offset):
        try:
            bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(
                game_id=game, proxy=STATS_PROXY, timeout=STATS_TIMEOUT
            )
        except Exception as ex:
            log_exceptions(ex)
            continue

        for player in bs_stats.player_stats.get_dict()["data"]:
            p = players_dict.get(player[_PLAYER_ID])
            if p is not None:
                if player[_COMMENT] == "":
                    if p[2] != player[_TEAM_ID]:
                        p[2] = player[_TEAM_ID]
                        changed = True

    if changed:
        dir_name = os.path.dirname(PLAYERS_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(players_with_teamid, f, indent=4)
            os.replace(tmp_path, PLAYERS_FILE)
        except BaseException:
            os.unlink(tmp_path)
            raise


if __name__ == "__main__":
    update_players()
