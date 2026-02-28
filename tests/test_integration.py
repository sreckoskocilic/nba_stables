"""Integration tests for the NBA Stables FastAPI application."""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from helpers.common import cache
from main import app

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
GAME_ID = "0022301234"
PLAYER_ID = 2544          # LeBron James
TEAM_ID_LAL = 1610612747
TEAM_ID_BOS = 1610612738

FAKE_PLAYERS = [
    [PLAYER_ID, "LeBron James", TEAM_ID_LAL],
    [1629029, "Jayson Tatum", TEAM_ID_BOS],
]

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Mock data builders
# ─────────────────────────────────────────────────────────────────────────────

def make_live_game(**kw):
    game = {
        "gameId": GAME_ID,
        "gameStatusText": "7:30 pm ET",
        "homeTeam": {
            "teamCity": "Los Angeles", "teamName": "Lakers",
            "teamTricode": "LAL", "teamId": TEAM_ID_LAL, "score": 0,
        },
        "awayTeam": {
            "teamCity": "Boston", "teamName": "Celtics",
            "teamTricode": "BOS", "teamId": TEAM_ID_BOS, "score": 0,
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


def make_live_boxscore(game_id=GAME_ID, status="Q2 5:32"):
    return {
        "game": {
            "gameStatusText": status,
            "homeTeam": {
                "teamCity": "Los Angeles", "teamName": "Lakers",
                "teamTricode": "LAL", "teamId": TEAM_ID_LAL, "score": 56,
                "players": [make_live_player()],
            },
            "awayTeam": {
                "teamCity": "Boston", "teamName": "Celtics",
                "teamTricode": "BOS", "teamId": TEAM_ID_BOS, "score": 48,
                "players": [make_live_player(person_id=1629029, name="Jayson Tatum")],
            },
        }
    }


def make_standings_row(rank, city, name, conf, wins, losses):
    """Build a row matching indices used by get_standings."""
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


def make_boxscore_team_row(team_id, city, name, score=100):
    """Build a BoxScoreTraditionalV3 team_stats row (len=26, score at [-2])."""
    row = [None] * 26
    row[1] = team_id
    row[2] = city
    row[3] = name
    row[7] = 40
    row[8] = 80
    row[9] = 0.500
    row[10] = 10
    row[11] = 25
    row[12] = 0.400
    row[13] = 15
    row[14] = 20
    row[15] = 0.750
    row[16] = 5
    row[17] = 30
    row[18] = 35
    row[19] = 20
    row[20] = 5
    row[21] = 3
    row[22] = 10
    row[23] = 15
    row[24] = score   # row[-2]
    return row


def make_player_stats_row(person_id=PLAYER_ID, minutes="28:00"):
    """Build a BoxScoreTraditionalV3 player_stats row."""
    row = [None] * 33
    row[6]  = person_id
    row[14] = minutes    # non-empty → player played
    row[15] = 11   # FGM
    row[16] = 20   # FGA
    row[18] = 2    # 3PM
    row[19] = 5    # 3PA
    row[21] = 4    # FTM
    row[22] = 4    # FTA
    row[26] = 8    # REB
    row[27] = 6    # AST
    row[28] = 0    # BLK
    row[29] = 1    # STL
    row[31] = 2    # PF
    row[32] = 28   # PTS
    return row


CAREER_HEADERS = [
    "PLAYER_ID", "SEASON_ID", "LEAGUE_ID", "TEAM_ID", "TEAM_ABBREVIATION",
    "PLAYER_AGE", "GP", "GS", "MIN", "FGM", "FGA", "FG_PCT",
    "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
    "OREB", "DREB", "REB", "AST", "STL", "BLK", "TOV", "PF", "PTS",
]

def make_career_row(gp=60):
    h = {k: i for i, k in enumerate(CAREER_HEADERS)}
    row = [None] * len(CAREER_HEADERS)
    row[h["SEASON_ID"]] = "2024-25"
    row[h["GP"]]  = gp
    row[h["MIN"]] = 1800.0
    row[h["PTS"]] = 1680.0   # 28.0 ppg
    row[h["REB"]] = 480.0    # 8.0 rpg
    row[h["AST"]] = 360.0    # 6.0 apg
    row[h["STL"]] = 60.0
    row[h["BLK"]] = 36.0
    row[h["TOV"]] = 120.0
    row[h["PF"]]  = 90.0
    row[h["FGM"]] = 660.0
    row[h["FGA"]] = 1200.0
    row[h["FG_PCT"]] = 0.55
    row[h["FG3M"]] = 120.0
    row[h["FG3A"]] = 300.0
    row[h["FG3_PCT"]] = 0.40
    row[h["FTM"]] = 240.0
    row[h["FTA"]] = 300.0
    row[h["FT_PCT"]] = 0.80
    return row


# ─────────────────────────────────────────────────────────────────────────────
# /api/health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_200(self, client):
        assert client.get("/api/health").status_code == 200

    def test_shape(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "healthy"
        assert "date" in body and len(body["date"]) > 5


# ─────────────────────────────────────────────────────────────────────────────
# /api/dates
# ─────────────────────────────────────────────────────────────────────────────

class TestDates:
    def test_returns_200(self, client):
        assert client.get("/api/dates").status_code == 200

    def test_returns_8_dates(self, client):
        assert len(client.get("/api/dates").json()["dates"]) == 8

    def test_all_strings(self, client):
        for d in client.get("/api/dates").json()["dates"]:
            assert isinstance(d, str) and len(d) > 0


# ─────────────────────────────────────────────────────────────────────────────
# /api/injuries
# ─────────────────────────────────────────────────────────────────────────────

INJURY_PAYLOAD = {
    "injuries": [{"team": "Los Angeles Lakers", "players": [
        {"name": "LeBron James", "injury": "Foot", "status": "Day-To-Day", "updated": "Today"},
    ]}],
    "lastUpdated": "2025-02-28",
    "source": "CBS Sports",
}

class TestInjuries:
    def test_503_when_file_missing(self, client):
        with patch("main.os.path.exists", return_value=False):
            r = client.get("/api/injuries")
        assert r.status_code == 503

    def test_returns_data_from_file(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(INJURY_PAYLOAD, f)
            tmp = f.name
        try:
            with patch("main.CBS_INJURIES_FILE", tmp):
                r = client.get("/api/injuries")
            assert r.status_code == 200
            assert r.json()["injuries"][0]["team"] == "Los Angeles Lakers"
        finally:
            os.unlink(tmp)

    def test_second_request_served_from_cache(self, client):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(INJURY_PAYLOAD, f)
            tmp = f.name
        try:
            with patch("main.CBS_INJURIES_FILE", tmp):
                r1 = client.get("/api/injuries")
                r2 = client.get("/api/injuries")
            assert r1.json() == r2.json()
        finally:
            os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# /api/scoreboard
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreboard:
    def _sb(self, games):
        m = MagicMock()
        m.games.data = games
        return m

    def test_empty_games(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get("/api/scoreboard")
        assert r.status_code == 200
        assert r.json()["games"] == []

    def test_game_shape(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game(gameStatusText="Final")])):
            r = client.get("/api/scoreboard")
        g = r.json()["games"][0]
        assert g["homeTeam"]["tricode"] == "LAL"
        assert g["awayTeam"]["tricode"] == "BOS"
        assert g["status"] == "Final"

    def test_et_time_converted(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game()])):
            r = client.get("/api/scoreboard")
        # "7:30 pm ET" should be converted; original format ends with " ET"
        assert not r.json()["games"][0]["status"].endswith(" ET")

    def test_has_date(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])):
            r = client.get("/api/scoreboard")
        assert "date" in r.json()

    def test_leader_stats_present(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([make_live_game(gameStatusText="Final")])):
            r = client.get("/api/scoreboard")
        home = r.json()["games"][0]["homeTeam"]
        assert home["leader"]["points"] == 28
        assert home["leader"]["rebounds"] == 8

    def test_cached_on_second_call(self, client):
        with patch("routes.scores.scoreboard.ScoreBoard", return_value=self._sb([])) as mock:
            client.get("/api/scoreboard")
            client.get("/api/scoreboard")
        mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# /api/boxscores
