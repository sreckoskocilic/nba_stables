"""Integration tests for the NBA Stables FastAPI application."""

import json
import os
import tempfile
import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests
from conftest import (
    CAREER_HEADERS,
    FAKE_PLAYERS,
    GAME_ID,
    PLAYER_ID,
    TEAM_ID_BOS,
    TEAM_ID_LAL,
    make_live_boxscore,
    make_live_game,
    make_scoreboard_v3,
    make_standings_row,
)
from fastapi.testclient import TestClient
from helpers.common import cache
from main import app

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
    row[24] = score  # row[-2]
    return row


def make_player_stats_row(person_id=PLAYER_ID, minutes="28:00"):
    """Build a BoxScoreTraditionalV3 player_stats row."""
    row = [None] * 33
    row[6] = person_id
    row[14] = minutes  # non-empty → player played
    row[15] = 11  # FGM
    row[16] = 20  # FGA
    row[18] = 2  # 3PM
    row[19] = 5  # 3PA
    row[21] = 4  # FTM
    row[22] = 4  # FTA
    row[26] = 8  # REB
    row[27] = 6  # AST
    row[28] = 0  # BLK
    row[29] = 1  # STL
    row[31] = 2  # PF
    row[32] = 28  # PTS
    return row


def make_career_row(gp=60):
    h = {k: i for i, k in enumerate(CAREER_HEADERS)}
    row = [None] * len(CAREER_HEADERS)
    row[h["SEASON_ID"]] = "2024-25"
    row[h["GP"]] = gp
    row[h["MIN"]] = 1800.0
    row[h["PTS"]] = 1680.0  # 28.0 ppg
    row[h["REB"]] = 480.0  # 8.0 rpg
    row[h["AST"]] = 360.0  # 6.0 apg
    row[h["STL"]] = 60.0
    row[h["BLK"]] = 36.0
    row[h["TOV"]] = 120.0
    row[h["PF"]] = 90.0
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
        with (
            patch("main._stats._players_cache", [1]),
            patch("main._stats._players_cache_expires", time.time() + 300),
        ):
            body = client.get("/api/health").json()
        assert body["status"] == "healthy"
        assert body["cache_ok"] is True
        assert "date" in body and len(body["date"]) > 5


# ─────────────────────────────────────────────────────────────────────────────
# /api/dates
# ─────────────────────────────────────────────────────────────────────────────


class TestDates:
    @pytest.fixture(autouse=True)
    def mock_games_list(self):
        with patch("routes.scores.get_games_list", return_value=[]):
            yield

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
    "injuries": [
        {
            "team": "Los Angeles Lakers",
            "players": [
                {
                    "name": "LeBron James",
                    "injury": "Foot",
                    "status": "Day-To-Day",
                    "updated": "Today",
                },
            ],
        }
    ],
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
            with patch("routes.injuries.CBS_INJURIES_FILE", tmp):
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
            with patch("routes.injuries.CBS_INJURIES_FILE", tmp):
                r1 = client.get("/api/injuries")
                r2 = client.get("/api/injuries")
            assert r1.json() == r2.json()
        finally:
            os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# /api/scoreboard
# ─────────────────────────────────────────────────────────────────────────────


