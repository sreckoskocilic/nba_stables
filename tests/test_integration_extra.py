"""Additional integration tests to increase coverage of scores.py and players.py."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from conftest import (
    CAREER_HEADERS,
    FAKE_PLAYERS,
    GAME_ID,
    PLAYER_ID,
    TEAM_ID_BOS,
    TEAM_ID_LAL,
    V3_PLAYER_STATS_HEADERS,
    make_game_logs,
    make_live_boxscore,
    make_live_game,
    make_live_player,
    make_scoreboard_v3,
    make_standings_row,
)
from helpers.common import CACHE_TTL
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


class TestCacheHits:
    def test_boxscores_served_from_cache(self, client):
        with patch("routes.scores.get_games_leaders_list", return_value={}) as mock:
            client.get("/api/boxscores?days_offset=2")
            client.get("/api/boxscores?days_offset=2")
        mock.assert_called_once()

    def test_leaders_served_from_cache(self, client):
        with patch("routes.scores.get_games_list", return_value=[]) as mock:
            client.get("/api/leaders?days_offset=2")
            client.get("/api/leaders?days_offset=2")
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
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch(
                "routes.players.playergamelogs.PlayerGameLogs",
                return_value=make_game_logs(),
            ) as mock,
        ):
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
            client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
        assert mock.call_count == 2

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


class TestPlayerStatsFields:
    def test_player_stats_shape(self, client):
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
            "minutes",
            "points",
            "fg",
            "threePointers",
            "ft",
            "rebounds",
            "assists",
            "blocks",
            "steals",
            "fouls",
        ):
            assert key in p


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
            "teamId",
        ):
            assert key in team

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

    def test_playin_skips_game_without_final_pts(self, client):
        # LeagueGameFinder leaves PTS=None until a game is finalised — the score
        # still shows, but no winner/loser may be derived from it.
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        lgf_rows = [["G1E", 1007, None], ["G1E", 1008, None]]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert r.status_code == 200
        east = r.json()["playinActual"]["east"]
        assert len(east["gameScores"]) == 1
        assert "seed7TeamId" not in east
        assert "g1LoserTeamId" not in east

    def test_playin_skips_g3_without_final_pts(self, client):
        # G3 is still tied — g3WinnerTeamId must stay unset.
        rows = self._make_conf_rows("East", 1000) + self._make_conf_rows("West", 2000)
        lgf_rows = [
            ["G1E", 1007, 110],
            ["G1E", 1008, 105],
            ["G2E", 1009, 100],
            ["G2E", 1010, 95],
            ["G3E", 1009, 88],
            ["G3E", 1008, 88],
        ]
        with (
            patch("routes.scores.leaguestandings.LeagueStandings", self._mock(rows)),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/playoffs")
        assert "g3WinnerTeamId" not in r.json()["playinActual"]["east"]

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
                {
                    "headers": [
                        "GAME_ID",
                        "TEAM_ID",
                        "WL",
                        "PTS",
                        "GAME_DATE",
                        "MATCHUP",
                    ],
                    "rowSet": rowset,
                }
            ]
        }
        return m

    def test_series_results_populated(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        lgf_rows = [
            ["PG01", 100, "W", 110, "2026-05-20", "TEA vs. TEB"],
            ["PG01", 200, "L", 100, "2026-05-20", "TEB @ TEA"],
            ["PG02", 100, "W", 105, "2026-05-22", "TEA vs. TEB"],
            ["PG02", 200, "L", 98, "2026-05-22", "TEB @ TEA"],
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
        lgf_rows = [["PG01", 100, "W", 110, "2026-05-20", "TEA vs. TEB"]]
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

    def test_finals_data_cross_conference_pair(self):
        from routes.scores import _build_finals_data

        east = [{"teamId": 1610612752, "name": "New York Knicks", "tricode": "NYK"}]
        west = [
            {"teamId": 1610612760, "name": "Oklahoma City Thunder", "tricode": "OKC"}
        ]
        pair_key = "1610612752_1610612760"
        pair_wins = {pair_key: {"1610612752": 2, "1610612760": 1}}
        pair_games = {
            pair_key: [
                {
                    "gameId": "FIN01",
                    "date": "2026-06-05",
                    "teams": {
                        1610612752: {"pts": 108, "wl": "W", "matchup": "NYK vs. OKC"},
                        1610612760: {"pts": 102, "wl": "L", "matchup": "OKC @ NYK"},
                    },
                }
            ]
        }
        result = _build_finals_data(east, west, pair_wins, pair_games)
        assert result["east"]["tricode"] == "NYK"
        assert result["west"]["tricode"] == "OKC"
        assert result["seriesScore"] == {"1610612752": 2, "1610612760": 1}
        assert len(result["games"]) == 1
        g = result["games"][0]
        assert g["gameId"] == "FIN01"
        assert g["home"]["tricode"] == "NYK"
        assert g["home"]["score"] == 108
        assert g["away"]["tricode"] == "OKC"
        assert g["away"]["score"] == 102

    def test_finals_data_conference_champion_no_finals(self):
        from routes.scores import _build_finals_data

        tid = 1610612752
        east = [
            {"teamId": tid, "name": "New York Knicks", "tricode": "NYK"},
            {"teamId": 201, "name": "R1 Opp", "tricode": "R1O"},
            {"teamId": 202, "name": "SF Opp", "tricode": "SFO"},
            {"teamId": 203, "name": "CF Opp", "tricode": "CFO"},
        ]
        west = [
            {"teamId": 1610612760, "name": "Oklahoma City Thunder", "tricode": "OKC"}
        ]
        pair_wins = {
            f"{tid}_201": {str(tid): 4, "201": 2},
            f"{tid}_202": {str(tid): 4, "202": 3},
            f"{tid}_203": {str(tid): 4, "203": 1},
        }
        result = _build_finals_data(east, west, pair_wins, {})
        assert result["east"]["name"] == "New York Knicks"
        assert result["west"] is None
        assert result["games"] == []

    def test_finals_data_skips_incomplete_game(self):
        from routes.scores import _build_finals_data

        east = [{"teamId": 100, "name": "East Team", "tricode": "EST"}]
        west = [{"teamId": 200, "name": "West Team", "tricode": "WST"}]
        pair_wins = {"100_200": {"100": 1, "200": 0}}
        pair_games = {
            "100_200": [
                {
                    "gameId": "FIN01",
                    "date": "2026-06-05",
                    "teams": {100: {"pts": 108, "wl": "W", "matchup": "EST vs. WST"}},
                }
            ]
        }
        result = _build_finals_data(east, west, pair_wins, pair_games)
        assert result["games"] == []

    def test_finals_data_empty_when_no_champions(self):
        from routes.scores import _build_finals_data

        east = [{"teamId": 100, "name": "Team A", "tricode": "TMA"}]
        west = [{"teamId": 200, "name": "Team B", "tricode": "TMB"}]
        result = _build_finals_data(east, west, {}, {})
        assert result["east"] is None
        assert result["west"] is None
        assert result["games"] == []


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
            patch(
                "routes.players._game_players_from_v3",
                side_effect=Exception("v3 down"),
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
                "routes.players.playergamelogs.PlayerGameLogs",
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
    empty = MagicMock()
    empty.get_dict.return_value = {
        "resultSets": [{"headers": DOUBLES_HEADERS, "rowSet": []}]
    }
    full = MagicMock()
    full.get_dict.return_value = {
        "resultSets": [{"headers": DOUBLES_HEADERS, "rowSet": rows}]
    }
    m = MagicMock(side_effect=[full, empty])
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
    empty = MagicMock()
    empty.get_dict.return_value = {
        "resultSets": [{"headers": GAMELOG_HEADERS, "rowSet": []}]
    }
    full = MagicMock()
    full.get_dict.return_value = {
        "resultSets": [{"headers": GAMELOG_HEADERS, "rowSet": rows}]
    }
    m = MagicMock(side_effect=[full, empty])
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
        assert mock.call_count == 2


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
        assert mock.call_count == 2

    def test_empty_returns_empty_games(self, client):
        with (
            patch("routes.season.playergamelog.PlayerGameLog", _mock_gamelog([])),
            patch("routes.season.load_players_dict", return_value=_TD_FAKE_PLAYER),
        ):
            r = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert r.json()["games"] == []


class TestScoresErrorHandlers:
    def test_scoreboard_500_on_error(self, client):
        from datetime import date

        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date", side_effect=Exception("boom")
            ),
            patch("routes.scores.get_cached_scoreboard", side_effect=Exception("boom")),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
            patch("routes.scores.log_exceptions"),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 500

    def test_scoreboard_falls_back_to_live_when_v3_fails(self, client):
        from datetime import date

        live = [
            make_live_game(gameCode="20260308/BOSLAL"),
            make_live_game(gameId="0022500999", gameCode="20260307/NYKMIA"),
        ]
        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date", side_effect=Exception("boom")
            ) as v3,
            patch("routes.scores.get_cached_scoreboard", return_value=live),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 8)),
            patch("routes.scores.log_exceptions"),
        ):
            r = client.get("/api/scoreboard")
            client.get("/api/scoreboard")
        assert r.status_code == 200
        assert [g["gameId"] for g in r.json()["games"]] == [GAME_ID]
        v3.assert_called_once()

    def test_boxscores_empty_leaders_returns_empty(self, client):
        with (
            patch(
                "routes.scores.get_games_leaders_list",
                return_value={"g1": [], "g2": []},
            ),
            patch("routes.scores.fetch_single_boxscore", return_value=None),
        ):
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


class TestMoreCacheHits:
    def test_player_stats_not_cached_at_route(self, client):
        with (
            patch(
                "routes.players.load_players_dict",
                return_value={p[0]: p for p in FAKE_PLAYERS},
            ),
            patch("routes.players.get_cached_scoreboard", return_value=[]) as mock,
        ):
            client.get(f"/api/players/stats?ids={PLAYER_ID}")
            client.get(f"/api/players/stats?ids={PLAYER_ID}")
        assert mock.call_count == 2

    def test_live_game_players_not_cached_at_route(self, client):
        gid = "0022500777"
        with patch(
            "routes.players.get_cached_live_boxscore",
            return_value=make_live_boxscore(gid, status="Q2 5:00"),
        ) as mock:
            client.get(f"/api/games/{gid}/players")
            client.get(f"/api/games/{gid}/players")
        assert mock.call_count == 2

    def test_game_players_cached(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ) as mock:
            client.get(f"/api/games/{GAME_ID}/players")
            client.get(f"/api/games/{GAME_ID}/players")
        mock.assert_called_once()


class TestEmptyBoxscoreResults:
    def test_leaders_skips_empty_boxscore(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[GAME_ID]),
            patch("routes.scores.get_cached_live_boxscore", return_value={}),
        ):
            r = client.get("/api/leaders?days_offset=1")
        assert r.status_code == 200
        assert r.json()["leaders"] == {}


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
        assert not any(r.json()["hasGames"])

    def test_dates_500_on_sync_error(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=[]),
            patch("routes.scores.get_display_date", side_effect=RuntimeError("boom")),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/dates")
        assert r.status_code == 500


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

    def test_trades_503_on_malformed_json(self, client):
        bad_resp = MagicMock()
        bad_resp.raise_for_status.return_value = None
        bad_resp.json.side_effect = ValueError("No JSON")
        with patch("routes.trades.with_retry", return_value=bad_resp):
            r = client.get("/api/trades")
        assert r.status_code == 503

    def test_trades_500_on_unexpected_error(self, client):
        with (
            patch("routes.trades.requests.get", side_effect=TypeError("unexpected")),
            patch("routes.trades.load_players_dict", return_value={}),
            patch("helpers.decorators.log_exceptions"),
        ):
            r = client.get("/api/trades")
        assert r.status_code == 500

    def test_injuries_500_on_json_error(self, client):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            tmp = f.name
        try:
            with (
                patch("routes.injuries.CBS_INJURIES_FILE", tmp),
                patch("helpers.decorators.log_exceptions"),
            ):
                r = client.get("/api/injuries")
            assert r.status_code == 503
        finally:
            os.unlink(tmp)


class TestExecutorTimeouts:
    def test_leaders_boxscore_failure_returns_empty(self, client):
        with (
            patch("routes.scores.get_games_list", return_value=["0022400001"]),
            patch(
                "routes.scores.get_cached_live_boxscore",
                side_effect=Exception("API error"),
            ),
            patch("routes.scores.log_exceptions"),
        ):
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


PLAYOFF_GAME_ID = "0042500101"


class TestScoreboardSeries:
    def _lgf_mock(self, rowset):
        m = MagicMock()
        m.return_value.get_dict.return_value = {
            "resultSets": [
                {
                    "headers": [
                        "GAME_ID",
                        "TEAM_ID",
                        "WL",
                        "PTS",
                        "GAME_DATE",
                        "MATCHUP",
                    ],
                    "rowSet": rowset,
                }
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
                "gameId": PLAYOFF_GAME_ID,
                "homeTeam": {"tricode": "LAL"},
                "awayTeam": {"tricode": "BOS"},
            }
        ]
        _attach_series_to_games(
            games, {f"{lo}_{hi}": {str(TEAM_ID_LAL): 3, str(TEAM_ID_BOS): 1}}
        )
        assert games[0]["series"] == {"home": 3, "away": 1}

    def test_attach_helper_skips_non_playoff_game(self):
        from routes.scores import _attach_series_to_games

        lo, hi = sorted((TEAM_ID_LAL, TEAM_ID_BOS))
        games = [
            {
                "gameId": "0012600001",
                "homeTeam": {"tricode": "LAL"},
                "awayTeam": {"tricode": "BOS"},
            }
        ]
        _attach_series_to_games(
            games, {f"{lo}_{hi}": {str(TEAM_ID_LAL): 3, str(TEAM_ID_BOS): 1}}
        )
        assert "series" not in games[0]

    def test_attach_helper_skips_unknown_pair(self):
        from routes.scores import _attach_series_to_games

        games = [
            {
                "gameId": PLAYOFF_GAME_ID,
                "homeTeam": {"tricode": "LAL"},
                "awayTeam": {"tricode": "BOS"},
            }
        ]
        _attach_series_to_games(games, {"999_998": {"999": 1, "998": 0}})
        assert "series" not in games[0]

    def test_attach_helper_skips_unknown_tricode(self):
        from routes.scores import _attach_series_to_games

        games = [
            {
                "gameId": PLAYOFF_GAME_ID,
                "homeTeam": {"tricode": "ZZZ"},
                "awayTeam": {"tricode": "BOS"},
            }
        ]
        _attach_series_to_games(games, {"1_2": {"1": 3, "2": 0}})
        assert "series" not in games[0]

    def test_attach_helper_noop_on_empty(self):
        from routes.scores import _attach_series_to_games

        games = [{"homeTeam": {"tricode": "LAL"}, "awayTeam": {"tricode": "BOS"}}]
        _attach_series_to_games(games, {})
        assert "series" not in games[0]

    def test_scoreboard_includes_series(self, client):
        lgf_rows = [
            ["PG01", TEAM_ID_LAL, "W", 110, "2026-05-20", "LAL vs. BOS"],
            ["PG01", TEAM_ID_BOS, "L", 100, "2026-05-20", "BOS @ LAL"],
            ["PG02", TEAM_ID_LAL, "W", 105, "2026-05-22", "LAL vs. BOS"],
            ["PG02", TEAM_ID_BOS, "L", 98, "2026-05-22", "BOS @ LAL"],
        ]
        with (
            self._patch_sb(
                [make_live_game(gameId=PLAYOFF_GAME_ID, gameStatusText="Final")]
            ),
            patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)),
        ):
            r = client.get("/api/scoreboard")
        assert r.status_code == 200
        g = r.json()["games"][0]
        # home=LAL, away=BOS by make_live_game defaults
        assert g["series"] == {"home": 2, "away": 0}

    def test_wnba_scoreboard_includes_series(self, client):
        # MIN is both Timberwolves and Lynx; WNBA lookup must pick the Lynx.
        nyl, min_lynx = 1611661313, 1611661324
        lgf_rows = [
            ["WG01", nyl, "W", 80, "2026-09-27", "NYL @ MIN"],
            ["WG01", min_lynx, "L", 75, "2026-09-27", "MIN vs. NYL"],
        ]
        game = make_live_game(gameId="1042600101")
        game["homeTeam"].update(teamTricode="MIN", teamId=min_lynx)
        game["awayTeam"].update(teamTricode="NYL", teamId=nyl)
        lgf = self._lgf_mock(lgf_rows)
        with (
            self._patch_sb([game]),
            patch("routes.scores.get_wnba_current_season", return_value="2026-27"),
            patch("routes.scores.LeagueGameFinder", lgf),
        ):
            r = client.get("/api/scoreboard?league=wnba")
        assert r.json()["games"][0]["series"] == {"home": 0, "away": 1}
        assert lgf.call_args.kwargs["season_nullable"] == "2026"
        assert lgf.call_args.kwargs["league_id_nullable"] == "10"

    def test_scoreboard_no_series_outside_playoffs(self, client):
        # Default autouse fixture returns empty rowset -> no series data
        with self._patch_sb([make_live_game(gameStatusText="Final")]):
            r = client.get("/api/scoreboard")
        assert "series" not in r.json()["games"][0]

    def test_series_cache_reused(self):
        """_get_playoff_series_cached returns the cached value on the second call."""
        from routes.scores import _get_playoff_series_cached

        val = ({"k": {"v": 1}}, {"k": [{"gameId": "G1"}]})
        with patch(
            "routes.scores._fetch_playoff_series_data",
            return_value=val,
        ) as fetch_mock:
            first = _get_playoff_series_cached()
            second = _get_playoff_series_cached()
        assert first == second == val
        fetch_mock.assert_called_once()

    def test_series_infers_winner_from_pts_when_wl_missing(self):
        """WL=None on a just-finished game -> winner inferred from higher PTS.

        LeagueGameFinder lags on setting WL while scores are already in;
        the series count must still update so the game shows in Finals.
        """
        from routes.scores import _fetch_playoff_series_data

        lgf_rows = [
            ["PG01", TEAM_ID_LAL, None, 90, "2026-06-03", "LAL vs. BOS"],
            ["PG01", TEAM_ID_BOS, None, 94, "2026-06-03", "BOS @ LAL"],
        ]
        with patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)):
            pair_wins, pair_games = _fetch_playoff_series_data("2025-26")
        lo, hi = sorted((TEAM_ID_LAL, TEAM_ID_BOS))
        key = f"{lo}_{hi}"
        assert pair_wins[key] == {str(TEAM_ID_BOS): 1, str(TEAM_ID_LAL): 0}
        assert len(pair_games[key]) == 1

    def test_series_no_win_when_pts_tied_and_wl_missing(self):
        """WL=None and equal PTS -> no winner inferred (entry stays 0-0)."""
        from routes.scores import _fetch_playoff_series_data

        lgf_rows = [
            ["PG01", TEAM_ID_LAL, None, 90, "2026-06-03", "LAL vs. BOS"],
            ["PG01", TEAM_ID_BOS, None, 90, "2026-06-03", "BOS @ LAL"],
        ]
        with patch("routes.scores.LeagueGameFinder", self._lgf_mock(lgf_rows)):
            pair_wins, _ = _fetch_playoff_series_data("2025-26")
        lo, hi = sorted((TEAM_ID_LAL, TEAM_ID_BOS))
        assert pair_wins[f"{lo}_{hi}"] == {str(lo): 0, str(hi): 0}


# Every route picks between a live TTL and the 24h "historical" one. Line
# coverage reaches both branches, but nothing asserted which TTL was chosen, so
# swapping them would have served day-old boxscores with a green suite.


class TestCacheTtlSelection:
    @staticmethod
    def _ttls(set_mock):
        return [call.args[2] for call in set_mock.call_args_list]

    @pytest.mark.parametrize(
        ("days_offset", "expected"),
        [(1, []), (2, [CACHE_TTL["historical"]])],
    )
    def test_boxscores_ttl(self, client, days_offset, expected):
        with (
            patch("routes.scores.get_games_leaders_list", return_value={}),
            patch("routes.scores.cache.set") as set_mock,
        ):
            r = client.get(f"/api/boxscores?days_offset={days_offset}")
        assert r.status_code == 200
        assert self._ttls(set_mock) == expected

    @pytest.mark.parametrize(
        ("days_offset", "expected"),
        [(1, []), (2, [CACHE_TTL["historical"]])],
    )
    def test_leaders_ttl(self, client, days_offset, expected):
        with (
            patch("routes.scores.get_games_list", return_value=[]),
            patch("routes.scores.cache.set") as set_mock,
        ):
            r = client.get(f"/api/leaders?days_offset={days_offset}")
        assert r.status_code == 200
        assert self._ttls(set_mock) == expected

    @pytest.mark.parametrize(
        ("season", "expected"),
        [(None, CACHE_TTL["season_leaders"]), ("2020-21", CACHE_TTL["historical"])],
    )
    def test_season_highs_ttl(self, client, season, expected):
        gamelog = MagicMock()
        gamelog.get_dict.return_value = {"resultSets": [{"headers": [], "rowSet": []}]}
        query = f"?season={season}" if season else ""
        with (
            patch("routes.season.leaguegamelog.LeagueGameLog", return_value=gamelog),
            patch("routes.season.cache.set") as set_mock,
        ):
            r = client.get(f"/api/season/highs{query}")
        assert r.status_code == 200
        assert self._ttls(set_mock) == [expected]


class TestUpstreamEdgeStates:
    def test_game_players_skips_inactive_and_handles_zero_attempts(self, client):
        bs = make_live_boxscore()
        bs["game"]["homeTeam"]["players"].extend(
            [
                make_live_player(
                    person_id=1, name="Did Not Play", status="INACTIVE", points=99
                ),
                make_live_player(
                    person_id=2,
                    name="Zero Shots",
                    points=0,
                    fieldGoalsMade=0,
                    fieldGoalsAttempted=0,
                    freeThrowsMade=0,
                    freeThrowsAttempted=0,
                ),
            ]
        )
        with patch("routes.players.get_cached_live_boxscore", return_value=bs):
            r = client.get(f"/api/games/{GAME_ID}/players")
        assert r.status_code == 200
        home = next(t for t in r.json()["teams"] if t["tricode"] == "LAL")
        by_name = {p["name"]: p for p in home["players"]}
        assert "Did Not Play" not in by_name
        assert by_name["Zero Shots"]["fgPct"] == 0

    def test_player_stats_handles_zero_attempts(self, client):
        bs = make_live_boxscore()
        bs["game"]["homeTeam"]["players"] = [
            make_live_player(
                person_id=PLAYER_ID,
                points=0,
                fieldGoalsMade=0,
                fieldGoalsAttempted=0,
                freeThrowsMade=0,
                freeThrowsAttempted=0,
            )
        ]
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
        p = r.json()["players"][0]
        assert p["fg"] == "0/0"
        assert p["ft"] == "0/0"

    def test_doubles_sums_both_teams_of_a_traded_player(self, client):
        # A mid-season trade gives the same PLAYER_ID one row per team
        rows = [
            _make_doubles_row(1, "Traded Player", "LAL", 7, 1),
            _make_doubles_row(1, "Traded Player", "BOS", 5, 2),
        ]
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            _mock_league_dash(rows),
        ):
            r = client.get("/api/season/doubles")
        dd = r.json()["doubleDoubles"]
        assert len(dd) == 1
        assert dd[0]["count"] == 12
        assert r.json()["tripleDoubles"][0]["count"] == 3

    def test_standings_preseason_row_without_pct_or_games_back(self, client):
        row = make_standings_row(1, "Boston", "Celtics", "East", 0, 0)
        row[14] = None  # WIN_PCT — null until the first game is played
        row[37] = None  # GAMES_BACK
        standings = MagicMock()
        standings.return_value.get_dict.return_value = {
            "resultSets": [{"rowSet": [row]}]
        }
        with patch("routes.scores.leaguestandings.LeagueStandings", standings):
            r = client.get("/api/standings")
        t = r.json()["east"][0]
        assert t["winPct"] == 0
        assert t["gamesBack"] == "-"


class TestBoxscoreExtras:
    def _live_box(self):
        bs = make_live_boxscore(status="Q3 4:10")
        game = bs["game"]
        game["gameStatus"] = 2
        home = game["homeTeam"]
        home["players"] = [
            {**make_live_player(), "starter": "1", "oncourt": "1"},
            make_live_player(person_id=2, name="Hurt Guy", status="INACTIVE", points=0)
            | {
                "notPlayingReason": "INACTIVE_INJURY",
                "notPlayingDescription": "Right Knee; N/A",
            },
            make_live_player(person_id=3, name="Two Way", status="INACTIVE", points=0)
            | {"notPlayingReason": "INACTIVE_GLEAGUE_TWOWAY"},
        ]
        home["statistics"] = {
            "pointsInThePaint": 40,
            "pointsSecondChance": 12,
            "pointsFastBreak": 9,
            "pointsFromTurnovers": 15,
            "benchPoints": 30,
            "biggestLead": 14,
            "biggestScoringRun": 10,
            "leadChanges": 7,
            "timesTied": 5,
        }
        return bs

    def test_live_extras(self, client):
        gid = "0022500888"
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=self._live_box()
        ):
            body = client.get(f"/api/games/{gid}/players").json()
        assert body["leadChanges"] == 7
        assert body["timesTied"] == 5
        home = next(t for t in body["teams"] if t["tricode"] == "LAL")
        away = next(t for t in body["teams"] if t["tricode"] == "BOS")
        assert home["flow"]["paint"] == 40
        assert home["flow"]["biggestRun"] == 10
        assert away["flow"] is None
        player = home["players"][0]
        assert player["starter"] is True
        assert player["onCourt"] is True
        assert player["plusMinus"] == 8
        assert home["inactive"] == [
            {"name": "Hurt Guy", "reason": "Right Knee"},
            {"name": "Two Way", "reason": "G League two-way"},
        ]

    def test_final_game_has_no_on_court_flag(self, client):
        with patch(
            "routes.players.get_cached_live_boxscore", return_value=make_live_boxscore()
        ):
            body = client.get(f"/api/games/{GAME_ID}/players").json()
        assert "onCourt" not in body["teams"][0]["players"][0]
        assert body["leadChanges"] is None

    def test_v3_starter_and_plus_minus(self, client):
        from conftest import WNBA_LVA, WNBA_NYL, make_v3_player_row

        gid = "1042500405"
        box = {
            "headers": V3_PLAYER_STATS_HEADERS,
            "data": [
                make_v3_player_row(
                    gid, WNBA_NYL, 1, "Start", "Er", position="G", plusMinusPoints=7.0
                ),
                make_v3_player_row(gid, WNBA_LVA, 2, "Bench", "Er"),
            ],
        }
        with (
            patch(
                "routes.players.get_cached_live_boxscore",
                side_effect=requests.RequestException("404"),
            ),
            patch("routes.players.get_cached_boxscore_v3", return_value=box),
            patch("routes.players.log_exceptions"),
        ):
            body = client.get(f"/api/games/{gid}/players").json()
        nyl = next(t for t in body["teams"] if t["tricode"] == "NYL")
        lva = next(t for t in body["teams"] if t["tricode"] == "LVA")
        assert nyl["players"][0]["starter"] is True
        assert nyl["players"][0]["plusMinus"] == 7
        assert lva["players"][0]["starter"] is False
        assert nyl["inactive"] == []


class TestRecordsAndStandingsColumns:
    def test_scoreboard_records(self, client):
        from datetime import date

        live = [make_live_game(gameStatus=2) | {"gameCode": "20260307/BOSLAL"}]
        live[0]["homeTeam"] = live[0]["homeTeam"] | {"wins": 3, "losses": 1}
        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date",
                return_value=make_scoreboard_v3([make_live_game()]),
            ),
            patch("routes.scores.get_cached_scoreboard", return_value=live),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
        ):
            game = client.get("/api/scoreboard").json()["games"][0]
        assert game["homeTeam"]["record"] == "3-1"
        assert game["awayTeam"]["record"] == ""

    def test_v3_scoreboard_records(self, client):
        from datetime import date

        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date",
                return_value=make_scoreboard_v3([make_live_game()]),
            ),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
        ):
            game = client.get("/api/scoreboard").json()["games"][0]
        assert game["homeTeam"]["record"] == "0-0"

    def test_playoff_games_have_no_record(self, client):
        from datetime import date

        game = make_live_game(gameId="0042500101")
        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date",
                return_value=make_scoreboard_v3([game]),
            ),
            patch("routes.scores.get_cached_scoreboard", return_value=[]),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 5, 1)),
        ):
            sb_game = client.get("/api/scoreboard").json()["games"][0]
        assert sb_game["homeTeam"]["record"] == ""

    def test_standings_points_columns(self, client):
        rows = [make_standings_row(1, "Boston", "Celtics", "East", 50, 20)]
        standings = MagicMock()
        standings.return_value.get_dict.return_value = {
            "resultSets": [{"rowSet": rows}]
        }
        with patch("routes.scores.leaguestandings.LeagueStandings", standings):
            team = client.get("/api/standings").json()["east"][0]
        assert (team["ppg"], team["oppPpg"], team["diff"]) == (112.4, 108.1, 4.3)


LEADERS_HEADERS = [
    "PLAYER_ID",
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "GP",
    "FGM",
    "FGA",
    "FTM",
    "FTA",
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "FG3M",
]


def _leaders_row(pid, name, team, gp, fgm, fga, pts, reb=0, ast=0, ftm=0, fta=0):
    return [pid, name, team, gp, fgm, fga, ftm, fta, pts, reb, ast, 0, 0, 0]


class TestSeasonLeaders:
    def _get(self, client, rows):
        full = MagicMock()
        full.get_dict.return_value = {
            "resultSets": [{"headers": LEADERS_HEADERS, "rowSet": rows}]
        }
        empty = MagicMock()
        empty.get_dict.return_value = {
            "resultSets": [{"headers": LEADERS_HEADERS, "rowSet": []}]
        }
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            side_effect=[full, empty],
        ):
            return client.get("/api/season/leaders").json()

    def test_per_game_ranking_and_qualifier(self, client):
        rows = [
            _leaders_row(1, "Star", "OKC", 10, 100, 200, 300),
            # traded: two rows summed -> 10 GP, 250 PTS
            _leaders_row(2, "Traded", "LAL", 4, 40, 100, 100),
            _leaders_row(2, "Traded", "BOS", 6, 60, 100, 150),
            # 6 GP < 70% of 10 -> not qualified despite 40 PPG
            _leaders_row(3, "Rookie", "SAS", 6, 90, 150, 240),
        ]
        body = self._get(client, rows)
        assert body["minGames"] == 7
        points = next(c for c in body["categories"] if c["key"] == "points")
        assert [(p["name"], p["value"]) for p in points["players"]] == [
            ("Star", 30.0),
            ("Traded", 25.0),
        ]
        assert points["short"] == "PPG"

    def test_fg_pct_needs_enough_makes(self, client):
        rows = [
            _leaders_row(1, "Volume", "OKC", 10, 50, 100, 120),
            _leaders_row(2, "Rare", "LAL", 10, 10, 10, 20),
        ]
        body = self._get(client, rows)
        fg = next(c for c in body["categories"] if c["key"] == "fgPct")
        assert [(p["name"], p["value"]) for p in fg["players"]] == [("Volume", 50.0)]

    def test_ft_pct_needs_enough_makes(self, client):
        rows = [
            _leaders_row(1, "Liner", "OKC", 10, 50, 100, 120, ftm=40, fta=50),
            _leaders_row(2, "Rare", "LAL", 10, 50, 100, 120, ftm=5, fta=5),
        ]
        body = self._get(client, rows)
        ft = next(c for c in body["categories"] if c["key"] == "ftPct")
        assert [(p["name"], p["value"]) for p in ft["players"]] == [("Liner", 80.0)]

    def test_shares_totals_with_doubles(self, client):
        full = MagicMock()
        full.get_dict.return_value = {
            "resultSets": [{"headers": LEADERS_HEADERS + ["DD2", "TD3"], "rowSet": []}]
        }
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            return_value=full,
        ) as mock:
            client.get("/api/season/doubles")
            client.get("/api/season/leaders")
            client.get("/api/season/leaders")
        assert mock.call_count == 2
