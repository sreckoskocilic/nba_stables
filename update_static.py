import json
import sys
import time
from datetime import timedelta, datetime

from nba_api.stats.endpoints import boxscoretraditionalv3
from nba_api.stats.library.data import players

from common.games import get_games_list


def update_players():
    date_offset = 1
    now = datetime.now()

    log_file = open("trades.log", "w")
    sys.stdout = log_file

    with open("players_with_teamid.json", "r") as file:
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
    with open("players_with_teamid.json", "w") as ffile:
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
