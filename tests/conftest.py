import os
import sys

# Make `api/` importable from anywhere pytest is run
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

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
            "homeTeam": {
                "teamCity": "Los Angeles",
                "teamName": "Lakers",
                "teamTricode": "LAL",
                "teamId": TEAM_ID_LAL,
                "score": 110,
                "players": [make_live_player()],
            },
            "awayTeam": {
                "teamCity": "Boston",
                "teamName": "Celtics",
                "teamTricode": "BOS",
                "teamId": TEAM_ID_BOS,
                "score": 105,
                "players": [make_live_player(person_id=1629029, name="Jayson Tatum")],
            },
        }
    }


def make_standings_row(rank, city, name, conf, wins, losses):
    row = [None] * 40
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
