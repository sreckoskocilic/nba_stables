from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from conftest import (
    GAME_ID,
    make_live_boxscore,
    make_live_game,
    make_live_player,
    make_scoreboard_v3,
)
from helpers.stats import live_clock_seconds
from main import app
from routes.scores import _refresh_live_games


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _real_box_refresh():
    with patch("routes.scores._refresh_live_games", _refresh_live_games):
        yield


def stuck_game(**kw):
    fields = {
        "gameStatus": 2,
        "gameStatusText": "4th Qtr             ",
        "period": 4,
        "gameClock": "PT01M59.00S",
    }
    fields.update(kw)
    return make_live_game(**fields)


def box(status="Q4 :50.8", clock="PT00M50.80S", period=4, home=114, away=108):
    data = make_live_boxscore(status=status)
    data["game"].update(period=period, gameClock=clock)
    data["game"]["homeTeam"]["score"] = home
    data["game"]["awayTeam"]["score"] = away
    data["game"]["homeTeam"]["players"] = [
        make_live_player(name="Bench Guy", points=2),
        make_live_player(name="Luka Doncic", points=49, reboundsTotal=5, assists=4),
    ]
    return data


def scoreboard(client, game, boxscore):
    with (
        patch(
            "routes.scores.get_scoreboard_v3_by_date",
            return_value=make_scoreboard_v3([game]),
        ),
        patch("routes.scores.scoreboard_date", return_value=date(2026, 11, 6)),
        patch("routes.scores.get_cached_scoreboard", return_value=[game]),
        patch("routes.scores.get_cached_live_boxscore", **boxscore) as fetch,
        patch("routes.scores.log_exceptions"),
    ):
        response = client.get("/api/scoreboard")
    assert response.status_code == 200
    return response.json()["games"][0], fetch


class TestStalledScoreboardFeed:
    def test_box_ahead_on_clock_wins(self, client):
        game, _ = scoreboard(client, stuck_game(), {"return_value": box()})
        assert game["status"] == "Q4 0:50"
        assert game["homeTeam"]["score"] == 114
        assert game["awayTeam"]["score"] == 108
        assert game["homeTeam"]["leader"] == {
            "name": "Luka Doncic",
            "points": 49,
            "rebounds": 5,
            "assists": 4,
        }

    def test_box_final_ends_game_still_running_on_scoreboard(self, client):
        final = box(status="Final", clock="PT00M00.00S", home=109, away=124)
        game, _ = scoreboard(client, stuck_game(), {"return_value": final})
        assert game["status"] == "Final"
        assert game["homeTeam"]["score"] == 109
        assert game["awayTeam"]["score"] == 124

    def test_same_clock_and_score_keeps_scoreboard(self, client):
        same = box(status="Q4 1:59", clock="PT01M59.00S", home=110, away=105)
        game, _ = scoreboard(client, stuck_game(), {"return_value": same})
        assert game["status"] == "Q4 1:59"
        assert game["homeTeam"]["leader"]["name"] == "LeBron James"

    def test_same_clock_higher_score_uses_box(self, client):
        free_throw = box(status="Q4 1:59", clock="PT01M59.00S", home=111, away=105)
        game, _ = scoreboard(client, stuck_game(), {"return_value": free_throw})
        assert game["status"] == "Q4 1:59"
        assert game["homeTeam"]["score"] == 111

    def test_box_behind_keeps_scoreboard(self, client):
        behind = box(status="Q4 3:00", clock="PT03M00.00S", home=100, away=100)
        game, _ = scoreboard(client, stuck_game(), {"return_value": behind})
        assert game["status"] == "Q4 1:59"
        assert game["homeTeam"]["score"] == 110

    def test_earlier_period_keeps_scoreboard(self, client):
        behind = box(status="Q3 :10", clock="PT00M10.00S", period=3)
        game, _ = scoreboard(client, stuck_game(), {"return_value": behind})
        assert game["status"] == "Q4 1:59"

    def test_box_failure_keeps_scoreboard(self, client):
        game, _ = scoreboard(client, stuck_game(), {"side_effect": Exception("down")})
        assert game["status"] == "Q4 1:59"
        assert game["homeTeam"]["score"] == 110

    def test_finished_game_skips_box_fetch(self, client):
        game, fetch = scoreboard(client, make_live_game(), {"return_value": box()})
        assert game["status"] == "Final"
        fetch.assert_not_called()

    def test_box_without_players_keeps_scoreboard_leader(self, client):
        data = box()
        data["game"]["homeTeam"]["players"] = []
        game, _ = scoreboard(client, stuck_game(), {"return_value": data})
        assert game["status"] == "Q4 0:50"
        assert game["homeTeam"]["leader"]["name"] == "LeBron James"

    def test_slow_box_keeps_scoreboard(self):
        games = [stuck_game()]
        with (
            patch("routes.scores.executor") as pool,
            patch("routes.scores.log_exceptions") as log,
        ):
            pool.map.side_effect = TimeoutError()
            assert _refresh_live_games(games, "00") == games
        log.assert_called_once()

    def test_v3_down_fallback_uses_box(self, client):
        live = stuck_game(gameCode="20261106/PORLAL")
        with (
            patch(
                "routes.scores.get_scoreboard_v3_by_date", side_effect=Exception("x")
            ),
            patch("routes.scores.scoreboard_date", return_value=date(2026, 11, 6)),
            patch("routes.scores.get_cached_scoreboard", return_value=[live]),
            patch("routes.scores.get_cached_live_boxscore", return_value=box()),
            patch("routes.scores.log_exceptions"),
        ):
            games = client.get("/api/scoreboard").json()["games"]
        assert games[0]["gameId"] == GAME_ID
        assert games[0]["status"] == "Q4 0:50"


@pytest.mark.parametrize(
    "clock,expected",
    [("PT00M50.80S", 50.8), ("PT01M59.00S", 119.0), ("", 0.0), (None, 0.0), ("x", 0.0)],
)
def test_live_clock_seconds(clock, expected):
    assert live_clock_seconds(clock) == expected
