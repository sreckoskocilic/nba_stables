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


# WNBA standings use different column indices (_WS_* in scores.py)
def make_wnba_standings_row(rank, city, name, conf, wins, losses, team_id=1611661313):
    row = [None] * 40
    row[2] = team_id  # _WS_TEAM_ID
    row[3] = city  # _WS_CITY
    row[4] = name  # _WS_NAME
    row[6] = conf  # _WS_CONF
    row[8] = rank  # _WS_RANK
    row[13] = wins  # _WS_WINS
    row[14] = losses  # _WS_LOSSES
    row[15] = wins / (wins + losses) if (wins + losses) else 0.0  # _WS_WIN_PCT
    row[18] = f"{wins // 2}-{losses // 2}"  # _WS_HOME
    row[19] = f"{wins // 2}-{losses // 2}"  # _WS_AWAY
    row[20] = "8-2"  # _WS_L10
    row[37] = "W3"  # _WS_STREAK
    row[38] = 2.5  # _WS_GAMES_BACK
    return row


WNBA_GAME_ID = "1022600001"
WNBA_TEAM_ID_NYL = 1611661313
WNBA_TEAM_ID_LVA = 1611661319


def _make_v3_player_stats(**kw):
    stats = {
        "minutes": "28:00",
        "fieldGoalsMade": 11,
        "fieldGoalsAttempted": 20,
        "threePointersMade": 2,
        "threePointersAttempted": 5,
        "freeThrowsMade": 4,
        "freeThrowsAttempted": 4,
        "reboundsOffensive": 1,
        "reboundsDefensive": 7,
        "reboundsTotal": 8,
        "assists": 6,
        "steals": 1,
        "blocks": 0,
        "turnovers": 2,
        "foulsPersonal": 2,
        "points": 28,
    }
    stats.update(kw)
    return stats


def make_v3_boxscore(game_id=WNBA_GAME_ID):
    m = MagicMock()
    m.get_dict.return_value = {
        "boxScoreTraditional": {
            "gameId": game_id,
            "homeTeam": {
                "teamId": WNBA_TEAM_ID_NYL,
                "teamCity": "New York",
                "teamName": "Liberty",
                "teamTricode": "NYL",
                "statistics": {
                    "points": 85,
                    "fieldGoalsMade": 30,
                    "fieldGoalsAttempted": 65,
                    "threePointersMade": 8,
                    "threePointersAttempted": 20,
                    "freeThrowsMade": 17,
                    "freeThrowsAttempted": 20,
                    "reboundsTotal": 35,
                    "reboundsOffensive": 8,
                    "assists": 20,
                    "steals": 7,
                    "blocks": 4,
                    "turnovers": 12,
                    "foulsPersonal": 18,
                    "freeThrowsPercentage": 0.85,
                    "fieldGoalsPercentage": 0.462,
                    "threePointersPercentage": 0.4,
                },
                "players": [
                    {
                        "personId": 100001,
                        "name": None,
                        "firstName": "Sabrina",
                        "familyName": "Ionescu",
                        "status": "ACTIVE",
                        "statistics": _make_v3_player_stats(points=25, assists=8),
                    },
                ],
            },
            "awayTeam": {
                "teamId": WNBA_TEAM_ID_LVA,
                "teamCity": "Las Vegas",
                "teamName": "Aces",
                "teamTricode": "LVA",
                "statistics": {
                    "points": 80,
                    "fieldGoalsMade": 28,
                    "fieldGoalsAttempted": 62,
                    "threePointersMade": 6,
                    "threePointersAttempted": 18,
                    "freeThrowsMade": 18,
                    "freeThrowsAttempted": 22,
                    "reboundsTotal": 32,
                    "reboundsOffensive": 6,
                    "assists": 18,
                    "steals": 5,
                    "blocks": 3,
                    "turnovers": 14,
                    "foulsPersonal": 20,
                    "freeThrowsPercentage": 0.818,
                    "fieldGoalsPercentage": 0.452,
                    "threePointersPercentage": 0.333,
                },
                "players": [
                    {
                        "personId": 100002,
                        "name": None,
                        "firstName": "A'ja",
                        "familyName": "Wilson",
                        "status": "ACTIVE",
                        "statistics": _make_v3_player_stats(
                            points=30,
                            reboundsTotal=12,
                            reboundsOffensive=3,
                            reboundsDefensive=9,
                            assists=3,
                        ),
                    },
                ],
            },
        }
    }
    return m


def make_wnba_live_boxscore(game_id=WNBA_GAME_ID, status="Final"):
    return {
        "game": {
            "gameStatusText": status,
            "homeTeam": {
                "teamCity": "New York",
                "teamName": "Liberty",
                "teamTricode": "NYL",
                "teamId": WNBA_TEAM_ID_NYL,
                "score": 85,
                "statistics": {
                    "fieldGoalsMade": 30,
                    "fieldGoalsAttempted": 65,
                    "fieldGoalsPercentage": 0.462,
                    "threePointersMade": 8,
                    "threePointersAttempted": 20,
                    "threePointersPercentage": 0.4,
                    "freeThrowsMade": 17,
                    "freeThrowsAttempted": 20,
                    "freeThrowsPercentage": 0.85,
                    "reboundsTotal": 35,
                    "reboundsOffensive": 8,
                    "assists": 20,
                    "steals": 7,
                    "blocks": 4,
                    "turnovers": 12,
                    "foulsPersonal": 18,
                },
                "players": [
                    {
                        "personId": 100001,
                        "name": "Sabrina Ionescu",
                        "status": "ACTIVE",
                        "statistics": make_live_player_stats(
                            points=25,
                            assists=8,
                        ),
                    },
                ],
            },
            "awayTeam": {
                "teamCity": "Las Vegas",
                "teamName": "Aces",
                "teamTricode": "LVA",
                "teamId": WNBA_TEAM_ID_LVA,
                "score": 80,
                "statistics": {
                    "fieldGoalsMade": 28,
                    "fieldGoalsAttempted": 62,
                    "fieldGoalsPercentage": 0.452,
                    "threePointersMade": 6,
                    "threePointersAttempted": 18,
                    "threePointersPercentage": 0.333,
                    "freeThrowsMade": 18,
                    "freeThrowsAttempted": 22,
                    "freeThrowsPercentage": 0.818,
                    "reboundsTotal": 32,
                    "reboundsOffensive": 6,
                    "assists": 18,
                    "steals": 5,
                    "blocks": 3,
                    "turnovers": 14,
                    "foulsPersonal": 20,
                },
                "players": [
                    {
                        "personId": 100002,
                        "name": "A'ja Wilson",
                        "status": "ACTIVE",
                        "statistics": make_live_player_stats(
                            points=30,
                            reboundsTotal=12,
                            reboundsOffensive=3,
                            reboundsDefensive=9,
                            assists=3,
                        ),
                    },
                ],
            },
        }
    }
