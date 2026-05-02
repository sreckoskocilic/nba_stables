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

    def test_cache_hit_skips_api_call(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        with patch(
            "routes.scores.leaguestandings.LeagueStandings", self._mock(rows)
        ) as m:
            client.get("/api/playoffs")
            client.get("/api/playoffs")
        m.assert_called_once()

    def _make_conf_rows(self, conf, id_base):
        return [
            make_standings_row(
                rank,
                f"City{rank}",
                f"Team{rank}",
                conf,
                50 - rank,
                10 + rank,
                team_id=id_base + rank,
            )
            for rank in range(1, 11)
        ]

    def _lgf_mock(self, rowset):
        m = MagicMock()
        m.return_value.get_dict.return_value = {
            "resultSets": [{"headers": ["GAME_ID", "TEAM_ID", "PTS"], "rowSet": rowset}]
        }
        return m

    def test_playin_game_scores_populated(self, client):
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        # G1 East: team1007 beats team1008
        lgf_rows = [["G1E", 1007, 110], ["G1E", 1008, 105]]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        playin = r.json()["playinActual"]
        assert playin["east"].get("seed7TeamId") == 1007
        assert playin["east"].get("g1LoserTeamId") == 1008
        assert len(playin["east"]["gameScores"]) == 1

    def test_playin_rank_correction_seed7(self, client):
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        lgf_rows = [["G1E", 1007, 110], ["G1E", 1008, 105]]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        east = r.json()["east"]
        team7 = next(t for t in east if t["teamId"] == 1007)
        assert team7["rank"] == 7

    def test_playin_rank_correction_seed8(self, client):
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        # G1: 1007 beats 1008; G2: 1009 beats 1010; G3: 1009 beats 1008
        lgf_rows = [
            ["G1E", 1007, 110],
            ["G1E", 1008, 105],
            ["G2E", 1009, 100],
            ["G2E", 1010, 95],
            ["G3E", 1009, 102],
            ["G3E", 1008, 98],
        ]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.json()["playinActual"]["east"]["g3WinnerTeamId"] == 1009

    def test_playin_process_conf_fewer_than_4_teams(self, client):
        # Only 8 teams per conf → play-in slice has 2 teams → process_conf returns early
        rows = [
            make_standings_row(
                rank,
                f"City{rank}",
                f"Team{rank}",
                "East",
                50 - rank,
                10 + rank,
                team_id=1000 + rank,
            )
            for rank in range(1, 9)
        ] + [
            make_standings_row(
                rank,
                f"City{rank}",
                f"Team{rank}",
                "West",
                50 - rank,
                10 + rank,
                team_id=2000 + rank,
            )
            for rank in range(1, 9)
        ]
        lgf_rows = [["G1E", 1007, 110], ["G1E", 1008, 105]]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        assert r.json()["playinActual"]["east"]["gameScores"] == {}

    def test_playin_data_exception_returns_empty(self, client):
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", side_effect=Exception("api down")),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        playin = r.json()["playinActual"]
        assert playin["east"]["gameScores"] == {}
        assert playin["west"]["gameScores"] == {}

    def _lgf_playoffs_mock(self, rowset):
        m = MagicMock()
        m.return_value.get_dict.return_value = {
            "resultSets": [
                {"headers": ["GAME_ID", "TEAM_ID", "WL", "PTS"], "rowSet": rowset}
            ]
        }
        return m

    def test_series_results_populated(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        lgf_rows = [
            ["PG01", 100, "W", 110],
            ["PG01", 200, "L", 100],
            ["PG02", 100, "W", 105],
            ["PG02", 200, "L", 98],
        ]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_playoffs_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        series = r.json()["seriesResults"]
        assert series["100_200"]["100"] == 2
        assert series["100_200"]["200"] == 0

    def test_series_results_skips_incomplete_game(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        # Game PG01 only has one team row → skipped (len(teams) != 2)
        lgf_rows = [["PG01", 100, "W", 110]]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_playoffs_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.json()["seriesResults"] == {}

    def test_series_results_empty_on_error(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", side_effect=Exception("api down")),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        assert r.json()["seriesResults"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Error handler branches – players.py
# ─────────────────────────────────────────────────────────────────────────────


class TestPlayerErrorHandlers:
    def test_search_500_on_unexpected_error(self, client):
        with (
            patch(
                "routes.players.load_players_with_lower",
                side_effect=OSError("disk error"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/players/search?q=LeBron")
        assert r.status_code == 500

    def test_game_players_500_on_boxscore_error(self, client):
        with (
            patch(
                "routes.players.get_cached_live_boxscore",
                side_effect=Exception("nba down"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 500

    def test_last_n_games_500_on_unexpected_error(self, client):
        with (
            patch("routes.players.load_players_dict", side_effect=Exception("boom")),
            patch("helpers.decorators.log_exceptions"),
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
            patch("helpers.decorators.log_exceptions"),
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


_TD_FAKE_PLAYER = {PLAYER_ID: [PLAYER_ID, "LeBron James", 1]}


class TestTripleDoubleGames:
    def test_returns_200(self, client):
        rows = [_make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10)]
        with (
            patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.status_code == 200

    def test_filters_triple_doubles(self, client):
        rows = [
            _make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10),
            _make_gamelog_row("2025-01-02", "LAL @ CHI", 15, 5, 3),
            _make_gamelog_row("2025-01-03", "LAL vs MIA", 10, 10, 10, 10),
        ]
        with (
            patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        games = r.json()["games"]
        assert len(games) == 2

    def test_game_shape(self, client):
        rows = [_make_gamelog_row("2025-01-01", "LAL vs BOS", 20, 10, 10)]
        with (
            patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog(rows)),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
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
        with (
            patch("routes.season.playergamelog.PlayerGameLog", mock),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        mock.assert_called_once()

    def test_empty_returns_empty_games(self, client):
        with (
            patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog([])),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
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
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 500

    def test_boxscores_timeout_returns_empty(self, client):
        with (
            patch(
                "routes.scores.get_games_leaders_list",
                return_value={"g1": [], "g2": []},
            ),
            patch("routes.scores.executor") as mock_exec,
        ):
            mock_exec.map.side_effect = TimeoutError("timed out")
            r = client.get("/api/boxscores?days_offset=1")
        assert r.status_code == 200
        assert r.json()["boxscores"] == []

    def test_boxscores_500_on_error(self, client):
        with (
            patch(
                "routes.scores.get_games_leaders_list", side_effect=Exception("boom")
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/boxscores?days_offset=1")
        assert r.status_code == 500

    def test_leaders_500_on_error(self, client):
        with (
            patch("routes.scores.get_games_list", side_effect=Exception("boom")),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 500

    def test_standings_500_on_error(self, client):
        with (
            patch(
                "routes.scores.leaguestandings.LeagueStandings",
                side_effect=Exception("boom"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/standings")
        assert r.status_code == 500

    def test_playoffs_500_on_error(self, client):
        with (
            patch(
                "routes.scores.leaguestandings.LeagueStandings",
                side_effect=Exception("boom"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 500


# ─────────────────────────────────────────────────────────────────────────────
# Cache hits that aren't yet tested
# ─────────────────────────────────────────────────────────────────────────────


class TestMoreCacheHits:
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
# Empty boxscore results in leaders
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

    def test_leaders_survives_malformed_boxscore(self, client):
        """A boxscore missing expected keys must not crash the endpoint."""
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch(
                "routes.scores.get_cached_live_boxscore",
                return_value={"game": {"homeTeam": {}}},
            ),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}

    def test_dates_survives_games_list_exception(self, client):
        with (
            patch("routes.scores.get_games_list", side_effect=Exception("boom")),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/dates")
        assert r.status_code == 200
        # All hasGames should be False when exception occurs
        assert not any(r.json()["hasGames"])

    def test_dates_500_on_sync_error(self, client):
        with (
            patch("routes.scores.get_display_date", side_effect=RuntimeError("boom")),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/dates")
        assert r.status_code == 500


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
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/season/highs")
        assert r.status_code == 500

    def test_season_doubles_500_on_error(self, client):
        with (
            patch(
                "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
                side_effect=Exception("boom"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/season/doubles")
        assert r.status_code == 500

    def test_triple_double_games_500_on_error(self, client):
        with (
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
            patch(
                "routes.season.playergamelog.PlayerGameLog",
                side_effect=Exception("boom"),
            ),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.status_code == 500

    def test_trades_500_on_unexpected_error(self, client):
        with (
            patch("routes.trades.requests.get", side_effect=TypeError("unexpected")),
            patch("routes.trades.load_players_dict", return_value={}),
            patch("helpers.decorators.log_exceptions"),
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
                patch("helpers.decorators.log_exceptions"),
            ):
                r = client.get("/api/injuries")
            assert r.status_code == 500
        finally:
            os.unlink(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# executor.map TimeoutError and scoreboard-fallback paths
# ─────────────────────────────────────────────────────────────────────────────


class TestExecutorTimeouts:
    def test_leaders_boxscore_timeout_returns_empty(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=["0022400001"]),
            patch("routes.scores.executor") as mock_exec,
            patch("routes.scores.log_exceptions"),
        ):
            mock_exec.map.side_effect = TimeoutError("timed out")
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}

    def test_player_tracker_scoreboard_error_returns_empty(self, client):
        with (
            patch(
                "routes.players.get_cached_scoreboard", side_effect=Exception("boom")
            ),
            patch("routes.players.log_exceptions"),
        ):
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.status_code == 200
        assert r.json()["players"] == []

    def test_player_tracker_timeout_returns_empty(self, client):
        with (
            patch(
                "routes.players.get_cached_scoreboard",
                return_value=[{"gameId": "0022400001"}],
            ),
            patch("routes.players.executor") as mock_exec,
            patch("routes.players.log_exceptions"),
        ):
            mock_exec.map.side_effect = TimeoutError("timed out")
            r = client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert r.status_code == 200
        assert r.json()["players"] == []

    def test_last_n_games_timeout_returns_empty_games(self, client):
        cache.set(
            f"player_games_raw_{PLAYER_ID}",
            [["LAL @ BOS", GAME_ID, "2026-03-01"]],
            60,
        )
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={PLAYER_ID: [PLAYER_ID, "Test Player", TEAM_ID_LAL]},
            ),
            patch("routes.players.executor") as mock_exec,
            patch("routes.players.log_exceptions"),
        ):
            mock_exec.map.side_effect = TimeoutError("timed out")
            r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert r.status_code == 200
        assert r.json()["games"] == []

    def test_playoffs_playin_timeout_returns_empty(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        standings_mock = MagicMock()
        standings_mock.return_value.get_dict.return_value = {
            "resultSets": [{"rowSet": rows}]
        }
        playin_future = MagicMock()
        playin_future.result.side_effect = TimeoutError("playin timed out")
        series_future = MagicMock()
        series_future.result.return_value = {}
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", standings_mock),
            patch("routes.scores.executor") as mock_exec,
            patch("routes.scores.log_exceptions"),
        ):
            mock_exec.submit.side_effect = [playin_future, series_future]
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        assert r.json()["playinActual"] == {
            "east": {"gameScores": {}},
            "west": {"gameScores": {}},
        }

    def test_playoffs_series_timeout_returns_empty(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        standings_mock = MagicMock()
        standings_mock.return_value.get_dict.return_value = {
            "resultSets": [{"rowSet": rows}]
        }
        playin_future = MagicMock()
        playin_future.result.return_value = {
            "east": {"gameScores": {}},
            "west": {"gameScores": {}},
        }
        series_future = MagicMock()
        series_future.result.side_effect = TimeoutError("series timed out")
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", standings_mock),
            patch("routes.scores.executor") as mock_exec,
            patch("routes.scores.log_exceptions"),
        ):
            mock_exec.submit.side_effect = [playin_future, series_future]
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        assert r.json()["seriesResults"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Scoreboard playoff series badge
# ─────────────────────────────────────────────────────────────────────────────


class TestScoreboardSeries:
    def _lgf_mock(self, rowset):
        m = MagicMock()
        m.return_value.get_dict.return_value = {
            "resultSets": [
                {"headers": ["GAME_ID", "TEAM_ID", "WL", "PTS"], "rowSet": rowset}
            ]
        }
        return m

    def _patch_sb(self, games):
        from contextlib import ExitStack
        from datetime import date

        from conftest import make_scoreboard_v3

        stack = ExitStack()
        stack.enter_context(
            patch(
                "routes.scores.get_scoreboard_v3_by_date",
                return_value=make_scoreboard_v3(games),
            )
        )
        stack.enter_context(
            patch("routes.scores.scoreboard_date", return_value=date(2026, 4, 25))
        )
        stack.enter_context(
            patch("routes.scores.get_cached_scoreboard", return_value=[])
        )
        return stack

    def test_attach_helper_sets_series(self):
        from routes.scores import _attach_series_to_games

        lo, hi = sorted((TEAM_ID_LAL, TEAM_ID_BOS))
        games = [
            {
                "homeTeam": {"tricode": "LAL"},
                "awayTeam": {"tricode": "BOS"},
            }
        ]
        _attach_series_to_games(
            games, {f"{lo}_{hi}": {str(TEAM_ID_LAL): 3, str(TEAM_ID_BOS): 1}}
        )
        assert games[0]["series"] == {"home": 3, "away": 1}

    def test_attach_helper_skips_unknown_pair(self):
        from routes.scores import _attach_series_to_games

        games = [{"homeTeam": {"tricode": "LAL"}, "awayTeam": {"tricode": "BOS"}}]
        _attach_series_to_games(games, {"999_998": {"999": 1, "998": 0}})
        assert "series" not in games[0]

    def test_attach_helper_skips_unknown_tricode(self):
        from routes.scores import _attach_series_to_games

        # Unknown tricode -> _TRICODE_TO_TEAM_ID lookup returns None -> continue.
        games = [{"homeTeam": {"tricode": "ZZZ"}, "awayTeam": {"tricode": "BOS"}}]
        _attach_series_to_games(games, {"1_2": {"1": 3, "2": 0}})
        assert "series" not in games[0]

    def test_attach_helper_noop_on_empty(self):
        from routes.scores import _attach_series_to_games

        games = [{"homeTeam": {"tricode": "LAL"}, "awayTeam": {"tricode": "BOS"}}]
        _attach_series_to_games(games, {})
        assert "series" not in games[0]

    def test_scoreboard_includes_series(self, client):
        # LeagueGameFinder rows: LAL beats BOS twice -> LAL leads 2-0
        lgf_rows = [
            ["PG01", TEAM_ID_LAL, "W", 110],
            ["PG01", TEAM_ID_BOS, "L", 100],
            ["PG02", TEAM_ID_LAL, "W", 105],
            ["PG02", TEAM_ID_BOS, "L", 98],
        ]
        with (
            self._patch_sb([make_live_game(gameStatusText="Final")]),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 200
        g = r.json()["games"][0]
        # home=LAL, away=BOS by make_live_game defaults
        assert g["series"] == {"home": 2, "away": 0}

    def test_scoreboard_no_series_outside_playoffs(self, client):
        # Default autouse fixture returns empty rowset -> no series data
        with self._patch_sb([make_live_game(gameStatusText="Final")]):
            r = client.get("/api/scoreboard")
        assert "series" not in r.json()["games"][0]

    def test_series_cache_reused(self):
        """_get_playoff_series_cached returns the cached value on the second call."""
        from routes.scores import _get_playoff_series_cached

        with patch(
            "routes.scores._fetch_playoff_series_data", return_value={"k": {"v": 1}}
        ) as fetch_mock:
            first = _get_playoff_series_cached("2025-26")
            second = _get_playoff_series_cached("2025-26")
        assert first == second == {"k": {"v": 1}}
        fetch_mock.assert_called_once()