# ─────────────────────────────────────────────────────────────────────────────

_BOXSCORE_RESULT = {
    "gameId": GAME_ID,
    "teams": [
        {"name": "Los Angeles Lakers", "score": 110, "stats": {
            "fg": "40/80", "fgPct": 0.5, "threePt": "10/25", "threePtPct": 0.4,
            "ft": "15/20", "ftPct": 0.75, "rebounds": 35, "offRebounds": 5,
            "assists": 20, "steals": 5, "blocks": 3, "turnovers": 10, "fouls": 15,
        }, "leader": {"name": "LeBron James", "points": 28, "rebounds": 8, "assists": 6}},
        {"name": "Boston Celtics", "score": 105, "stats": {
            "fg": "40/80", "fgPct": 0.5, "threePt": "10/25", "threePtPct": 0.4,
            "ft": "15/20", "ftPct": 0.75, "rebounds": 35, "offRebounds": 5,
            "assists": 20, "steals": 5, "blocks": 3, "turnovers": 10, "fouls": 15,
        }, "leader": {"name": "Jayson Tatum", "points": 32, "rebounds": 9, "assists": 4}},
    ],
}

class TestBoxscores:
    def test_no_games(self, client):
        with patch("routes.scores.get_games_leaders_list", return_value={}):
            r = client.get("/api/boxscores?days_offset=1")
        assert r.status_code == 200
        assert r.json()["boxscores"] == []

    def test_returns_team_data(self, client):
        leaders = {GAME_ID: [["LeBron James", 28, 8, 6, TEAM_ID_LAL]]}
        with patch("routes.scores.get_games_leaders_list", return_value=leaders), \
             patch("routes.scores.fetch_single_boxscore", return_value=_BOXSCORE_RESULT):
            r = client.get("/api/boxscores?days_offset=1")
        assert r.status_code == 200
        teams = r.json()["boxscores"][0]["teams"]
        assert teams[0]["name"] == "Los Angeles Lakers"
        assert teams[0]["score"] == 110

    def test_offset_too_large_rejected(self, client):
        assert client.get("/api/boxscores?days_offset=99").status_code == 422

    def test_has_date_field(self, client):
        with patch("routes.scores.get_games_leaders_list", return_value={}):
            r = client.get("/api/boxscores?days_offset=1")
        assert "date" in r.json()

    def test_default_offset(self, client):
        with patch("routes.scores.get_games_leaders_list", return_value={}) as mock:
            client.get("/api/boxscores")
        mock.assert_called_once_with(1)


