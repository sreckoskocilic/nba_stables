"""Integration tests for /api/season/highs, /api/season/doubles, and
/api/season/triple-double-games/{player_id}."""

from unittest.mock import MagicMock, patch

import pytest
from conftest import PLAYER_ID
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
# Helpers for /api/season/highs
# ─────────────────────────────────────────────────────────────────────────────

HIGHS_HEADERS = [
    "PLAYER_NAME",
    "TEAM_ABBREVIATION",
    "GAME_DATE",
    "MATCHUP",
    "PTS",
    "REB",
    "AST",
    "BLK",
    "STL",
    "FG3M",
    "FGM",
    "FTM",
    "FTA",
    "OREB",
    "DREB",
    "TOV",
]


def _highs_row(
    name="LeBron James",
    team="LAL",
    date="2024-01-15",
    matchup="LAL vs. BOS",
    pts=0,
    reb=0,
    ast=0,
    blk=0,
    stl=0,
    fg3m=0,
    fgm=0,
    ftm=0,
    fta=0,
    oreb=0,
    dreb=0,
    tov=0,
):
    h = {k: i for i, k in enumerate(HIGHS_HEADERS)}
    row = [None] * len(HIGHS_HEADERS)
    row[h["PLAYER_NAME"]] = name
    row[h["TEAM_ABBREVIATION"]] = team
    row[h["GAME_DATE"]] = date
    row[h["MATCHUP"]] = matchup
    row[h["PTS"]] = pts
    row[h["REB"]] = reb
    row[h["AST"]] = ast
    row[h["BLK"]] = blk
    row[h["STL"]] = stl
    row[h["FG3M"]] = fg3m
    row[h["FGM"]] = fgm
    row[h["FTM"]] = ftm
    row[h["FTA"]] = fta
    row[h["OREB"]] = oreb
    row[h["DREB"]] = dreb
    row[h["TOV"]] = tov
    return row


