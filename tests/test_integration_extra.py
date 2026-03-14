"""Additional integration tests to increase coverage of scores.py and players.py."""

from unittest.mock import MagicMock, patch

import pytest
from conftest import (
    CAREER_HEADERS,
    FAKE_PLAYERS,
    GAME_ID,
    PLAYER_ID,
    TEAM_ID_BOS,
    TEAM_ID_LAL,
    make_live_boxscore,
    make_live_game,
    make_live_player_stats,
    make_standings_row,
)
from fastapi.testclient import TestClient
from helpers.common import cache
from main import app


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
        standings_mock.return_value.get_dict.return_value = {
            "resultSets": [{"rowSet": rows}]
        }
        with patch("routes.scores.leaguestandings.LeagueStandings", standings_mock):
            client.get("/api/standings")
            client.get("/api/standings")
        standings_mock.assert_called_once()

    def test_last_n_games_served_from_cache(self, client):
        gamelog = MagicMock()
        gamelog.player_game_log.get_dict.return_value = {"data": []}
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.playergamelog.PlayerGameLog",
                return_value=gamelog,
            ) as mock,
        ):
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        mock.assert_called_once()

    def test_season_avg_served_from_cache(self, client):
        h = {k: i for i, k in enumerate(CAREER_HEADERS)}
        row = [None] * len(CAREER_HEADERS)
        row[h["SEASON_ID"]] = "2024-25"
        row[h["GP"]] = 60
        for k in (
            "MIN",
            "PTS",
            "REB",
            "AST",
            "STL",
            "BLK",
            "TOV",
            "PF",
            "FGM",
            "FGA",
            "FG3M",
            "FG3A",
            "FTM",
            "FTA",
        ):
            row[h[k]] = 0.0
        for k in ("FG_PCT", "FG3_PCT", "FT_PCT"):
            row[h[k]] = 0.0
        career = MagicMock()
        career.season_totals_regular_season.get_dict.return_value = {
            "headers": CAREER_HEADERS,
            "data": [row],
        }
        with patch(
            "routes.players.playercareerstats.PlayerCareerStats", return_value=career
        ) as mock:
            client.get(f"/api/players/{PLAYER_ID}/season-avg")
            client.get(f"/api/players/{PLAYER_ID}/season-avg")
        mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# /api/players/stats – advanced fields (double-double, triple-double, fg/ft%)
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayerStatsAdvancedFields:
    def test_player_stats_shape_includes_advanced_fields(self, client):
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
        p = r.json()["players"][0]
        for key in (
            "id",
            "name",
            "team",
            "points",
            "rebounds",
            "assists",
            "fg",
            "fgPct",
            "ft",
            "ftPct",
            "isDoubleDouble",
            "isTripleDouble",
        ):
            assert key in p

    def test_double_double_flagged(self, client):
        stats = make_live_player_stats(points=20, reboundsTotal=10)
        player = {
            "personId": PLAYER_ID,
            "name": "LeBron James",
            "status": "ACTIVE",
            "statistics": stats,
        }
        bs = {
            "game": {
                "gameStatusText": "Final",
                "homeTeam": {
                    "teamCity": "LA",
                    "teamName": "Lakers",
                    "teamTricode": "LAL",
                    "teamId": TEAM_ID_LAL,
                    "score": 110,
                    "players": [player],
                },
                "awayTeam": {
                    "teamCity": "BOS",
                    "teamName": "Celtics",
                    "teamTricode": "BOS",
                    "teamId": TEAM_ID_BOS,
                    "score": 100,
                    "players": [],
                },
            }
        }
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.players.get_cached_live_boxscore", return_value=bs),
        ):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.json()["players"][0]["isDoubleDouble"] is True
        assert r.json()["players"][0]["isTripleDouble"] is False

    def test_triple_double_flagged(self, client):
        stats = make_live_player_stats(points=20, reboundsTotal=10, assists=10)
        player = {
            "personId": PLAYER_ID,
            "name": "LeBron James",
            "status": "ACTIVE",
            "statistics": stats,
        }
        bs = {
            "game": {
                "gameStatusText": "Final",
                "homeTeam": {
                    "teamCity": "LA",
                    "teamName": "Lakers",
                    "teamTricode": "LAL",
                    "teamId": TEAM_ID_LAL,
                    "score": 110,
                    "players": [player],
                },
                "awayTeam": {
                    "teamCity": "BOS",
                    "teamName": "Celtics",
                    "teamTricode": "BOS",
                    "teamId": TEAM_ID_BOS,
                    "score": 100,
                    "players": [],
                },
            }
        }
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.players.get_cached_live_boxscore", return_value=bs),
        ):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.json()["players"][0]["isTripleDouble"] is True


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
            make_standings_row(1, "Boston", "Celtics", "East", 50, 20),
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
        for key in (
            "rank",
            "name",
            "wins",
            "losses",
            "gamesRemaining",
            "projectedWins",
            "projectedLosses",
            "status",
        ):
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
            make_standings_row(3, "Philadelphia", "76ers", "East", 30, 40),
            make_standings_row(1, "Boston", "Celtics", "East", 50, 20),
            make_standings_row(2, "Milwaukee", "Bucks", "East", 42, 28),
        ]
        with patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)):
            r = client.get("/api/playoffs")
        ranks = [t["rank"] for t in r.json()["east"]]
        assert ranks == sorted(ranks)


