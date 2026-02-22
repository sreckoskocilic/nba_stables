from operator import itemgetter

from nba_api.live.nba.endpoints import boxscore
from tabulate2 import tabulate

from common.games import get_games_list

tabulate.MIN_PADDING = 0
stats_categories = [
    (1, "POINTS"),
    (2, "REBOUNDS"),
    (3, "ASSISTS"),
    (4, "BLOCKS"),
    (5, "STEALS"),
    (6, "3 POINTERS"),
]
g_list = get_games_list()


def get_top_performers():
    pls = []
    table = []

    for gid in g_list:
        try:
            bs = boxscore.BoxScore(game_id=gid).get_dict()
        except Exception:
            continue
        home_name = bs["game"]["homeTeam"]["teamTricode"]
        away_name = bs["game"]["awayTeam"]["teamTricode"]
        for player in bs["game"]["homeTeam"]["players"]:
            if player["status"] == "ACTIVE":
                pls.append(
                    [
                        f"{player['name']}  ({home_name})",
                        player["statistics"]["points"],
                        player["statistics"]["reboundsTotal"],
                        player["statistics"]["assists"],
                        player["statistics"]["blocks"],
                        player["statistics"]["steals"],
                        player["statistics"]["threePointersMade"],
                    ]
                )

        for player in bs["game"]["awayTeam"]["players"]:
            if player["status"] == "ACTIVE":
                pls.append(
                    [
                        f"{player['name']}  ({away_name})",
                        player["statistics"]["points"],
                        player["statistics"]["reboundsTotal"],
                        player["statistics"]["assists"],
                        player["statistics"]["blocks"],
                        player["statistics"]["steals"],
                        player["statistics"]["threePointersMade"],
                    ]
                )

    for cp in stats_categories:
        max_value = max(pls, key=itemgetter(cp[0]))[cp[0]]
        # key_player = sorted(pls, key=itemgetter(cp[0]), reverse=True)[:1][0]
        key_players = [row for row in pls if row[cp[0]] == max_value]
        for key_player in key_players:
            table.append(
                [
                    key_player[0],
                    cp[1],
                    key_player[cp[0]],
                ]
            )

    return tabulate(
        table,
        tablefmt="fancy_grid",
    )


if __name__ == "__main__":
    print(get_top_performers())