class TestScoreboard:
    def _patch_sb(self, games=None, live_raw=None):
        """Return a context manager that mocks the scoreboard endpoint dependencies."""
        from contextlib import ExitStack
        from datetime import date

        stack = ExitStack()
        sb_v3 = make_scoreboard_v3(games or [])
        stack.enter_context(
            patch("routes.scores.get_scoreboard_v3_by_date", return_value=sb_v3)
        )
        stack.enter_context(
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7))
        )
        stack.enter_context(
            patch("routes.scores.get_cached_scoreboard", return_value=live_raw or [])
        )
        return stack

    def test_empty_games(self, client):
        with self._patch_sb([]):
            r = client.get("/api/scoreboard")
        assert r.status_code == 200
        assert r.json()["games"] == []

    def test_game_shape(self, client):
        with self._patch_sb([make_live_game(gameStatusText="Final")]):
            r = client.get("/api/scoreboard")
        g = r.json()["games"][0]
        assert g["homeTeam"]["tricode"] == "LAL"
        assert g["awayTeam"]["tricode"] == "BOS"
        assert g["status"] == "Final"

    def test_et_time_converted(self, client):
        with self._patch_sb([make_live_game(gameStatusText="7:30 pm ET")]):
            r = client.get("/api/scoreboard")
        assert not r.json()["games"][0]["status"].endswith(" ET")

    def test_has_date(self, client):
        with self._patch_sb([]):
            r = client.get("/api/scoreboard")
        assert "date" in r.json()

    def test_leader_stats_present(self, client):
        with self._patch_sb([make_live_game(gameStatusText="Final")]):
            r = client.get("/api/scoreboard")
        home = r.json()["games"][0]["homeTeam"]
        assert home["leader"]["points"] == 28
        assert home["leader"]["rebounds"] == 8

    def test_live_et_time_converted(self, client):
        """Live scoreboard game with ET time gets converted to CET."""
        live_game = make_live_game(gameStatus=2, gameStatusText="7:00 pm ET")
        with self._patch_sb(
            [make_live_game(gameStatusText="Q2 5:30")], live_raw=[live_game]
        ):
            r = client.get("/api/scoreboard")
        assert "CET" in r.json()["games"][0]["status"]

    def test_missing_line_score_fallback(self, client):
        """Game in header but no matching line_score rows -> empty team fallback."""
        sb = MagicMock()
        # Header has one game, but line_score has no rows for it
        sb.game_header.get_dict.return_value = {
            "data": [
                [
                    GAME_ID,
                    "20260307/BOSLAL",
                    1,
                    "7:00 pm ET",
                    0,
                    "",
                    "2026-03-08T00:00:00Z",
                    "2026-03-07T19:00:00Z",
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
            ]
        }
        sb.line_score.get_dict.return_value = {"data": []}
        sb.game_leaders.get_dict.return_value = {"data": []}

        with (
            patch("routes.scores.get_scoreboard_v3_by_date", return_value=sb),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
        ):
            r = client.get("/api/scoreboard")

        g = r.json()["games"][0]
        assert g["homeTeam"]["name"] == ""
        assert g["homeTeam"]["score"] == 0
        assert g["awayTeam"]["name"] == ""
        assert g["awayTeam"]["score"] == 0

    def test_two_calls_both_succeed(self, client):
        with self._patch_sb([]):
            r1 = client.get("/api/scoreboard")
            r2 = client.get("/api/scoreboard")
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_get_cached_scoreboard_exception_falls_back(self, client):
        """If get_cached_scoreboard() raises, started_ids is empty and V3 data is used."""
        v3_game = make_live_game(gameStatusText="7:00 pm ET")
        sb_v3 = make_scoreboard_v3([v3_game])
        with (
            patch("routes.scores.get_scoreboard_v3_by_date", return_value=sb_v3),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
            patch("routes.scores.get_cached_scoreboard", side_effect=Exception("boom")),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 200
        # Falls back to V3 data (ET time not converted because live merge skipped)
        assert r.json()["games"][0]["status"] != ""

    def test_mixed_started_unstarted_games(self, client):
        """Only started games get live data; unstarted games keep V3 data."""
        started_id = GAME_ID
        unstarted_id = "0022500001"

        started_live = make_live_game(
            gameId=started_id, gameStatus=2, gameStatusText="Q2 5:30"
        )
        unstarted_live = make_live_game(
            gameId=unstarted_id, gameStatus=1, gameStatusText="9:00 pm ET"
        )

        v3_started = make_live_game(gameStatusText="Q1 10:00")
        v3_unstarted = make_live_game(gameStatusText="9:00 pm ET")
        # Override gameId for unstarted V3 game
        v3_unstarted["gameId"] = unstarted_id

        sb_v3 = make_scoreboard_v3([v3_started, v3_unstarted])
        with (
            patch("routes.scores.get_scoreboard_v3_by_date", return_value=sb_v3),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
            patch(
                "routes.scores.get_cached_scoreboard",
                return_value=[started_live, unstarted_live],
            ),
        ):
            r = client.get("/api/scoreboard")

        games = {g["gameId"]: g for g in r.json()["games"]}
        assert games[started_id]["status"] == "Q2 5:30"
        assert (
            "ET" in games[unstarted_id]["status"]
            or "CET" in games[unstarted_id]["status"]
        )


# ─────────────────────────────────────────────────────────────────────────────
# /api/boxscores
# ─────────────────────────────────────────────────────────────────────────────

_BOXSCORE_RESULT = {
    "gameId": GAME_ID,
    "teams": [
        {
            "name": "Los Angeles Lakers",
            "score": 110,
            "stats": {
                "fg": "40/80",
                "fgPct": 0.5,
                "threePt": "10/25",
                "threePtPct": 0.4,
                "ft": "15/20",
                "ftPct": 0.75,
                "rebounds": 35,
                "offRebounds": 5,
                "assists": 20,
                "steals": 5,
                "blocks": 3,
                "turnovers": 10,
                "fouls": 15,
            },
            "leader": {
                "name": "LeBron James",
                "points": 28,
                "rebounds": 8,
                "assists": 6,
            },
        },
        {
            "name": "Boston Celtics",
            "score": 105,
            "stats": {
                "fg": "40/80",
                "fgPct": 0.5,
                "threePt": "10/25",
                "threePtPct": 0.4,
                "ft": "15/20",
                "ftPct": 0.75,
                "rebounds": 35,
                "offRebounds": 5,
                "assists": 20,
                "steals": 5,
                "blocks": 3,
                "turnovers": 10,
                "fouls": 15,
            },
            "leader": {
                "name": "Jayson Tatum",
                "points": 32,
                "rebounds": 9,
                "assists": 4,
            },
        },
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
        with (
            patch("routes.scores.get_games_leaders_list", return_value=leaders),
            patch("routes.scores.fetch_single_boxscore", return_value=_BOXSCORE_RESULT),
        ):
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

    def test_one_game_fails_others_succeed(self, client):
        """A game returning None (internal error) is skipped; successful games are still returned."""
        good_id = "0022500001"
        bad_id = "0022500002"
        leaders = {
            good_id: [["LeBron James", 28, 8, 6, TEAM_ID_LAL]],
            bad_id: [["Jayson Tatum", 32, 9, 4, TEAM_ID_BOS]],
        }

        def _fetch(game_id, leaders_data):
            if game_id == bad_id:
                return None  # fetch_single_boxscore returns None on error
            return _BOXSCORE_RESULT

        with (
            patch("routes.scores.get_games_leaders_list", return_value=leaders),
            patch("routes.scores.fetch_single_boxscore", side_effect=_fetch),
        ):
            r = client.get("/api/boxscores?days_offset=1")

        assert r.status_code == 200
        assert len(r.json()["boxscores"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# /api/leaders
# ─────────────────────────────────────────────────────────────────────────────


class TestLeaders:
    def _bs_dict(self):
        return {
            "game": {
                "homeTeam": {
                    "teamTricode": "LAL",
                    "players": [
                        {
                            "status": "ACTIVE",
                            "name": "LeBron James",
                            "statistics": {
                                "points": 35,
                                "reboundsTotal": 10,
                                "assists": 8,
                                "blocks": 2,
                                "steals": 3,
                                "threePointersMade": 4,
                            },
                        }
                    ],
                },
                "awayTeam": {
                    "teamTricode": "BOS",
                    "players": [
                        {
                            "status": "ACTIVE",
                            "name": "Jayson Tatum",
                            "statistics": {
                                "points": 30,
                                "reboundsTotal": 8,
                                "assists": 5,
                                "blocks": 1,
                                "steals": 2,
                                "threePointersMade": 3,
                            },
                        }
                    ],
                },
            }
        }

    def test_no_games_returns_empty(self, client):
        with patch("routes.scores.get_games_list", return_value=[]):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}

    def test_points_leader_computed(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch(
                "routes.scores.get_cached_live_boxscore", return_value=self._bs_dict()
            ),
        ):
            r = client.get("/api/leaders?days_offset=1")
        leaders = r.json()["leaders"]
        assert leaders["points"]["value"] == 35
        assert leaders["points"]["players"][0]["name"] == "LeBron James"

    def test_all_categories_present(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch(
                "routes.scores.get_cached_live_boxscore", return_value=self._bs_dict()
            ),
        ):
            r = client.get("/api/leaders?days_offset=1")
        for cat in (
            "points",
            "rebounds",
            "assists",
            "blocks",
            "steals",
            "threePointers",
        ):
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
            make_standings_row(1, "Boston", "Celtics", "East", 50, 20),
            make_standings_row(1, "Oklahoma City", "Thunder", "West", 52, 18),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/standings")
        body = r.json()
        assert len(body["east"]) == 1
        assert len(body["west"]) == 1

    def test_sorted_by_rank(self, client):
        rows = [
            make_standings_row(3, "Philadelphia", "76ers", "East", 30, 40),
            make_standings_row(1, "Boston", "Celtics", "East", 50, 20),
            make_standings_row(2, "Milwaukee", "Bucks", "East", 42, 28),
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
        for key in (
            "rank",
            "name",
            "wins",
            "losses",
            "winPct",
            "gamesBack",
            "streak",
            "last10",
        ):
            assert key in team


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/search
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayerSearch:
    def test_finds_player(self, client):
        with patch(
            "routes.players.load_players_with_lower",
            return_value=[(p, p[1].lower()) for p in FAKE_PLAYERS],
        ):
            r = client.get("/api/players/search?q=LeBron")
        assert r.status_code == 200
        assert r.json()["players"][0]["name"] == "LeBron James"

    def test_case_insensitive(self, client):
        with patch(
            "routes.players.load_players_with_lower",
            return_value=[(p, p[1].lower()) for p in FAKE_PLAYERS],
        ):
            r = client.get("/api/players/search?q=lebron")
        assert r.json()["players"][0]["name"] == "LeBron James"

    def test_query_too_short_rejected(self, client):
        assert client.get("/api/players/search?q=L").status_code == 422

    def test_no_match_returns_empty(self, client):
        with patch(
            "routes.players.load_players_with_lower",
            return_value=[(p, p[1].lower()) for p in FAKE_PLAYERS],
        ):
            r = client.get("/api/players/search?q=Kobe")
        assert r.json()["players"] == []

    def test_capped_at_20_results(self, client):
        many = [[i, f"Player {i:02d}", 0] for i in range(30)]
        with patch(
            "routes.players.load_players_with_lower",
            return_value=[(p, p[1].lower()) for p in many],
        ):
            r = client.get("/api/players/search?q=Player")
        assert len(r.json()["players"]) <= 20


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/stats
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayerStats:
    def test_returns_live_stats(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch(
                "routes.players.get_cached_live_boxscore",
                return_value=make_live_boxscore(),
            ),
        ):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")

        assert r.status_code == 200
        players = r.json()["players"]
        assert len(players) == 1
        assert players[0]["points"] == 28
        assert players[0]["team"] == "LAL"

    def test_invalid_id_returns_empty(self, client):
        r = client.get("/api/players/stats?ids=not_a_number")
        assert r.json()["players"] == []

    def test_player_not_in_game_returns_empty(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch("routes.players.get_cached_scoreboard", return_value=[]),
        ):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.json()["players"] == []

    def test_rejects_too_many_ids(self, client):
        ids = ",".join(str(i) for i in range(26))
        r = client.get(f"/api/players/stats?ids={ids}")
        assert r.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# /api/games/{game_id}/players
# ─────────────────────────────────────────────────────────────────────────────


class TestGamePlayers:
    def test_returns_two_teams(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 200
        assert len(r.json()["teams"]) == 2

    def test_player_stats_present(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ):
            r = client.get(f"/api/games/{GAME_ID}/players")
        lal = next(t for t in r.json()["teams"] if t["tricode"] == "LAL")
        assert lal["players"][0]["points"] == 28

    def test_player_data_shape(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ):
            r = client.get(f"/api/games/{GAME_ID}/players")
        p = r.json()["teams"][0]["players"][0]
        for key in (
            "name",
            "minutes",
            "points",
            "rebounds",
            "assists",
            "fg",
            "threePt",
            "ft",
        ):
            assert key in p

    def test_rejects_invalid_game_id(self, client):
        r = client.get("/api/games/INVALID/players")
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/{id}/last-n-games
# ─────────────────────────────────────────────────────────────────────────────


class TestLastNGames:
    def _gamelog(self):
        m = MagicMock()
        m.player_game_log.get_dict.return_value = {
            "data": [[None, None, GAME_ID, "2025-02-27", "LAL vs BOS"]]
        }
        return m

    def _trad_boxscore(self, person_id=PLAYER_ID):
        m = MagicMock()
        m.player_stats.get_dict.return_value = {
            "data": [make_player_stats_row(person_id)]
        }
        return m

    def test_returns_game_log(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.playergamelog.PlayerGameLog",
                return_value=self._gamelog(),
            ),
            patch(
                "routes.players.get_cached_boxscore_v3",
                return_value=self._trad_boxscore(),
            ),
        ):
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
        assert (
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=99").status_code == 422
        )

    def test_dnp_game_flagged(self, client):
        empty_bs = MagicMock()
        empty_bs.player_stats.get_dict.return_value = {"data": []}
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.playergamelog.PlayerGameLog",
                return_value=self._gamelog(),
            ),
            patch(
                "routes.players.get_cached_boxscore_v3",
                return_value=empty_bs,
            ),
        ):
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
        with patch(
            "routes.players.playercareerstats.PlayerCareerStats",
            return_value=self._mock_career(),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 200
        body = r.json()
        assert body["points"] == 28.0
        assert body["rebounds"] == 8.0
        assert body["gp"] == 60

    def test_response_shape(self, client):
        with patch(
            "routes.players.playercareerstats.PlayerCareerStats",
            return_value=self._mock_career(),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        for key in (
            "season",
            "gp",
            "points",
            "rebounds",
            "assists",
            "fgPct",
            "fg3Pct",
            "ftPct",
        ):
            assert key in r.json()

    def test_no_data_returns_404(self, client):
        with patch(
            "routes.players.playercareerstats.PlayerCareerStats",
            return_value=self._mock_career(rows=[]),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# /api/trades
# ─────────────────────────────────────────────────────────────────────────────


class TestTrades:
    def _resp(self, rows):
        m = MagicMock()
        m.raise_for_status.return_value = None
        m.json.return_value = {"NBA_Player_Movement": {"rows": rows}}
        return m

    def _row(self, **kw):
        row = {
            "Transaction_Type": "Signing",
            "TRANSACTION_DATE": "2026-02-01T00:00:00",
            "TRANSACTION_DESCRIPTION": "Brooklyn Nets signed LeBron James to a 10-Day Contract.",
            "TEAM_ID": 1610612751.0,  # BKN
            "TEAM_SLUG": "nets",
            "PLAYER_ID": float(PLAYER_ID),
            "PLAYER_SLUG": "lebron-james",
            "Additional_Sort": 0.0,
            "GroupSort": "Signing 999",
        }
        row.update(kw)
        return row

    def test_returns_200(self, client):
        with (
            patch("routes.trades._session.get", return_value=self._resp([])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.status_code == 200

    def test_response_shape(self, client):
        with (
            patch("routes.trades._session.get", return_value=self._resp([])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        body = r.json()
        assert "transactions" in body
        assert "total" in body

    def test_team_name_resolved(self, client):
        with (
            patch("routes.trades._session.get", return_value=self._resp([self._row()])),
            patch(
                "routes.trades.load_players_dict",
                return_value={PLAYER_ID: [PLAYER_ID, "LeBron James", TEAM_ID_LAL]},
            ),
        ):
            r = client.get("/api/trades")
        t = r.json()["transactions"][0]
        assert t["teamName"] == "Brooklyn Nets"
        assert t["teamTricode"] == "BKN"

    def test_player_name_resolved_from_dict(self, client):
        with (
            patch("routes.trades._session.get", return_value=self._resp([self._row()])),
            patch(
                "routes.trades.load_players_dict",
                return_value={PLAYER_ID: [PLAYER_ID, "LeBron James", TEAM_ID_LAL]},
            ),
        ):
            r = client.get("/api/trades")
        assert r.json()["transactions"][0]["playerName"] == "LeBron James"

    def test_player_name_falls_back_to_slug(self, client):
        row = self._row(PLAYER_ID=9999999.0, PLAYER_SLUG="grant-nelson")
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.json()["transactions"][0]["playerName"] == "Grant Nelson"

    def test_sorted_by_date_descending(self, client):
        rows = [
            self._row(TRANSACTION_DATE="2026-01-10T00:00:00"),
            self._row(TRANSACTION_DATE="2026-01-20T00:00:00"),
            self._row(TRANSACTION_DATE="2026-01-05T00:00:00"),
        ]
        with (
            patch("routes.trades._session.get", return_value=self._resp(rows)),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        dates = [t["date"] for t in r.json()["transactions"]]
        assert dates == sorted(dates, reverse=True)

    def test_description_included(self, client):
        row = self._row(
            TRANSACTION_DESCRIPTION="Brooklyn Nets signed LeBron James to a 10-Day Contract."
        )
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert (
            r.json()["transactions"][0]["description"]
            == "Brooklyn Nets signed LeBron James to a 10-Day Contract."
        )

    def test_total_matches_row_count(self, client):
        rows = [self._row() for _ in range(5)]
        with (
            patch("routes.trades._session.get", return_value=self._resp(rows)),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.json()["total"] == 5

    def test_cached_on_second_call(self, client):
        with (
            patch(
                "routes.trades._session.get", return_value=self._resp([])
            ) as mock_req,
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            client.get("/api/trades")
            client.get("/api/trades")
        mock_req.assert_called_once()

    def test_503_on_request_error(self, client):
        with (
            patch(
                "routes.trades._session.get",
                side_effect=requests.RequestException("timeout"),
            ),
            patch("routes.trades.load_players_dict", return_value={}),
            patch("routes.trades.log_exceptions"),
        ):
            r = client.get("/api/trades")
        assert r.status_code == 503

    def test_unknown_team_id_returns_unknown(self, client):
        row = self._row(TEAM_ID=9999999.0)
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        t = r.json()["transactions"][0]
        assert t["teamName"] == "Unknown Team"
        assert t["teamTricode"] == ""

    def test_type_field_preserved(self, client):
        row = self._row(Transaction_Type="Trade")
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.json()["transactions"][0]["type"] == "Trade"

    def test_date_normalised_to_yyyy_mm_dd(self, client):
        row = self._row(TRANSACTION_DATE="2026-02-15T00:00:00")
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.json()["transactions"][0]["date"] == "2026-02-15"

    def test_player_name_falls_back_to_unknown_when_slug_empty(self, client):
        row = self._row(PLAYER_ID=9999999.0, PLAYER_SLUG="")
        with (
            patch("routes.trades._session.get", return_value=self._resp([row])),
            patch("routes.trades.load_players_dict", return_value={}),
        ):
            r = client.get("/api/trades")
        assert r.json()["transactions"][0]["playerName"] == "Unknown Player"