def _mock_gamelog(rows):
    mock = MagicMock()
    mock.get_dict.return_value = {
        "resultSets": [{"headers": HIGHS_HEADERS, "rowSet": rows}]
    }
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Tests: GET /api/season/highs
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSeasonHighs:
    def _call(self, client, rows):
        mock = _mock_gamelog(rows)
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch("routes.season.leaguegamelog.LeagueGameLog", return_value=mock),
        ):
            return client.get("/api/season/highs")

    def test_returns_200(self, client):
        resp = self._call(client, [_highs_row(pts=30)])
        assert resp.status_code == 200

    def test_response_has_highs_and_season_keys(self, client):
        resp = self._call(client, [_highs_row(pts=30)])
        body = resp.json()
        assert "highs" in body
        assert "season" in body

    def test_season_value(self, client):
        resp = self._call(client, [_highs_row(pts=30)])
        assert resp.json()["season"] == "2024-25"

    def test_all_categories_present(self, client):
        expected_keys = {
            "points",
            "rebounds",
            "assists",
            "blocks",
            "steals",
            "threePointers",
            "fgm",
            "ftm",
            "fta",
            "oreb",
            "dreb",
            "turnovers",
        }
        resp = self._call(client, [_highs_row(pts=30)])
        assert set(resp.json()["highs"].keys()) == expected_keys

    def test_category_has_label_value_players(self, client):
        resp = self._call(client, [_highs_row(pts=30)])
        pts = resp.json()["highs"]["points"]
        assert "label" in pts
        assert "value" in pts
        assert "players" in pts

    def test_points_high_correct_value(self, client):
        rows = [
            _highs_row(name="Player A", pts=50),
            _highs_row(name="Player B", pts=40),
        ]
        resp = self._call(client, rows)
        assert resp.json()["highs"]["points"]["value"] == 50

    def test_points_high_correct_player(self, client):
        rows = [
            _highs_row(name="Player A", pts=50),
            _highs_row(name="Player B", pts=40),
        ]
        resp = self._call(client, rows)
        players = resp.json()["highs"]["points"]["players"]
        assert len(players) == 1
        assert players[0]["name"] == "Player A"

    def test_ties_include_all_tied_players(self, client):
        rows = [
            _highs_row(name="Player A", pts=50),
            _highs_row(name="Player B", pts=50),
        ]
        resp = self._call(client, rows)
        players = resp.json()["highs"]["points"]["players"]
        assert len(players) == 2
        names = {p["name"] for p in players}
        assert names == {"Player A", "Player B"}

    def test_player_entry_has_required_fields(self, client):
        rows = [
            _highs_row(
                name="Player A",
                team="LAL",
                date="2024-01-15",
                matchup="LAL vs. BOS",
                pts=30,
            )
        ]
        resp = self._call(client, rows)
        player = resp.json()["highs"]["points"]["players"][0]
        assert player["name"] == "Player A"
        assert player["team"] == "LAL"
        assert player["date"] == "2024-01-15"
        assert player["matchup"] == "LAL vs. BOS"

    def test_zero_value_stays_zero_with_no_players(self, client):
        # If no row has assists > 0, value stays 0 and players is empty
        rows = [_highs_row(pts=30, ast=0)]
        resp = self._call(client, rows)
        ast_high = resp.json()["highs"]["assists"]
        assert ast_high["value"] == 0
        assert ast_high["players"] == []

    def test_null_stat_treated_as_zero(self, client):
        # None values should not crash and should count as 0
        row = _highs_row(pts=None)
        resp = self._call(client, [row])
        assert resp.status_code == 200
        assert resp.json()["highs"]["points"]["value"] == 0

    def test_multiple_categories_tracked_independently(self, client):
        rows = [
            _highs_row(name="Scorer", pts=60, reb=5),
            _highs_row(name="Rebounder", pts=10, reb=25),
        ]
        resp = self._call(client, rows)
        highs = resp.json()["highs"]
        assert highs["points"]["players"][0]["name"] == "Scorer"
        assert highs["rebounds"]["players"][0]["name"] == "Rebounder"

    def test_mojibake_player_name_fixed(self, client):
        original = "Joki\u0107"
        mojibake = original.encode("utf-8").decode("latin-1")
        rows = [_highs_row(name=mojibake, pts=45)]
        resp = self._call(client, rows)
        assert resp.json()["highs"]["points"]["players"][0]["name"] == original

    def test_cache_hit_skips_api_call(self, client):
        mock = _mock_gamelog([_highs_row(pts=30)])
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch(
                "routes.season.leaguegamelog.LeagueGameLog", return_value=mock
            ) as api_mock,
        ):
            client.get("/api/season/highs")
            client.get("/api/season/highs")
        api_mock.assert_called_once()

    def test_empty_rows_returns_all_zeros(self, client):
        resp = self._call(client, [])
        assert resp.status_code == 200
        for key, entry in resp.json()["highs"].items():
            assert entry["value"] == 0, f"{key} should be 0 with no data"
            assert entry["players"] == []

    def test_points_label(self, client):
        resp = self._call(client, [])
        assert resp.json()["highs"]["points"]["label"] == "Points"

    def test_three_pointers_label(self, client):
        resp = self._call(client, [])
        assert resp.json()["highs"]["threePointers"]["label"] == "3-Pointers"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for /api/season/doubles
# ─────────────────────────────────────────────────────────────────────────────

DOUBLES_HEADERS = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "DD2", "TD3"]


def _doubles_row(player_id=1, name="Player", team="LAL", dd2=0, td3=0):
    h = {k: i for i, k in enumerate(DOUBLES_HEADERS)}
    row = [None] * len(DOUBLES_HEADERS)
    row[h["PLAYER_ID"]] = player_id
    row[h["PLAYER_NAME"]] = name
    row[h["TEAM_ABBREVIATION"]] = team
    row[h["DD2"]] = dd2
    row[h["TD3"]] = td3
    return row


def _mock_dash_stats(rows):
    mock = MagicMock()
    mock.get_dict.return_value = {
        "resultSets": [{"headers": DOUBLES_HEADERS, "rowSet": rows}]
    }
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Tests: GET /api/season/doubles
# ─────────────────────────────────────────────────────────────────────────────


