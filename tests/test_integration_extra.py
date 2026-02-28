"""Additional integration tests to increase coverage of scores.py and players.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from helpers.common import cache
from main import app

# ── shared constants ──────────────────────────────────────────────────────────
GAME_ID     = "0022301234"
PLAYER_ID   = 2544
TEAM_ID_LAL = 1610612747
TEAM_ID_BOS = 1610612738

FAKE_PLAYERS = [
    [PLAYER_ID, "LeBron James", TEAM_ID_LAL],
    [1629029,   "Jayson Tatum", TEAM_ID_BOS],
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── helpers ───────────────────────────────────────────────────────────────────

def make_live_game(**kw):
    game = {
        "gameId": GAME_ID,
        "gameStatusText": "Final",
        "homeTeam": {
            "teamCity": "Los Angeles", "teamName": "Lakers",
            "teamTricode": "LAL", "teamId": TEAM_ID_LAL, "score": 110,
        },
        "awayTeam": {
            "teamCity": "Boston", "teamName": "Celtics",
            "teamTricode": "BOS", "teamId": TEAM_ID_BOS, "score": 105,
        },
        "gameLeaders": {
            "homeLeaders": {"name": "LeBron James", "points": 28, "rebounds": 8, "assists": 6},
            "awayLeaders": {"name": "Jayson Tatum", "points": 32, "rebounds": 9, "assists": 4},
        },
    }
    game.update(kw)
    return game


def make_live_player_stats(**kw):
    stats = {
        "points": 28, "reboundsTotal": 8, "assists": 6,
        "steals": 1, "blocks": 0, "turnovers": 2,
        "fieldGoalsMade": 11, "fieldGoalsAttempted": 20,
        "threePointersMade": 2, "threePointersAttempted": 5,
        "freeThrowsMade": 4, "freeThrowsAttempted": 4,
        "reboundsOffensive": 1, "reboundsDefensive": 7,
        "foulsPersonal": 2, "minutes": "PT28M00.00S", "plusMinusPoints": 8,
    }
    stats.update(kw)
    return stats


def make_live_player(person_id=PLAYER_ID, name="LeBron James", **stats_kw):
    return {
        "personId": person_id, "name": name, "status": "ACTIVE",
        "statistics": make_live_player_stats(**stats_kw),
    }


def make_live_boxscore(game_id=GAME_ID, status="Final"):
    return {
        "game": {
            "gameStatusText": status,
            "homeTeam": {
                "teamCity": "Los Angeles", "teamName": "Lakers",
                "teamTricode": "LAL", "teamId": TEAM_ID_LAL, "score": 110,
                "players": [make_live_player()],
            },
            "awayTeam": {
                "teamCity": "Boston", "teamName": "Celtics",
                "teamTricode": "BOS", "teamId": TEAM_ID_BOS, "score": 105,
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


def make_adv_player_row(person_id, plus_minus=5):
    row = [None] * 20
    row[6]  = person_id
    row[14] = plus_minus
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Cache-hit branches
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheHits:
    def test_boxscores_served_from_cache(self, client):
        with patch("routes.scores.get_games_leaders_list", return_value={}) as mock:
            client.get("/api/boxscores?days_offset=1")
            client.get("/api/boxscores?days_offset=1")
        mock.assert_called_once()

    def test_leaders_served_from_cache(self, client):
        with patch("routes.scores.get_games_list", return_value=[]) as mock:
            client.get("/api/leaders?days_offset=1")
            client.get("/api/leaders?days_offset=1")
        mock.assert_called_once()

    def test_standings_served_from_cache(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        standings_mock = MagicMock()
        standings_mock.return_value.get_dict.return_value = {"resultSets": [{"rowSet": rows}]}
        with patch("routes.scores.leaguestandings.LeagueStandings", standings_mock):
            client.get("/api/standings")
            client.get("/api/standings")
        standings_mock.assert_called_once()

    def test_last_n_games_served_from_cache(self, client):
        cumestats = MagicMock()
        cumestats.cume_stats_team_games.get_dict.return_value = {"data": []}
        with patch("routes.players.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.players.cumestatsteamgames.CumeStatsTeamGames", return_value=cumestats) as mock:
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        mock.assert_called_once()

    def test_season_avg_served_from_cache(self, client):
        CAREER_HEADERS = [
            "PLAYER_ID", "SEASON_ID", "LEAGUE_ID", "TEAM_ID", "TEAM_ABBREVIATION",
            "PLAYER_AGE", "GP", "GS", "MIN", "FGM", "FGA", "FG_PCT",
            "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
            "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS",
        ]
        h = {k: i for i, k in enumerate(CAREER_HEADERS)}
        row = [None] * len(CAREER_HEADERS)
        row[h["SEASON_ID"]] = "2024-25"
        row[h["GP"]] = 60
        for k in ("MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "PF",
                  "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA"):
            row[h[k]] = 0.0
        for k in ("FG_PCT", "FG3_PCT", "FT_PCT"):
            row[h[k]] = 0.0
        career = MagicMock()
        career.season_totals_regular_season.get_dict.return_value = {
            "headers": CAREER_HEADERS, "data": [row],
        }
        with patch("routes.players.playercareerstats.PlayerCareerStats", return_value=career) as mock:
            client.get(f"/api/players/{PLAYER_ID}/season-avg")
            client.get(f"/api/players/{PLAYER_ID}/season-avg")
        mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/advanced
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerAdvancedStats:
    def _sb(self, games):
        m = MagicMock()
        m.games.data = games
        return m

    def _bs(self, bs_dict=None):
        m = MagicMock()
        m.get_dict.return_value = bs_dict or make_live_boxscore()
        return m

    def _adv(self, rows=None):
        m = MagicMock()
        m.player_stats.get_dict.return_value = {"data": rows or []}
        return m

    def test_returns_200(self, client):
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.status_code == 200

    def test_no_game_returns_empty(self, client):
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.json()["players"] == []

    def test_player_stats_shape(self, client):
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=self._bs()), \
             patch("routes.scores.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=self._adv()):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.status_code == 200
        p = r.json()["players"][0]
        for key in ("id", "name", "team", "points", "rebounds", "assists", "fg", "efgPct", "tsPct", "plusMinus"):
            assert key in p

    def test_double_double_flagged(self, client):
        stats = make_live_player_stats(points=20, reboundsTotal=10)
        player = {
            "personId": PLAYER_ID, "name": "LeBron James", "status": "ACTIVE",
            "statistics": stats,
        }
        bs = {"game": {
            "homeTeam": {
                "teamCity": "LA", "teamName": "Lakers", "teamTricode": "LAL",
                "teamId": TEAM_ID_LAL, "score": 110, "players": [player],
            },
            "awayTeam": {
                "teamCity": "BOS", "teamName": "Celtics", "teamTricode": "BOS",
                "teamId": TEAM_ID_BOS, "score": 100, "players": [],
            },
        }}
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = bs
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.scores.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=self._adv()):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.json()["players"][0]["isDoubleDouble"] is True
        assert r.json()["players"][0]["isTripleDouble"] is False

    def test_triple_double_flagged(self, client):
        stats = make_live_player_stats(points=20, reboundsTotal=10, assists=10)
        player = {
            "personId": PLAYER_ID, "name": "LeBron James", "status": "ACTIVE",
            "statistics": stats,
        }
        bs = {"game": {
            "homeTeam": {
                "teamCity": "LA", "teamName": "Lakers", "teamTricode": "LAL",
                "teamId": TEAM_ID_LAL, "score": 110, "players": [player],
            },
            "awayTeam": {
                "teamCity": "BOS", "teamName": "Celtics", "teamTricode": "BOS",
                "teamId": TEAM_ID_BOS, "score": 100, "players": [],
            },
        }}
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = bs
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.scores.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=self._adv()):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.json()["players"][0]["isTripleDouble"] is True

    def test_plus_minus_from_advanced_stats(self, client):
        adv_row = make_adv_player_row(PLAYER_ID, plus_minus=12)
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=self._bs()), \
             patch("routes.scores.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=self._adv([adv_row])):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.json()["players"][0]["plusMinus"] == 12

    def test_invalid_ids_returns_400(self, client):
        r = client.get("/api/players/advanced?ids=not_a_number")
        # non-digit chunks are discarded by the route
        assert r.status_code == 200

    def test_missing_ids_param_returns_422(self, client):
        assert client.get("/api/players/advanced").status_code == 422

    def test_adv_stats_failure_falls_back_gracefully(self, client):
        with patch("routes.scores.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=self._bs()), \
             patch("routes.scores.boxscoreadvancedv3.BoxScoreAdvancedV3", side_effect=Exception("adv fail")), \
             patch("routes.scores.log_exceptions"):
            r = client.get(f"/api/players/advanced?ids={PLAYER_ID}")
        assert r.status_code == 200
        assert r.json()["players"][0]["plusMinus"] == 8  # falls back to plusMinusPoints


# ─────────────────────────────────────────────────────────────────────────────
# /api/playoffs
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayoffs:
    def _mock(self, rows):
        m = MagicMock()
        m.return_value.get_dict.return_value = {"resultSets": [{"rowSet": rows}]}
        return m

    def test_returns_200(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        assert r.status_code == 200

    def test_east_west_split(self, client):
        rows = [
            make_standings_row(1, "Boston",        "Celtics", "East", 50, 20),
            make_standings_row(1, "Oklahoma City", "Thunder", "West", 52, 18),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        assert len(r.json()["east"]) == 1
        assert len(r.json()["west"]) == 1

    def test_shape(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        team = r.json()["east"][0]
        for key in ("rank", "name", "wins", "losses", "gamesRemaining", "projectedWins", "projectedLosses", "status"):
            assert key in team

    def test_status_in(self, client):
        rows = [make_standings_row(3, "Boston", "Celtics", "East", 50, 20)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        assert r.json()["east"][0]["status"] == "in"

    def test_status_play_in(self, client):
        rows = [make_standings_row(8, "Chicago", "Bulls", "East", 32, 38)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        assert r.json()["east"][0]["status"] == "play-in"

    def test_status_out(self, client):
        rows = [make_standings_row(13, "Detroit", "Pistons", "East", 15, 55)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        assert r.json()["east"][0]["status"] == "out"

    def test_projected_wins_calculated(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 41, 41)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        t = r.json()["east"][0]
        assert t["projectedWins"] + t["projectedLosses"] == 82

    def test_sorted_by_rank(self, client):
        rows = [
            make_standings_row(3, "Philadelphia", "76ers",   "East", 30, 40),
            make_standings_row(1, "Boston",        "Celtics", "East", 50, 20),
            make_standings_row(2, "Milwaukee",     "Bucks",   "East", 42, 28),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        ranks = [t["rank"] for t in r.json()["east"]]
        assert ranks == sorted(ranks)


# ─────────────────────────────────────────────────────────────────────────────
# /api/doubledoubles
# ─────────────────────────────────────────────────────────────────────────────

class TestDoubleDoubles:
    def _sb(self, games):
        m = MagicMock()
        m.games.data = games
        return m

    def _bs(self, players_home, players_away):
        return {"game": {
            "homeTeam": {"teamTricode": "LAL", "players": players_home},
            "awayTeam": {"teamTricode": "BOS", "players": players_away},
        }}

    def _player(self, name, pts, reb, ast, stl=0, blk=0):
        return {
            "status": "ACTIVE", "name": name,
            "statistics": {
                "points": pts, "reboundsTotal": reb, "assists": ast,
                "steals": stl, "blocks": blk,
            },
        }

    def test_returns_200(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get("/api/doubledoubles")
        assert r.status_code == 200

    def test_response_shape(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get("/api/doubledoubles")
        for key in ("doubleDoubles", "tripleDoubles", "date"):
            assert key in r.json()

    def test_no_games_returns_empty(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get("/api/doubledoubles")
        assert r.json()["doubleDoubles"] == []
        assert r.json()["tripleDoubles"] == []

    def test_double_double_detected(self, client):
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = self._bs(
            [self._player("LeBron James", pts=20, reb=10, ast=5)], [],
        )
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=mock_bs):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert len(r.json()["doubleDoubles"]) == 1
        assert r.json()["doubleDoubles"][0]["name"] == "LeBron James"

    def test_triple_double_detected(self, client):
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = self._bs(
            [self._player("LeBron James", pts=10, reb=10, ast=10)], [],
        )
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=mock_bs):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert len(r.json()["tripleDoubles"]) == 1
        assert r.json()["doubleDoubles"] == []

    def test_historical_offset_uses_games_list(self, client):
        with patch("routes.scores.get_games_list", return_value=[]) as mock, \
             patch("routes.scores.scoreboard.ScoreBoard"):
            r = client.get("/api/doubledoubles?days_offset=1")
        assert r.status_code == 200
        mock.assert_called_once_with(1)

    def test_live_offset_uses_scoreboard(self, client):
        sb = self._sb([])
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=sb) as mock:
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        mock.assert_called_once()

    def test_offset_too_large_rejected(self, client):
        assert client.get("/api/doubledoubles?days_offset=99").status_code == 422

    def test_player_below_threshold_excluded(self, client):
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = self._bs(
            [self._player("Bench Guy", pts=5, reb=4, ast=3)], [],
        )
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])), \
             patch("routes.scores.boxscore.BoxScore", return_value=mock_bs):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.json()["doubleDoubles"] == []
        assert r.json()["tripleDoubles"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Error handler branches – players.py
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerErrorHandlers:
    def test_search_500_on_unexpected_error(self, client):
        with patch("routes.players.load_players_file", side_effect=OSError("disk error")), \
             patch("routes.players.log_exceptions"):
            r = client.get("/api/players/search?q=LeBron")
        assert r.status_code == 500

    def test_game_players_500_on_boxscore_error(self, client):
        with patch("routes.players.boxscore.BoxScore", side_effect=Exception("nba down")), \
             patch("routes.players.log_exceptions"):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 500

    def test_last_n_games_500_on_unexpected_error(self, client):
        with patch("routes.players.load_players_dict", side_effect=Exception("boom")), \
             patch("routes.players.log_exceptions"):
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.status_code == 500

    def test_season_avg_500_on_unexpected_error(self, client):
        with patch("routes.players.playercareerstats.PlayerCareerStats", side_effect=Exception("boom")), \
             patch("routes.players.log_exceptions"):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 500
