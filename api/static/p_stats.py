import json
import os
import sys
import time

from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
    cumestatsteamgames,
)
from tabulate2 import tabulate
from termcolor import colored


def rgc(statval: list) -> list:
    return [colored(item, "light_green") for item in statval]


def bgc(statval: list) -> list:
    return [colored(item, "light_blue") for item in statval]


pid = sys.argv[1]
PLAYERS_FILE = f"{os.path.dirname(os.path.abspath(__file__))}/players_new.json"

with open(PLAYERS_FILE, "r") as ff:
    players_with_teamid = json.load(ff)
p = next(x for x in players_with_teamid if x[0] == int(pid))
pl_name = p[1]

game_ids = []
cc = cumestatsteamgames.CumeStatsTeamGames(team_id=p[2])
for game in cc.cume_stats_team_games.get_dict()["data"][:5]:
    game_ids.append(game)


stats = []

for gg in game_ids:
    time.sleep(0.2)
    csp = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=gg[1])
    ss = next(
        (x for x in csp.player_stats.get_dict()["data"] if x[6] == int(pid)), None
    )

    if ss is not None:
        stats.append(
            [gg[0]]
            + rgc(
                [
                    ss[14],
                    ss[32],
                    f"{ss[18]}/{ss[19]}",
                    ss[26],
                    ss[27],
                    ss[28],
                    ss[29],
                    ss[31],
                ]
            )
        )
    else:
        stats.append(bgc([gg[0], "DNP"]))


print("\n" + pl_name)
print(
    tabulate(
        stats,
        tablefmt="fancy_grid",
        headers=["MATCHUP", "TIME", "PTS", "3P", "REB", "AST", "BLK", "STL", "PF"],
        colalign=(
            "left",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
            "right",
        ),
    )
)