# ─────────────────────────────────────────────────────────────────────────────
# /api/leaders
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaders:
    def _bs(self):
        m = MagicMock()
        m.get_dict.return_value = {"game": {
            "homeTeam": {"teamTricode": "LAL", "players": [{
                "status": "ACTIVE", "name": "LeBron James",
                "statistics": {"points": 35, "reboundsTotal": 10, "assists": 8,
                               "blocks": 2, "steals": 3, "threePointersMade": 4},
            }]},
            "awayTeam": {"teamTricode": "BOS", "players": [{
                "status": "ACTIVE", "name": "Jayson Tatum",
                "statistics": {"points": 30, "reboundsTotal": 8, "assists": 5,
                               "blocks": 1, "steals": 2, "threePointersMade": 3},
            }]},
        }}
        return m

    def test_no_games_returns_empty(self, client):
        with patch("routes.scores.get_games_list", return_value=[]):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}

    def test_points_leader_computed(self, client):
        with patch("routes.scores.get_games_list", return_value=[GAME_ID]), \
             patch("routes.scores.boxscore.BoxScore", return_value=self._bs()):
            r = client.get("/api/leaders?days_offset=1")
        leaders = r.json()["leaders"]
        assert leaders["points"]["value"] == 35
        assert leaders["points"]["players"][0]["name"] == "LeBron James"

    def test_all_categories_present(self, client):
        with patch("routes.scores.get_games_list", return_value=[GAME_ID]), \
             patch("routes.scores.boxscore.BoxScore", return_value=self._bs()):
            r = client.get("/api/leaders?days_offset=1")
        for cat in ("points", "rebounds", "assists", "blocks", "steals", "threePointers"):
            assert cat in r.json()["leaders"]

    def test_offset_too_large_rejected(self, client):
        assert client.get("/api/leaders?days_offset=10").status_code == 422

    def test_has_date_field(self, client):
        with patch("routes.scores.get_games_list", return_value=[]):
            r = client.get("/api/leaders?days_offset=1")
        assert "date" in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# /api/standings
