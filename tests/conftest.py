import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Make `api/` importable from anywhere pytest is run
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

# Suppress noisy error logs from intentional exception tests
logging.getLogger("helpers.logger").setLevel(logging.CRITICAL)


@pytest.fixture(autouse=True)
def _patch_lgf_playoffs():
    """Block real LeagueGameFinder calls in every test.

    `_fetch_playoff_series_data` is invoked indirectly from /api/scoreboard and
    /api/playoffs via the cached series helper; without this patch each affected
    test would hit the live NBA API. Tests that need specific behaviour override
    this with their own patch.
    """
    m = MagicMock()
    m.return_value.get_dict.return_value = {
        "resultSets": [{"headers": ["GAME_ID", "TEAM_ID", "WL", "PTS"], "rowSet": []}]
    }
    with patch("routes.scores.LeagueGameFinder", m):
        yield


# ─────────────────────────────────────────────────────────────────────────────
# Shared test constants
# ─────────────────────────────────────────────────────────────────────────────

GAME_ID = "0022301234"
PLAYER_ID = 2544  # LeBron James
TEAM_ID_LAL = 1610612747
TEAM_ID_BOS = 1610612738

FAKE_PLAYERS = [
    [PLAYER_ID, "LeBron James", TEAM_ID_LAL],
    [1629029, "Jayson Tatum", TEAM_ID_BOS],
]

CAREER_HEADERS = [
    "PLAYER_ID",
    "SEASON_ID",
    "LEAGUE_ID",
    "TEAM_ID",
    "TEAM_ABBREVIATION",
    "PLAYER_AGE",
    "GP",
    "GS",
    "MIN",
    "FGM",
    "FGA",
    "FG_PCT",
    "FG3M",
    "FG3A",
    "FG3_PCT",
    "FTM",
    "FTA",
    "FT_PCT",
    "OREB",
    "DREB",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
    "PTS",
]


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock data builders
# ─────────────────────────────────────────────────────────────────────────────


def make_live_player_stats(**kw):
    stats = {
        "points": 28,
        "reboundsTotal": 8,
        "assists": 6,
        "steals": 1,
        "blocks": 0,
        "turnovers": 2,
        "fieldGoalsMade": 11,
        "fieldGoalsAttempted": 20,
        "threePointersMade": 2,
        "threePointersAttempted": 5,
        "freeThrowsMade": 4,
        "freeThrowsAttempted": 4,
        "reboundsOffensive": 1,
        "reboundsDefensive": 7,
        "foulsPersonal": 2,
        "minutes": "PT28M00.00S",
        "plusMinusPoints": 8,
    }
    stats.update(kw)
    return stats


def make_live_player(person_id=PLAYER_ID, name="LeBron James", **stats_kw):
    return {
        "personId": person_id,
        "name": name,
        "status": "ACTIVE",
        "statistics": make_live_player_stats(**stats_kw),
    }


def make_live_game(**kw):
    game = {
        "gameId": GAME_ID,
        "gameStatus": 3,
        "gameStatusText": "Final",
        "homeTeam": {
            "teamCity": "Los Angeles",
            "teamName": "Lakers",
            "teamTricode": "LAL",
            "teamId": TEAM_ID_LAL,
            "score": 110,
        },
        "awayTeam": {
            "teamCity": "Boston",
            "teamName": "Celtics",
            "teamTricode": "BOS",
            "teamId": TEAM_ID_BOS,
            "score": 105,
        },
        "gameLeaders": {
            "homeLeaders": {
                "name": "LeBron James",
                "points": 28,
                "rebounds": 8,
                "assists": 6,
            },
            "awayLeaders": {
                "name": "Jayson Tatum",
                "points": 32,
                "rebounds": 9,
                "assists": 4,
            },
        },
    }
    game.update(kw)
    return game


def make_live_boxscore(game_id=GAME_ID, status="Final"):
    return {
        "game": {
            "gameStatusText": status,
            "arena": {"arenaName": "Crypto.com Arena", "arenaCity": "Los Angeles"},
            "attendance": 18997,
            "officials": [
                {"name": "Tony Brothers"},
                {"firstName": "Scott", "familyName": "Foster"},
            ],
            "homeTeam": {
                "teamCity": "Los Angeles",
                "teamName": "Lakers",
                "teamTricode": "LAL",
                "teamId": TEAM_ID_LAL,
                "score": 110,
                "periods": [
                    {"period": 1, "score": 28},
                    {"period": 2, "score": 25},
                    {"period": 3, "score": 30},
                    {"period": 4, "score": 27},
                ],
                "players": [make_live_player()],
            },
            "awayTeam": {
                "teamCity": "Boston",
                "teamName": "Celtics",
                "teamTricode": "BOS",
                "teamId": TEAM_ID_BOS,
                "score": 105,
                "periods": [
                    {"period": 1, "score": 22},
                    {"period": 2, "score": 30},
                    {"period": 3, "score": 28},
                    {"period": 4, "score": 25},
                ],
                "players": [
                    make_live_player(
                        person_id=1629029,
                        name="Jayson Tatum",
                        points=32,
                        reboundsTotal=9,
                    )
                ],
            },
        }
    }


