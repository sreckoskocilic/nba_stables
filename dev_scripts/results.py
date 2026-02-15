from nba_api.live.nba.endpoints import scoreboard
from tabulate2 import tabulate

from common.games import parse_scoreboard

tabulate.MIN_PADDING = 0
result = [["", "Score", "Status", "Lead Player", "PTS", "REB", "AST"]]

if __name__ == "__main__":
    # time.sleep(1)

    for scoreboard_game in scoreboard.ScoreBoard().games.data:
        result.append(parse_scoreboard(scoreboard_game))

    table = tabulate(
        result,
        tablefmt="fancy_grid",
        colalign=("left", "right", "left", "left", "right", "right", "right"),
    )
    print(table)