class TestGetSeasonDoubles:
    def _call(self, client, rows):
        mock = _mock_dash_stats(rows)
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            return_value=mock,
        ):
            return client.get("/api/season/doubles")

    def test_returns_200(self, client):
        resp = self._call(client, [])
        assert resp.status_code == 200

    def test_response_has_double_doubles_and_triple_doubles(self, client):
        resp = self._call(client, [])
        body = resp.json()
        assert "doubleDoubles" in body
        assert "tripleDoubles" in body

    def test_players_with_dd2_included(self, client):
        rows = [_doubles_row(player_id=1, name="Player A", dd2=30)]
        resp = self._call(client, rows)
        assert len(resp.json()["doubleDoubles"]) == 1

    def test_players_with_zero_dd2_excluded(self, client):
        rows = [_doubles_row(player_id=1, name="Player A", dd2=0)]
        resp = self._call(client, rows)
        assert resp.json()["doubleDoubles"] == []

    def test_players_with_td3_included(self, client):
        rows = [_doubles_row(player_id=1, name="Player A", td3=5)]
        resp = self._call(client, rows)
        assert len(resp.json()["tripleDoubles"]) == 1

    def test_players_with_zero_td3_excluded(self, client):
        rows = [_doubles_row(player_id=1, name="Player A", td3=0)]
        resp = self._call(client, rows)
        assert resp.json()["tripleDoubles"] == []

    def test_double_doubles_sorted_descending(self, client):
        rows = [
            _doubles_row(player_id=1, name="A", dd2=10),
            _doubles_row(player_id=2, name="B", dd2=30),
            _doubles_row(player_id=3, name="C", dd2=20),
        ]
        resp = self._call(client, rows)
        counts = [p["count"] for p in resp.json()["doubleDoubles"]]
        assert counts == sorted(counts, reverse=True)

    def test_triple_doubles_sorted_descending(self, client):
        rows = [
            _doubles_row(player_id=1, name="A", td3=3),
            _doubles_row(player_id=2, name="B", td3=10),
        ]
        resp = self._call(client, rows)
        counts = [p["count"] for p in resp.json()["tripleDoubles"]]
        assert counts == sorted(counts, reverse=True)

    def test_double_doubles_has_rank(self, client):
        rows = [_doubles_row(player_id=1, name="A", dd2=5)]
        resp = self._call(client, rows)
        assert resp.json()["doubleDoubles"][0]["rank"] == 1

    def test_triple_doubles_has_rank(self, client):
        rows = [_doubles_row(player_id=1, name="A", td3=5)]
        resp = self._call(client, rows)
        assert resp.json()["tripleDoubles"][0]["rank"] == 1

    def test_rank_increments(self, client):
        rows = [
            _doubles_row(player_id=1, name="A", dd2=30),
            _doubles_row(player_id=2, name="B", dd2=20),
        ]
        resp = self._call(client, rows)
        ranks = [p["rank"] for p in resp.json()["doubleDoubles"]]
        assert ranks == [1, 2]

    def test_player_entry_has_name_team_player_id(self, client):
        rows = [_doubles_row(player_id=99, name="Test Player", team="GSW", dd2=15)]
        resp = self._call(client, rows)
        entry = resp.json()["doubleDoubles"][0]
        assert entry["name"] == "Test Player"
        assert entry["team"] == "GSW"
        assert entry["playerId"] == 99

    def test_double_doubles_capped_at_30(self, client):
        rows = [_doubles_row(player_id=i, name=f"P{i}", dd2=i + 1) for i in range(40)]
        resp = self._call(client, rows)
        assert len(resp.json()["doubleDoubles"]) == 30

    def test_triple_doubles_capped_at_20(self, client):
        rows = [_doubles_row(player_id=i, name=f"P{i}", td3=i + 1) for i in range(25)]
        resp = self._call(client, rows)
        assert len(resp.json()["tripleDoubles"]) == 20

    def test_cache_hit_skips_api_call(self, client):
        mock = _mock_dash_stats([])
        with patch(
            "routes.season.leaguedashplayerstats.LeagueDashPlayerStats",
            return_value=mock,
        ) as api_mock:
            client.get("/api/season/doubles")
            client.get("/api/season/doubles")
        api_mock.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for /api/season/triple-double-games/{player_id}
# ─────────────────────────────────────────────────────────────────────────────

TD_GAMES_HEADERS = ["GAME_DATE", "MATCHUP", "PTS", "REB", "AST", "STL", "BLK"]


def _td_game_row(
    date="2024-01-15", matchup="LAL vs. BOS", pts=0, reb=0, ast=0, stl=0, blk=0
):
    h = {k: i for i, k in enumerate(TD_GAMES_HEADERS)}
    row = [None] * len(TD_GAMES_HEADERS)
    row[h["GAME_DATE"]] = date
    row[h["MATCHUP"]] = matchup
    row[h["PTS"]] = pts
    row[h["REB"]] = reb
    row[h["AST"]] = ast
    row[h["STL"]] = stl
    row[h["BLK"]] = blk
    return row


def _mock_player_gamelog(rows):
    mock = MagicMock()
    mock.get_dict.return_value = {
        "resultSets": [{"headers": TD_GAMES_HEADERS, "rowSet": rows}]
    }
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# Tests: GET /api/season/triple-double-games/{player_id}
# ─────────────────────────────────────────────────────────────────────────────


