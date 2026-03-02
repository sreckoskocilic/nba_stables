import json
import os
from datetime import date, timedelta

from nba_api.stats.endpoints import boxscoretraditionalv3, scoreboardv3

PLAYERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "players_with_teamid.json"
)

def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_set = set()
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv3.ScoreboardV3(game_date=target_date.strftime("%Y-%m-%d"))
        games = sb.game_header.get_dict()
        for g in games["data"]:
            g_set.add(g[0])
    except Exception:
        pass
    return list(g_set)


def update_players():
    date_offset = 1

    with open(PLAYERS_FILE, "r") as file:
        players_with_teamid = json.load(file)

    players_dict = {p[0]: p for p in players_with_teamid}

    for game in get_games_list(date_offset):
        try:
            bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game)
        except Exception:
            continue

        for player in bs_stats.player_stats.get_dict()["data"]:
            p = players_dict.get(player[6])
            if p is not None:
                if player[12] == "":
                    if p[2] != player[1]:
                        p[2] = player[1]
    with open(PLAYERS_FILE, "w") as ffile:
        json.dump(players_with_teamid, ffile, indent=4)


if __name__ == "__main__":
    update_players()
