import json
import os
import sys
from datetime import date, datetime, timedelta

from nba_api.stats.endpoints import boxscoretraditionalv3, scoreboardv3

PLAYERS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "players_with_teamid.json"
)

TRADES_LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "trades.log"
)

def get_games_list(days_offset: int = 1):
    """Get list of game IDs for a given date offset"""
    g_dict = []
    target_date = date.today() - timedelta(days=days_offset)
    try:
        sb = scoreboardv3.ScoreboardV3(game_date=target_date.strftime("%Y-%m-%d"))
        games = sb.game_header.get_dict()
        for g in games["data"]:
            g_dict.append(g[0])
    except Exception:
        pass
    return list(set(g_dict))


def update_players():
    date_offset = 1
    now = datetime.now()

    log_file = open(TRADES_LOG_FILE, "w")
    sys.stdout = log_file

    with open(PLAYERS_FILE, "r") as file:
        players_with_teamid = json.load(file)

    changes = 0
    changed_players = []
    off_date = (now + timedelta(days=-date_offset)).strftime("%d-%m-%Y")
    for game in get_games_list(date_offset):
        try:
            bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game)
        except Exception:
            continue

        for player in bs_stats.player_stats.get_dict()["data"]:
            p = next((x for x in players_with_teamid if x[0] == player[6]), None)
            if p is not None:
                if player[12] == "":
                    if p[2] != player[1]:
                        p[2] = player[1]
                        changes += 1
                        changed_players.append(player)
    with open(PLAYERS_FILE, "w") as ffile:
        json.dump(players_with_teamid, ffile, indent=4)

    if changes > 0:
        print(f"Date: {off_date} Changes: {changes}")
        for player in changed_players:
            print(player)
    else:
        print(f"Date: {off_date}")

    log_file.close()


if __name__ == "__main__":
    update_players()