_FAKE_PLAYER = {PLAYER_ID: [PLAYER_ID, "LeBron James", 1]}


class TestGetTripleDoubleGames:
    def _call(self, client, rows, player_id=PLAYER_ID, season=None):
        mock = _mock_player_gamelog(rows)
        url = f"/api/season/triple-double-games/{player_id}"
        if season:
            url += f"?season={season}"
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch("routes.season.load_players_dict", return_value=_FAKE_PLAYER),
            patch("routes.season.playergamelog.PlayerGameLog", return_value=mock),
        ):
            return client.get(url)

    def test_returns_200(self, client):
        resp = self._call(client, [])
        assert resp.status_code == 200

    def test_response_has_player_id_and_games(self, client):
        resp = self._call(client, [])
        body = resp.json()
        assert "playerId" in body
        assert "games" in body

    def test_player_id_in_response(self, client):
        resp = self._call(client, [], player_id=PLAYER_ID)
        assert resp.json()["playerId"] == PLAYER_ID

    def test_triple_double_pts_reb_ast_included(self, client):
        row = _td_game_row(pts=10, reb=10, ast=10)
        resp = self._call(client, [row])
        assert len(resp.json()["games"]) == 1

    def test_triple_double_pts_reb_stl_included(self, client):
        row = _td_game_row(pts=10, reb=10, stl=10)
        resp = self._call(client, [row])
        assert len(resp.json()["games"]) == 1

    def test_triple_double_pts_ast_blk_included(self, client):
        row = _td_game_row(pts=10, ast=10, blk=10)
        resp = self._call(client, [row])
        assert len(resp.json()["games"]) == 1

    def test_non_triple_double_excluded(self, client):
        row = _td_game_row(pts=30, reb=9, ast=9)
        resp = self._call(client, [row])
        assert resp.json()["games"] == []

    def test_double_double_excluded(self, client):
        row = _td_game_row(pts=10, reb=10, ast=9)
        resp = self._call(client, [row])
        assert resp.json()["games"] == []

    def test_game_entry_has_required_fields(self, client):
        row = _td_game_row(
            date="2024-02-01", matchup="LAL @ BOS", pts=12, reb=10, ast=10
        )
        resp = self._call(client, [row])
        game = resp.json()["games"][0]
        assert game["date"] == "2024-02-01"
        assert game["matchup"] == "LAL @ BOS"
        assert game["points"] == 12
        assert game["rebounds"] == 10
        assert game["assists"] == 10
        assert "steals" in game
        assert "blocks" in game

    def test_empty_log_returns_empty_games(self, client):
        resp = self._call(client, [])
        assert resp.json()["games"] == []

    def test_multiple_triple_doubles(self, client):
        rows = [
            _td_game_row(pts=10, reb=10, ast=10),
            _td_game_row(pts=20, reb=12, ast=11),
        ]
        resp = self._call(client, rows)
        assert len(resp.json()["games"]) == 2

    def test_cache_hit_skips_api_call(self, client):
        mock = _mock_player_gamelog([])
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch("routes.season.load_players_dict", return_value=_FAKE_PLAYER),
            patch(
                "routes.season.playergamelog.PlayerGameLog", return_value=mock
            ) as api_mock,
        ):
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        api_mock.assert_called_once()

    def test_season_param_accepted(self, client):
        resp = self._call(client, [], season="2023-24")
        assert resp.status_code == 200

    def test_season_param_uses_historical_ttl(self, client):
        # Different season params produce independent cache keys
        mock = _mock_player_gamelog([])
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch("routes.season.load_players_dict", return_value=_FAKE_PLAYER),
            patch(
                "routes.season.playergamelog.PlayerGameLog", return_value=mock
            ) as api_mock,
        ):
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
            client.get(f"/api/season/triple-double-games/{PLAYER_ID}?season=2023-24")
        assert api_mock.call_count == 2

    def test_unknown_player_returns_404(self, client):
        mock = _mock_player_gamelog([])
        with (
            patch("routes.season.get_current_season", return_value="2024-25"),
            patch("routes.season.load_players_dict", return_value={}),
            patch("routes.season.playergamelog.PlayerGameLog", return_value=mock),
        ):
            resp = client.get(f"/api/season/triple-double-games/{PLAYER_ID}")
        assert resp.status_code == 404

    def test_null_stats_treated_as_zero(self, client):
        # None values should not raise errors and should not count as double digits
        row = _td_game_row(pts=None, reb=None, ast=None)
        resp = self._call(client, [row])
        assert resp.status_code == 200
        assert resp.json()["games"] == []