def make_scoreboard_v3(games=None):
    """Build a mock ScoreboardV3 object from a list of live game dicts.

    Translates make_live_game()-style dicts into the V3 data format
    so tests can mock get_scoreboard_v3_by_date with familiar data.
    """
    from unittest.mock import MagicMock

    if games is None:
        games = []

    header_data = []
    line_score_data = []
    leaders_data = []

    for g in games:
        gid = g["gameId"]
        home = g["homeTeam"]
        away = g["awayTeam"]
        status_text = g.get("gameStatusText", "Final")
        game_status = 3 if "Final" in status_text else (2 if "Q" in status_text else 1)
        game_code = f"20260307/{away['teamTricode']}{home['teamTricode']}"  # date portion is arbitrary; only tricodes are parsed
        game_et = g.get("gameEt", "2026-03-07T19:00:00Z")

        header_data.append(
            [
                gid,
                game_code,
                game_status,
                status_text,
                0,
                "",
                "2026-03-08T00:00:00Z",
                game_et,
                4,
                "",
                "",
                "",
                "",
                False,
                "",
                "",
                "",
                False,
            ]
        )

        line_score_data.append(
            [
                gid,
                home["teamId"],
                home["teamCity"],
                home["teamName"],
                home["teamTricode"],
                home["teamName"].lower(),
                0,
                0,
                home.get("score", 0),
                0,
                None,
                0,
            ]
        )
        line_score_data.append(
            [
                gid,
                away["teamId"],
                away["teamCity"],
                away["teamName"],
                away["teamTricode"],
                away["teamName"].lower(),
                0,
                0,
                away.get("score", 0),
                0,
                None,
                0,
            ]
        )

        for team_key in ("homeLeaders", "awayLeaders"):
            leader = g["gameLeaders"][team_key]
            tid = home["teamId"] if team_key == "homeLeaders" else away["teamId"]
            leaders_data.append(
                [
                    gid,
                    tid,
                    0,
                    0,
                    leader.get("name", ""),
                    0,
                    0,
                    0,
                    0,
                    leader.get("points", 0),
                    leader.get("rebounds", 0),
                    leader.get("assists", 0),
                ]
            )

    sb = MagicMock()
    sb.game_header.get_dict.return_value = {"data": header_data}
    sb.line_score.get_dict.return_value = {"data": line_score_data}
    sb.game_leaders.get_dict.return_value = {"data": leaders_data}
    return sb


_V3_PLAYER_HEADERS = (
    "gameId",
    "teamId",
    "teamCity",
    "teamName",
    "teamTricode",
    "teamSlug",
    "personId",
    "firstName",
    "familyName",
    "nameI",
    "playerSlug",
    "position",
    "comment",
    "jerseyNum",
    "minutes",
    "fieldGoalsMade",
    "fieldGoalsAttempted",
    "fieldGoalsPercentage",
    "threePointersMade",
    "threePointersAttempted",
    "threePointersPercentage",
    "freeThrowsMade",
    "freeThrowsAttempted",
    "freeThrowsPercentage",
    "reboundsOffensive",
    "reboundsDefensive",
    "reboundsTotal",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "foulsPersonal",
    "points",
    "plusMinusPoints",
)


def make_v3_boxscore_for_leaders(players):
    """Build a mock BoxScoreTraditionalV3 with player_stats for leaders tests.

    Each player dict: firstName, familyName, teamTricode, minutes,
    points, reboundsTotal, assists, blocks, steals, threePointersMade.
    """
    rows = []
    for p in players:
        rows.append(
            [
                GAME_ID,
                0,
                "",
                "",
                p.get("teamTricode", ""),
                "",
                0,
                p.get("firstName", ""),
                p.get("familyName", ""),
                "",
                "",
                "",
                "",
                "",
                p.get("minutes", "30:00"),
                0,
                0,
                0.0,
                p.get("threePointersMade", 0),
                0,
                0.0,
                0,
                0,
                0.0,
                0,
                0,
                p.get("reboundsTotal", 0),
                p.get("assists", 0),
                p.get("steals", 0),
                p.get("blocks", 0),
                0,
                0,
                p.get("points", 0),
                0.0,
            ]
        )
    mock = MagicMock()
    mock.player_stats.get_dict.return_value = {
        "headers": _V3_PLAYER_HEADERS,
        "data": rows,
    }
    return mock


