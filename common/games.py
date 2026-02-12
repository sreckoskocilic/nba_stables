from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

from nba_api.stats.endpoints import scoreboardv3


def get_games_list(days_offset=1):
    g_dict = []
    yesterday = date.today() - timedelta(days=days_offset)
    games_list = scoreboardv3.ScoreboardV3(game_date=yesterday.strftime("%Y-%m-%d")).game_leaders.get_dict()
    for g in games_list["data"]:
        g_dict.append(g[0])
    return list(set(g_dict))


def get_games_leaders_list(days_offset=1):
    g_dict = {}
    yesterday = date.today() - timedelta(days=days_offset)
    games_list = scoreboardv3.ScoreboardV3(game_date=yesterday.strftime("%Y-%m-%d")).game_leaders.get_dict()

    for g in games_list["data"]:
        g_dict.setdefault(g[0], [])
        g_dict[g[0]].append(
            [
                g[4],
                g[9],
                g[10],
                g[11],
            ]
        )
    return g_dict


def parse_scoreboard(game):
    parsed = []
    home_team = f"{game['homeTeam']['teamCity']} {game['homeTeam']['teamName']}"
    away_team = f"{game["awayTeam"]["teamCity"]} {game["awayTeam"]["teamName"]}"
    score = f"{game["homeTeam"]['score']}\n{game['awayTeam']['score']}"
    if game["gameStatus"] != 1:
        game_status = game["gameStatusText"]
    else:
        game_status = convert_time_to_cet(game["gameStatusText"])
    home_leaders = game["gameLeaders"]["homeLeaders"]
    away_leaders = game["gameLeaders"]["awayLeaders"]
    home_leader_player = bytes(home_leaders["name"], "iso-8859-1").decode("utf-8")
    away_leader_player = bytes(away_leaders["name"], "iso-8859-1").decode("utf-8")

    parsed.append(f"{home_team}\n{away_team}")
    parsed.append(score)
    parsed.append(game_status)
    parsed.append(f"{home_leader_player}\n{away_leader_player}")
    parsed.append(f"{home_leaders["points"]}\n{away_leaders["points"]}")
    parsed.append(f"{home_leaders["rebounds"]}\n{away_leaders["rebounds"]}")
    parsed.append(f"{home_leaders["assists"]}\n{away_leaders["assists"]}")
    return parsed

def convert_time_to_cet(time: str) -> str:
    source_tz = ZoneInfo("US/Eastern")
    cet_tz = ZoneInfo("CET")

    now = datetime.now()
    naive_dt = datetime.strptime(f"{now.year}-{now.month}-{now.day} {time[:-3]}", "%Y-%m-%d %H:%M %p")

    aware_et_dt = naive_dt.replace(tzinfo=source_tz) - timedelta(hours=12)
    aware_cet_dt = aware_et_dt.astimezone(cet_tz)

    output_time_str = aware_cet_dt.strftime("%H:%M")

    return output_time_str

def parse_boxscore_stats(bscore_stats, leader):
    stats = []
    for i, d in enumerate(bscore_stats):
        stats.append(
            [
                f"{d[2]} {d[3]}".ljust(25),
                d[-2],
                f"{d[7]}/{d[8]}",
                d[9],
                f"{d[10]}/{d[11]}",
                d[12],
                f"{d[13]}/{d[14]}",
                d[15],
                d[18],
                d[16],
                d[19],
                d[20],
                d[21],
                d[22],
                d[23],
                leader[i][0],
                leader[i][1],
                leader[i][2],
                leader[i][3],
            ]
        )
    return stats


def get_date(days_offset=1) -> str:
    yesterday = date.today() - timedelta(days=days_offset)
    return yesterday.strftime("%d-%m-%Y")
