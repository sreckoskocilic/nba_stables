import argparse
import json
import os

from isodate import parse_duration
from nba_api.live.nba.endpoints import boxscore, scoreboard
from tabulate2 import tabulate
from termcolor import colored

PLAYERS_FILE = f"{os.path.dirname(os.path.abspath(__file__))}/players_with_teamid.json"


def reformat_player_minutes(total_seconds: int) -> str:
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    return f"{minutes}:{seconds:02d}"


def parse_player_stats(player_dict, team_tricode):
    return [
        f"{player_dict["name"]} - {player_dict["personId"]}",
        team_tricode,
        reformat_player_minutes(int(parse_duration(player_dict["statistics"]["minutes"]).total_seconds())),
        (
            colored(player_dict["statistics"]["points"], "light_green")
            if player_dict["statistics"]["points"] > 0
            else player_dict["statistics"]["points"]
        ),
        f"{player_dict["statistics"]["threePointersMade"]}/{player_dict["statistics"]["threePointersAttempted"]}",
        (
            colored(player_dict["statistics"]["reboundsTotal"], "light_green")
            if player_dict["statistics"]["reboundsTotal"] > 0
            else player_dict["statistics"]["reboundsTotal"]
        ),
        (
            colored(player_dict["statistics"]["assists"], "light_green")
            if player_dict["statistics"]["assists"] > 0
            else player_dict["statistics"]["assists"]
        ),
        player["statistics"]["blocks"],
        player["statistics"]["steals"],
        player["statistics"]["turnovers"],
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--ids",
        default=None,
        help="Player ids",
    )
    args = parser.parse_args()
    player_ids = [int(item) for item in args.ids.split(",")]
    team_ids = []

    result = [["Player - ID", "TEAM", "TIME", "PT", "3P", "RB", "AS", "BL", "ST", "TO"]]  #

    with open(PLAYERS_FILE, "r") as ff:
        players_with_teamid = json.load(ff)

    for pl in player_ids:
        p = next(x for x in players_with_teamid if x[0] == pl)
        if p[2] not in team_ids:
            team_ids.append(p[2])

    for game in scoreboard.ScoreBoard().games.data:
        if game["homeTeam"]["teamId"] in team_ids or game["awayTeam"]["teamId"] in team_ids:
            try:
                bs = boxscore.BoxScore(game_id=game.get("gameId")).get_dict()
            except Exception:
                continue

            for player in bs["game"]["homeTeam"]["players"]:
                if player["personId"] in player_ids and player["status"] == "ACTIVE":
                    result.append(parse_player_stats(player, bs["game"]["homeTeam"]["teamTricode"]))
            for player in bs["game"]["awayTeam"]["players"]:
                if player["personId"] in player_ids and player["status"] == "ACTIVE":
                    result.append(parse_player_stats(player, bs["game"]["awayTeam"]["teamTricode"]))

    print(
        tabulate(
            result,
            tablefmt="fancy_grid",
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
                "right",
            ),
        )
    )