# ─────────────────────────────────────────────────────────────────────────────
# /api/doubledoubles
# ─────────────────────────────────────────────────────────────────────────────


class TestDoubleDoubles:
    def _bs(self, players_home, players_away):
        return {
            "game": {
                "homeTeam": {"teamTricode": "LAL", "players": players_home},
                "awayTeam": {"teamTricode": "BOS", "players": players_away},
            }
        }

    def _player(self, name, pts, reb, ast, stl=0, blk=0):
        return {
            "status": "ACTIVE",
            "name": name,
            "statistics": {
                "points": pts,
                "reboundsTotal": reb,
                "assists": ast,
                "steals": stl,
                "blocks": blk,
            },
        }

    def _patch_sb_today(self):
        """Patch scoreboard_date to return today so days_offset=0 uses live scoreboard."""
        from datetime import date

        return patch("routes.scores.scoreboard_date", return_value=date.today())

    def test_returns_200(self, client):
        with (
            self._patch_sb_today(),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
        ):
            r = client.get("/api/doubledoubles")
        assert r.status_code == 200

    def test_response_shape(self, client):
        with (
            self._patch_sb_today(),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
        ):
            r = client.get("/api/doubledoubles")
        for key in ("doubleDoubles", "tripleDoubles", "date"):
            assert key in r.json()

    def test_no_games_returns_empty(self, client):
        with (
            self._patch_sb_today(),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
        ):
            r = client.get("/api/doubledoubles")
        assert r.json()["doubleDoubles"] == []
        assert r.json()["tripleDoubles"] == []

    def test_double_double_detected(self, client):
        bs_dict = self._bs(
            [self._player("LeBron James", pts=20, reb=10, ast=5)],
            [],
        )
        with (
            self._patch_sb_today(),
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.scores.get_cached_live_boxscore", return_value=bs_dict),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert len(r.json()["doubleDoubles"]) == 1
        assert r.json()["doubleDoubles"][0]["name"] == "LeBron James"

    def test_triple_double_detected(self, client):
        bs_dict = self._bs(
            [self._player("LeBron James", pts=10, reb=10, ast=10)],
            [],
        )
        with (
            self._patch_sb_today(),
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.scores.get_cached_live_boxscore", return_value=bs_dict),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert len(r.json()["tripleDoubles"]) == 1
        assert r.json()["doubleDoubles"] == []

    def test_historical_offset_uses_games_list(self, client):
        with patch("routes.scores.get_games_list", return_value=[]) as mock:
            r = client.get("/api/doubledoubles?days_offset=1")
        assert r.status_code == 200
        mock.assert_called_once_with(1)

    def test_morning_cet_uses_games_list(self, client):
        """Before 13:00 CET, days_offset=0 falls back to games_list with ET offset."""
        from datetime import date, timedelta

        yesterday = date.today() - timedelta(days=1)
        with (
            patch("routes.scores.scoreboard_date", return_value=yesterday),
            patch("routes.scores.get_games_list", return_value=[]) as mock,
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        mock.assert_called_once()

    def test_boxscore_fetch_error_skipped(self, client):
        """Boxscore fetch errors are logged and skipped gracefully."""
        with (
            self._patch_sb_today(),
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch(
                "routes.scores.get_cached_live_boxscore",
                side_effect=Exception("timeout"),
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        assert r.json()["doubleDoubles"] == []

    def test_empty_boxscore_skipped(self, client):
        """Empty boxscore dict is skipped without error."""
        with (
            self._patch_sb_today(),
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.scores.get_cached_live_boxscore", return_value={}),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        assert r.json()["doubleDoubles"] == []

    def test_live_offset_uses_scoreboard(self, client):
        with (
            self._patch_sb_today(),
            patch("routes.scores.get_cached_scoreboard", return_value=[]) as mock,
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        mock.assert_called_once()

    def test_offset_too_large_rejected(self, client):
        assert client.get("/api/doubledoubles?days_offset=99").status_code == 422

    def test_player_below_threshold_excluded(self, client):
        bs_dict = self._bs(
            [self._player("Bench Guy", pts=5, reb=4, ast=3)],
            [],
        )
        with (
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.scores.get_cached_live_boxscore", return_value=bs_dict),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.json()["doubleDoubles"] == []
        assert r.json()["tripleDoubles"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Error handler branches – players.py
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayerErrorHandlers:
    def test_search_500_on_unexpected_error(self, client):
        with (
            patch(
                "routes.players.load_players_file", side_effect=OSError("disk error")
            ),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get("/api/players/search?q=LeBron")
        assert r.status_code == 500

    def test_game_players_500_on_boxscore_error(self, client):
        with (
            patch(
                "routes.players.get_cached_live_boxscore",
                side_effect=Exception("nba down"),
            ),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 500

    def test_last_n_games_500_on_unexpected_error(self, client):
        with (
            patch("routes.players.load_players_dict", side_effect=Exception("boom")),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.status_code == 500

    def test_last_n_games_503_when_feeds_unavailable(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={PLAYER_ID: [PLAYER_ID, "LeBron James", TEAM_ID_LAL]},
            ),
            patch(
                "routes.players.playergamelog.PlayerGameLog",
                side_effect=Exception("player feed down"),
            ),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.status_code == 503

    def test_season_avg_500_on_unexpected_error(self, client):
        with (
            patch(
                "routes.players.playercareerstats.PlayerCareerStats",
                side_effect=Exception("boom"),
            ),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get(f"/api/players/{PLAYER_ID}/season-avg")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# /api/season/doubles
# ─────────────────────────────────────────────────────────────────────────────

DOUBLES_HEADERS = [
    "PLAYER_ID",
    "PLAYER_NAME",
    "TEAM_ID",
    "TEAM_ABBREVIATION",
    "DD2",
    "TD3",
]


def _make_doubles_row(pid, name, team, dd2, td3):
    return [pid, name, 0, team, dd2, td3]


def _mock_league_dash(rows):
    m = MagicMock()
    m.return_value.get_dict.return_value = {
        "resultSets": [{"headers": DOUBLES_HEADERS, "rowSet": rows}]
    }
    return m


GAMELOG_HEADERS = [
    "GAME_DATE",
    "MATCHUP",
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
]


def _make_gamelog_row(date, matchup, pts, reb, ast, stl=0, blk=0):
    return [date, matchup, pts, reb, ast, stl, blk]


def _mock_gamelog(rows):
    m = MagicMock()
    m.return_value.get_dict.return_value = {
        "resultSets": [{"headers": GAMELOG_HEADERS, "rowSet": rows}]
    }
    return m


class TestSeasonDoubles:
    def test_returns_200(self, client):
        rows = [_make_doubles_row(1, "Player A", "LAL", 10, 0)]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        assert r.status_code == 200

    def test_response_shape(self, client):
        rows = [_make_doubles_row(1, "Player A", "LAL", 5, 2)]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        data = r.json()
        assert "doubleDoubles" in data
        assert "tripleDoubles" in data

    def test_sorted_descending(self, client):
        rows = [
            _make_doubles_row(1, "A", "LAL", 5, 0),
            _make_doubles_row(2, "B", "BOS", 15, 0),
            _make_doubles_row(3, "C", "GSW", 10, 0),
        ]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        counts = [p["count"] for p in r.json()["doubleDoubles"]]
        assert counts == sorted(counts, reverse=True)

    def test_max_10_results(self, client):
        rows = [_make_doubles_row(i, f"P{i}", "LAL", 20 - i, 0) for i in range(15)]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        assert len(r.json()["doubleDoubles"]) <= 30

    def test_zero_excluded(self, client):
        rows = [
            _make_doubles_row(1, "A", "LAL", 5, 0),
            _make_doubles_row(2, "B", "BOS", 0, 0),
        ]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        dd_names = [p["name"] for p in r.json()["doubleDoubles"]]
        assert "B" not in dd_names
        assert len(r.json()["tripleDoubles"]) == 0

    def test_cached_on_second_call(self, client):
        rows = [_make_doubles_row(1, "A", "LAL", 5, 0)]
        mock = _mock_league_dash(rows)
        with patch("routes.season.leaguedashplayerstats.LeagueDashPlayerStats", mock):
            client.get("/api/season/doubles")
            client.get("/api/season/doubles")
        mock.assert_called_once()


class TestTripleDoubleGames:
    def test_returns_200(self, client):
        rows = [_make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10)]
        with patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.status_code == 200

    def test_filters_triple_doubles(self, client):
        rows = [
            _make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10),
            _make_gamelog_row("2025-01-02", "LAL @ CHI", 15, 5, 3),
            _make_gamelog_row("2025-01-03", "LAL vs MIA", 10, 10, 10, 10),
        ]
        with patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        games = r.json()["games"]
        assert len(games) == 2

    def test_game_shape(self, client):
        rows = [_make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10)]
        with patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        game = r.json()["games"][0]
        for key in (
            "date",
            "matchup",
            "points",
            "rebounds",
            "assists",
            "steals",
            "blocks",
        ):
            assert key in game

    def test_cached_on_second_call(self, client):
        rows = [_make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10)]
        mock = _mock_gamelog(rows)
        with patch("routes.season.playergamelog.PlayerGameLog", mock):
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        mock.assert_called_once()

    def test_empty_returns_empty_games(self, client):
        with patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog([])):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.json()["games"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers – scores.py routes (500 on exception)
# ─────────────────────────────────────────────────────────────────────────────


class TestScoresErrorHandlers:
    def _patch_sb(self):
        from contextlib import ExitStack
        from datetime import date

        stack = ExitStack()
        stack.enter_context(
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7))
        )
        return stack

    def test_scoreboard_500_on_error(self, client):
        from datetime import date

        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date", side_effect=Exception("boom")
            ),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 500

    def test_boxscores_500_on_error(self, client):
        with (
            patch(
                "routes.scores.get_games_leaders_list", side_effect=Exception("boom")
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/boxscores?days_offset=1")
        assert r.status_code == 500

    def test_leaders_500_on_error(self, client):
        with (
            patch("routes.scores.get_games_list", side_effect=Exception("boom")),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 500

    def test_standings_500_on_error(self, client):
        with (
            patch(
                "routes.scores.leaguestandings.LeagueStandings",
                side_effect=Exception("boom"),
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/standings")
        assert r.status_code == 500

    def test_playoffs_500_on_error(self, client):
        with (
            patch(
                "routes.scores.leaguestandings.LeagueStandings",
                side_effect=Exception("boom"),
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 500

    def test_doubledoubles_500_on_error(self, client):
        from datetime import date

        with (
            patch("routes.scores.scoreboard_date", return_value=date.today()),
            patch("routes.scores.get_cached_scoreboard", side_effect=Exception("boom")),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# Cache hits that aren't yet tested
# ─────────────────────────────────────────────────────────────────────────────


class TestMoreCacheHits:
    def test_doubledoubles_cached(self, client):
        from datetime import date

        with (
            patch("routes.scores.scoreboard_date", return_value=date.today()),
            patch("routes.scores.get_cached_scoreboard", return_value=[]) as mock,
        ):
            client.get("/api/doubledoubles?days_offset=0")
            client.get("/api/doubledoubles?days_offset=0")
        mock.assert_called_once()

    def test_player_stats_cached(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch("routes.players.get_cached_scoreboard", return_value=[]) as mock,
        ):
            client.get(f"/api/players/stats?ids={PLAYER_ID}")
            client.get(f"/api/players/stats?ids={PLAYER_ID}")
        mock.assert_called_once()

    def test_game_players_cached(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ) as mock:
            client.get(f"/api/games/{GAME_ID}/players")
            client.get(f"/api/games/{GAME_ID}/players")
        mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Empty boxscore results in leaders/doubledoubles
# ─────────────────────────────────────────────────────────────────────────────


class TestEmptyBoxscoreResults:
    def test_leaders_skips_empty_boxscore(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch("routes.scores.get_cached_live_boxscore", return_value={}),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}

    def test_doubledoubles_skips_empty_boxscore(self, client):
        with (
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch("routes.scores.get_cached_live_boxscore", return_value={}),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200
        assert r.json()["doubleDoubles"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Inner exception handlers (fetch fails but endpoint continues)
# ─────────────────────────────────────────────────────────────────────────────


class TestInnerExceptionHandlers:
    def test_leaders_survives_boxscore_exception(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch(
                "routes.scores.get_cached_live_boxscore", side_effect=Exception("boom")
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200

    def test_doubledoubles_survives_boxscore_exception(self, client):
        with (
            patch(
                "routes.scores.get_cached_scoreboard", return_value=[make_live_game()]
            ),
            patch(
                "routes.scores.get_cached_live_boxscore", side_effect=Exception("boom")
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/doubledoubles?days_offset=0")
        assert r.status_code == 200

    def test_dates_survives_games_list_exception(self, client):
        with (
            patch("routes.scores.get_games_list", side_effect=Exception("boom")),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/dates")
        assert r.status_code == 200
        # All hasGames should be False when exception occurs
        assert not any(r.json()["hasGames"])


# ─────────────────────────────────────────────────────────────────────────────
# Season and trades error handlers
# ─────────────────────────────────────────────────────────────────────────────


class TestSeasonErrorHandlers:
    def test_season_highs_500_on_error(self, client):
        with (
            patch(
                "routes.season.leaguegamelog.LeagueGameLog",
                side_effect=Exception("boom"),
            ),
            patch("routes.season.log_exceptions"),
        ):
            r = client.get("/api/season/highs")
        assert r.status_code == 500

    def test_season_doubles_500_on_error(self, client):
        with (
            patch(
                "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
                side_effect=Exception("boom"),
            ),
            patch("routes.season.log_exceptions"),
        ):
            r = client.get("/api/season/doubles")
        assert r.status_code == 500

    def test_triple_double_games_500_on_error(self, client):
        with (
            patch(
                "routes.season.playergamelog.PlayerGameLog",
                side_effect=Exception("boom"),
            ),
            patch("routes.season.log_exceptions"),
        ):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.status_code == 500

    def test_trades_500_on_unexpected_error(self, client):
        with (
            patch("routes.trades.requests.get", side_effect=TypeError("unexpected")),
            patch("routes.trades.load_players_dict", return_value={}),
            patch("routes.trades.log_exceptions"),
        ):
            r = client.get("/api/trades")
        assert r.status_code == 500

    def test_injuries_500_on_json_error(self, client):
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            tmp = f.name
        try:
            with (
                patch("routes.injuries.CBS_INJURIES_FILE", tmp),
                patch("routes.injuries.log_exceptions"),
            ):
                r = client.get("/api/injuries")
            assert r.status_code == 500
        finally:
            os.unlink(tmp)