_V3_TEAM_HEADERS = (
    "gameId",
    "teamId",
    "teamCity",
    "teamName",
    "teamTricode",
    "teamSlug",
    "minutes",
    "fieldGoalsMade",
    "fieldGoalsAttempted",
    "fieldGoalsPercentage",
    "threePointersMade",
    "threePointersAttempted",
    "threePointersPercentage",
    "freeThrowsMade",
    "freeThrowsAttempted",
    "freeThrowsPercentage",
    "reboundsOffensive",
    "reboundsDefensive",
    "reboundsTotal",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "foulsPersonal",
    "points",
    "plusMinusPoints",
)


def make_v3_game_boxscore():
    """Build a mock BoxScoreTraditionalV3 matching make_live_boxscore() data."""
    lal_player = make_live_player_stats()
    tat_stats = make_live_player_stats(points=32, reboundsTotal=9)

    player_rows = [
        [
            GAME_ID,
            TEAM_ID_LAL,
            "Los Angeles",
            "Lakers",
            "LAL",
            "lakers",
            PLAYER_ID,
            "LeBron",
            "James",
            "L. James",
            "lebron-james",
            "F",
            "",
            "",
            "28:00",
            lal_player["fieldGoalsMade"],
            lal_player["fieldGoalsAttempted"],
            round(lal_player["fieldGoalsMade"] / lal_player["fieldGoalsAttempted"], 3),
            lal_player["threePointersMade"],
            lal_player["threePointersAttempted"],
            0.4,
            lal_player["freeThrowsMade"],
            lal_player["freeThrowsAttempted"],
            1.0,
            lal_player["reboundsOffensive"],
            lal_player["reboundsDefensive"],
            lal_player["reboundsTotal"],
            lal_player["assists"],
            lal_player["steals"],
            lal_player["blocks"],
            lal_player["turnovers"],
            lal_player["foulsPersonal"],
            lal_player["points"],
            lal_player["plusMinusPoints"],
        ],
        [
            GAME_ID,
            TEAM_ID_BOS,
            "Boston",
            "Celtics",
            "BOS",
            "celtics",
            1629029,
            "Jayson",
            "Tatum",
            "J. Tatum",
            "jayson-tatum",
            "F",
            "",
            "",
            "28:00",
            tat_stats["fieldGoalsMade"],
            tat_stats["fieldGoalsAttempted"],
            round(tat_stats["fieldGoalsMade"] / tat_stats["fieldGoalsAttempted"], 3),
            tat_stats["threePointersMade"],
            tat_stats["threePointersAttempted"],
            0.4,
            tat_stats["freeThrowsMade"],
            tat_stats["freeThrowsAttempted"],
            1.0,
            tat_stats["reboundsOffensive"],
            tat_stats["reboundsDefensive"],
            tat_stats["reboundsTotal"],
            tat_stats["assists"],
            tat_stats["steals"],
            tat_stats["blocks"],
            tat_stats["turnovers"],
            tat_stats["foulsPersonal"],
            tat_stats["points"],
            tat_stats["plusMinusPoints"],
        ],
    ]

    team_rows = [
        [
            GAME_ID,
            TEAM_ID_LAL,
            "Los Angeles",
            "Lakers",
            "LAL",
            "lakers",
            "240:00",
            11,
            20,
            0.55,
            2,
            5,
            0.4,
            4,
            4,
            1.0,
            1,
            7,
            8,
            6,
            1,
            0,
            2,
            2,
            110,
            5.0,
        ],
        [
            GAME_ID,
            TEAM_ID_BOS,
            "Boston",
            "Celtics",
            "BOS",
            "celtics",
            "240:00",
            11,
            20,
            0.55,
            2,
            5,
            0.4,
            4,
            4,
            1.0,
            1,
            8,
            9,
            6,
            1,
            0,
            2,
            2,
            105,
            -5.0,
        ],
    ]

    mock = MagicMock()
    mock.player_stats.get_dict.return_value = {
        "headers": _V3_PLAYER_HEADERS,
        "data": player_rows,
    }
    mock.team_stats.get_dict.return_value = {
        "headers": _V3_TEAM_HEADERS,
        "data": team_rows,
    }
    return mock


def make_standings_row(rank, city, name, conf, wins, losses, team_id=1610612738):
    row = [None] * 40
    row[2] = team_id
    row[3] = city
    row[4] = name
    row[5] = conf
    row[7] = rank
    row[12] = wins
    row[13] = losses
    row[14] = wins / (wins + losses) if (wins + losses) else 0.0
    row[17] = f"{wins // 2}-{losses // 2}"
    row[18] = f"{wins // 2}-{losses // 2}"
    row[19] = "8-2"
    row[36] = "W3"
    row[37] = 2.5
    return row
