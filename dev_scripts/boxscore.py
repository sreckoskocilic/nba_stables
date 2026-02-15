from nba_api.stats.endpoints import boxscoretraditionalv3
from tabulate2 import tabulate

from common.games import get_games_leaders_list, parse_boxscore_stats


def get_boxscore():
    g_list = get_games_leaders_list()

    for game_id, leaders in g_list.items():
        result = [
            [
                "",
                "Score",
                "FG",
                "FG %",
                "3P",
                "3P %",
                "FT",
                "FT %",
                "RB",
                "ORB",
                "AST",
                "ST",
                "BL",
                "TO",
                "PF",
                "Lead Player",
                "PT",
                "RB",
                "AS",
            ]
        ]
        try:
            bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        except:
            continue
        if bs_stats is None:
            continue
        result += parse_boxscore_stats(bs_stats.team_stats.get_dict()["data"], leaders)
        print(tabulate(result, tablefmt="fancy_grid", preserve_whitespace=True))
        print()


def get_boxscores_list():
    bscores = ""
    g_list = get_games_leaders_list()

    for game_id, leaders in g_list.items():
        result = [
            [
                "",
                "Score",
                "FG",
                "FG %",
                "3PT",
                "3PT %",
                "FT",
                "FT %",
                "REB",
                "OREB",
                "AST",
                "STE",
                "BLK",
                "TO",
                "PF",
                "Lead Player",
                "PTS",
                "REB",
                "AST",
            ]
        ]
        try:
            bs_stats = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        except:
            continue
        if bs_stats is None:
            continue
        result += parse_boxscore_stats(bs_stats.team_stats.get_dict()["data"], leaders)
        bscores += tabulate(result, tablefmt="fancy_grid", preserve_whitespace=False) + "\n\n"
    return bscores


if __name__ == "__main__":
    get_boxscore()