# ─────────────────────────────────────────────────────────────────────────────

class TestStandings:
    def _mock(self, rows):
        m = MagicMock()
        m.return_value.get_dict.return_value = {"resultSets": [{"rowSet": rows}]}
        return m

    def test_east_and_west_split(self, client):
        rows = [
            make_standings_row(1, "Boston",        "Celtics", "East", 50, 20),
            make_standings_row(1, "Oklahoma City", "Thunder", "West", 52, 18),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/standings")
        body = r.json()
        assert len(body["east"]) == 1
        assert len(body["west"]) == 1

    def test_sorted_by_rank(self, client):
        rows = [
            make_standings_row(3, "Philadelphia", "76ers",   "East", 30, 40),
            make_standings_row(1, "Boston",        "Celtics", "East", 50, 20),
            make_standings_row(2, "Milwaukee",     "Bucks",   "East", 42, 28),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/standings")
        ranks = [t["rank"] for t in r.json()["east"]]
        assert ranks == sorted(ranks)

    def test_team_data_shape(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/standings")
        team = r.json()["east"][0]
        for key in ("rank", "name", "wins", "losses", "winPct", "gamesBack", "streak", "last10"):
            assert key in team


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/search
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerSearch:
    def test_finds_player(self, client):
        with patch("routes.players.load_players_file", return_value=FAKE_PLAYERS):
            r = client.get("/api/players/search?q=LeBron")
        assert r.status_code == 200
        assert r.json()["players"][0]["name"] == "LeBron James"

    def test_case_insensitive(self, client):
        with patch("routes.players.load_players_file", return_value=FAKE_PLAYERS):
            r = client.get("/api/players/search?q=lebron")
        assert r.json()["players"][0]["name"] == "LeBron James"

    def test_query_too_short_rejected(self, client):
        assert client.get("/api/players/search?q=L").status_code == 422

    def test_no_match_returns_empty(self, client):
        with patch("routes.players.load_players_file", return_value=FAKE_PLAYERS):
            r = client.get("/api/players/search?q=Kobe")
        assert r.json()["players"] == []

    def test_capped_at_20_results(self, client):
        many = [[i, f"Player {i:02d}", 0] for i in range(30)]
        with patch("routes.players.load_players_file", return_value=many):
            r = client.get("/api/players/search?q=Player")
        assert len(r.json()["players"]) <= 20


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestPlayerStats:
    def test_returns_live_stats(self, client):
        mock_sb = MagicMock()
        mock_sb.games.data = [make_live_game()]
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = make_live_boxscore()

        with patch("routes.players.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.players.scoreboard.ScoreBoard", return_value=mock_sb), \
             patch("routes.players.boxscore.BoxScore", return_value=mock_bs):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")

        assert r.status_code == 200
        players = r.json()["players"]
        assert len(players) == 1
        assert players[0]["points"] == 28
        assert players[0]["team"] == "LAL"

    def test_invalid_id_returns_400(self, client):
        assert client.get("/api/players/stats?ids=not_a_number").status_code == 400

    def test_player_not_in_game_returns_empty(self, client):
        mock_sb = MagicMock()
        mock_sb.games.data = []
        with patch("routes.players.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.players.scoreboard.ScoreBoard", return_value=mock_sb):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.json()["players"] == []


# ─────────────────────────────────────────────────────────────────────────────
# /api/games/{game_id}/players
# ─────────────────────────────────────────────────────────────────────────────

class TestGamePlayers:
    def _setup(self, bs_dict=None):
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = bs_dict or make_live_boxscore()
        mock_adv = MagicMock()
        mock_adv.player_stats.get_dict.return_value = {"data": []}
        return mock_bs, mock_adv

    def test_returns_two_teams(self, client):
        mock_bs, mock_adv = self._setup()
        with patch("routes.players.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.players.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=mock_adv):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 200
        assert len(r.json()["teams"]) == 2

    def test_player_stats_present(self, client):
        mock_bs, mock_adv = self._setup()
        with patch("routes.players.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.players.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=mock_adv):
            r = client.get(f"/api/games/{GAME_ID}/players")
        lal = next(t for t in r.json()["teams"] if t["tricode"] == "LAL")
        assert lal["players"][0]["points"] == 28

    def test_player_data_shape(self, client):
        mock_bs, mock_adv = self._setup()
        with patch("routes.players.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.players.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=mock_adv):
            r = client.get(f"/api/games/{GAME_ID}/players")
        p = r.json()["teams"][0]["players"][0]
        for key in ("name", "minutes", "points", "rebounds", "assists", "fg", "threePt", "ft"):
            assert key in p

    def test_advanced_stats_fallback_when_unavailable(self, client):
        mock_bs = MagicMock()
        mock_bs.get_dict.return_value = make_live_boxscore()
        mock_adv = MagicMock()
        mock_adv.player_stats.get_dict.side_effect = Exception("unavailable")

        with patch("routes.players.boxscore.BoxScore", return_value=mock_bs), \
             patch("routes.players.boxscoreadvancedv3.BoxScoreAdvancedV3", return_value=mock_adv):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 200
        assert r.json()["teams"][0]["players"][0]["plusMinus"] == 8  # falls back to plusMinusPoints


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/{id}/last-n-games
# ─────────────────────────────────────────────────────────────────────────────

class TestLastNGames:
    def _cumestats(self):
        m = MagicMock()
        m.cume_stats_team_games.get_dict.return_value = {
            "data": [["2025-02-27 vs BOS", GAME_ID]]
        }
        return m

    def _trad_boxscore(self, person_id=PLAYER_ID):
        m = MagicMock()
        m.player_stats.get_dict.return_value = {
            "data": [make_player_stats_row(person_id)]
        }
        return m

    def test_returns_game_log(self, client):
        with patch("routes.players.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.players.cumestatsteamgames.CumeStatsTeamGames", return_value=self._cumestats()), \
             patch("routes.players.boxscoretraditionalv3.BoxScoreTraditionalV3", return_value=self._trad_boxscore()):
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.status_code == 200
        body = r.json()
        assert body["playerId"] == PLAYER_ID
        assert body["games"][0]["points"] == 28
        assert body["games"][0]["dnp"] is False

    def test_unknown_player_404(self, client):
        with patch("routes.players.load_players_dict", return_value={}):
            r = client.get("/api/players/9999999/last-n-games?n=5")
        assert r.status_code == 404

    def test_n_out_of_range_rejected(self, client):
        assert client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=99").status_code == 422

    def test_dnp_game_flagged(self, client):
        empty_bs = MagicMock()
        empty_bs.player_stats.get_dict.return_value = {"data": []}
        with patch("routes.players.load_players_dict", return_value={p[0]: p for p in FAKE_PLAYERS}), \
             patch("routes.players.cumestatsteamgames.CumeStatsTeamGames", return_value=self._cumestats()), \
             patch("routes.players.boxscoretraditionalv3.BoxScoreTraditionalV3", return_value=empty_bs):
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.json()["games"][0]["dnp"] is True


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/{id}/season-avg
# ─────────────────────────────────────────────────────────────────────────────

class TestSeasonAvg:
    def _mock_career(self, rows=None):
        m = MagicMock()
        m.season_totals_regular_season.get_dict.return_value = {
            "headers": CAREER_HEADERS,
            "data": rows if rows is not None else [make_career_row()],
        }
        return m

    def test_returns_averages(self, client):
        with patch("routes.players.playercareerstats.PlayerCareerStats", return_value=self._mock_career()):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 200
        body = r.json()
        assert body["points"] == 28.0
        assert body["rebounds"] == 8.0
        assert body["gp"] == 60

    def test_response_shape(self, client):
        with patch("routes.players.playercareerstats.PlayerCareerStats", return_value=self._mock_career()):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        for key in ("season", "gp", "points", "rebounds", "assists", "fgPct", "fg3Pct", "ftPct"):
            assert key in r.json()

    def test_no_data_returns_404(self, client):
        with patch("routes.players.playercareerstats.PlayerCareerStats", return_value=self._mock_career(rows=[])):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 404
