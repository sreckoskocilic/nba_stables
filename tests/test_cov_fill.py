import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import helpers.stats as hs
from conftest import PLAYER_ID
from helpers.common import (
    SimpleCache,
    cache,
)
from helpers.logger import log_exceptions, logger
from helpers.stats import get_current_season
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_log_exceptions_with_context(monkeypatch):
    called = {"args": None}

    def fake_exception(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(logger, "exception", fake_exception)
    monkeypatch.setattr(logger, "isEnabledFor", lambda level: True)
    log_exceptions(Exception("boom"), "ctx123")
    assert called["args"] is not None
    assert any("ctx123" in str(a) for a in called["args"])


def test_fetch_players_parses_name_and_team(monkeypatch):
    mock_cap = MagicMock()
    mock_cap.common_all_players.get_dict.return_value = {
        "data": [
            [123, "Doe, John", None, None, None, None, None, 456],
            [999, "SingleName", None, None, None, None, None, None],
        ]
    }
    monkeypatch.setattr(hs.commonallplayers, "CommonAllPlayers", lambda **_: mock_cap)
    players = hs._fetch_players()
    assert players == [[123, "John Doe", 456], [999, "SingleName", None]]


def test_fetch_players_wnba_filters_inactive(monkeypatch):
    mock_cap = MagicMock()
    mock_cap.common_all_players.get_dict.return_value = {
        "data": [
            [101, "Active, Player", None, 1, None, None, None, 200],
            [102, "Inactive, Player", None, 0, None, None, None, 300],
        ]
    }
    monkeypatch.setattr(hs.commonallplayers, "CommonAllPlayers", lambda **_: mock_cap)
    players = hs._fetch_players(league_id="10")
    assert players == [[101, "Player Active", 200]]


def test_players_search_invalid_chars(client):
    r = client.get("/api/players/search?q=LeBron!")
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid characters in query"


def test_players_search_empty_spaces(client):
    r = client.get("/api/players/search?q=   ")
    assert r.status_code == 400


def test_players_search_http_exception_passthrough(client, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        "routes.players.load_players_with_lower",
        lambda league_id="00": (_ for _ in ()).throw(HTTPException(status_code=418)),
    )
    r = client.get("/api/players/search?q=LeBron")
    assert r.status_code == 418


def test_last_n_games_cached_branch(client):
    cache_key = f"last_n_games_00_{PLAYER_ID}_5_{get_current_season()}"
    cached_val = {"playerId": PLAYER_ID, "games": [{"gameId": "cached"}]}
    cache.set(cache_key, cached_val, 60)
    r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
    assert r.json() == cached_val


def test_last_n_games_playergamelog_path_with_dates(monkeypatch, client):
    # Force team_id=None to trigger gamelog fallback and provide a date to hit matchup_display else branch
    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda league_id="00": {PLAYER_ID: [PLAYER_ID, "Test Player", None]},
    )
    mock_pgl = MagicMock()
    mock_pgl.player_game_log.get_dict.return_value = {
        "data": [["", PLAYER_ID, "0022309999", "2026-03-10", "LAC @ IND"]]
    }
    monkeypatch.setattr(
        "routes.players.playergamelog.PlayerGameLog", lambda **_: mock_pgl
    )

    def player_stats_row(pid):
        row = [0] * 40
        row[6] = pid
        row[14] = "10:00"
        row[15] = 5
        row[16] = 10
        row[18] = 2
        row[19] = 5
        row[21] = 4
        row[22] = 4
        row[26] = 8
        row[27] = 6
        row[28] = 1
        row[29] = 2
        row[31] = 3
        row[32] = 20
        return row

    bs = MagicMock()
    bs.player_stats.get_dict.return_value = {"data": [player_stats_row(PLAYER_ID)]}
    bs.game_summary.get_dict.return_value = {
        "headers": ["GAME_DATE_EST"],
        "data": [["2026-03-10"]],
    }
    monkeypatch.setattr("routes.players.get_cached_boxscore_v3", lambda gid: bs)

    r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=1")
    assert r.status_code == 200
    matchup = r.json()["games"][0]["matchup"]
    assert matchup.startswith("2026-03-10 —")


def test_get_player_stats_value_error(client):
    r = client.get("/api/players/stats?ids=abc")
    assert r.status_code == 200
    assert r.json()["players"] == []


def test_player_stats_timeout_branch(monkeypatch, client):
    from concurrent.futures import Future

    class SlowFuture(Future):
        def result(self, timeout=None):
            raise TimeoutError()

    monkeypatch.setattr(
        "routes.players.load_players_dict", lambda league_id="00": {1: [1, "P1", None]}
    )
    monkeypatch.setattr(
        "routes.players.executor.submit", lambda fn, *a, **k: SlowFuture()
    )
    monkeypatch.setattr("routes.players.get_cached_scoreboard", lambda lid="00": [])
    r = client.get("/api/players/stats?ids=1")
    # should ignore timeouts and still return an empty list gracefully
    assert r.status_code == 200
    assert r.json()["players"] == []


def test_convert_et_to_cet_error_branch(monkeypatch):
    # Force datetime.now to raise to hit exception handler
    monkeypatch.setattr("helpers.stats.datetime", None)
    from helpers.stats import convert_et_to_cet

    assert convert_et_to_cet("7:00 pm ET") == "7:00 pm ET"


def test_simple_cache_expiry_and_eviction():
    sc = SimpleCache()
    sc.set("a", 1, ttl_seconds=0)
    assert sc.get("a") is None  # expired path deletes entry
    # Force an expired cache entry with empty heap to exercise deletion
    sc._cache["stale"] = {"data": 1, "expires": 0}
    sc._heap.clear()
    assert sc.get("stale") is None
    for i in range(10):
        sc.set(f"k{i}", i, ttl_seconds=1)
    assert sc.get("k0") == 0
    # Trigger background eviction directly
    with sc._lock:
        sc._evict_expired()
    assert sc.get("nonexistent") is None


def _make_stats_row(pid):
    row = [0] * 40
    row[6] = pid
    row[14] = "28:00"
    row[15] = 5
    row[16] = 10
    row[18] = 2
    row[19] = 5
    row[21] = 4
    row[22] = 4
    row[26] = 8
    row[27] = 6
    row[28] = 1
    row[29] = 2
    row[31] = 3
    row[32] = 20
    return row


def test_last_n_games_game_summary_date_path(monkeypatch, client):
    """Game date falls back to game_summary when the gamelog row has none."""
    fake_pid = 9991
    cache._cache.pop(f"last_n_games_00_{fake_pid}_1", None)
    cache._cache.pop(f"player_games_raw_00_{fake_pid}", None)

    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda league_id="00": {fake_pid: [fake_pid, "Test Player C", None]},
    )
    mock_pgl = MagicMock()
    mock_pgl.player_game_log.get_dict.return_value = {
        "data": [[None, None, "0022309991", "", "LAL vs BOS"]]
    }
    monkeypatch.setattr(
        "routes.players.playergamelog.PlayerGameLog", lambda **_: mock_pgl
    )

    bs = MagicMock()
    bs.player_stats.get_dict.return_value = {"data": [_make_stats_row(fake_pid)]}
    bs.game_summary.get_dict.return_value = {
        "headers": ["GAME_DATE_EST"],
        "data": [["2025-02-27"]],
    }
    monkeypatch.setattr("routes.players.get_cached_boxscore_v3", lambda gid: bs)

    r = client.get(f"/api/players/{fake_pid}/last-n-games?n=1")
    assert r.status_code == 200
    assert "2025-02-27" in r.json()["games"][0]["matchup"]


def test_last_n_games_matchup_date_prefix_path(monkeypatch, client):
    """Game date is parsed from the matchup YYYY-MM-DD prefix when row and summary lack it."""
    fake_pid = 9992
    cache._cache.pop(f"last_n_games_00_{fake_pid}_1", None)
    cache._cache.pop(f"player_games_raw_00_{fake_pid}", None)

    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda league_id="00": {fake_pid: [fake_pid, "Test Player D", None]},
    )
    mock_pgl = MagicMock()
    mock_pgl.player_game_log.get_dict.return_value = {
        "data": [[None, None, "0022309992", "", "2025-02-27 vs BOS"]]
    }
    monkeypatch.setattr(
        "routes.players.playergamelog.PlayerGameLog", lambda **_: mock_pgl
    )

    bs = MagicMock()
    bs.player_stats.get_dict.return_value = {"data": [_make_stats_row(fake_pid)]}
    bs.game_summary.get_dict.return_value = {"headers": [], "data": []}
    monkeypatch.setattr("routes.players.get_cached_boxscore_v3", lambda gid: bs)

    r = client.get(f"/api/players/{fake_pid}/last-n-games?n=1")
    assert r.status_code == 200
    matchup = r.json()["games"][0]["matchup"]
    assert matchup.startswith("2025-02-27 —")
    assert "vs BOS" in matchup


def test_get_cached_boxscore_v3_cache_miss(monkeypatch):
    """get_cached_boxscore_v3 fetches and returns the boxscore on a cache miss."""
    from helpers.stats import get_cached_boxscore_v3

    fake_game_id = "TESTGAME001"
    cache._cache.pop(f"raw_boxscore_{fake_game_id}", None)

    mock_bs = MagicMock()
    monkeypatch.setattr(
        "helpers.stats.boxscoretraditionalv3.BoxScoreTraditionalV3",
        lambda **_: mock_bs,
    )
    result = get_cached_boxscore_v3(fake_game_id)
    assert result is mock_bs


def test_lifespan_warns_invalid_workers(monkeypatch, caplog):
    """Lifespan warns when EXECUTOR_WORKERS is out of range."""
    import logging

    import helpers.common as _common

    monkeypatch.setattr(_common, "_DEFAULT_WORKERS", 0)
    with caplog.at_level(logging.WARNING, logger="main"), TestClient(app):
        pass
    assert "EXECUTOR_WORKERS" in caplog.text
    assert "outside reasonable range" in caplog.text


def test_lifespan_warns_invalid_timeout(monkeypatch, caplog):
    """Lifespan warns when STATS_TIMEOUT is less than 1."""
    import logging

    import helpers.common as _common

    monkeypatch.setattr(_common, "STATS_TIMEOUT", 0)
    with caplog.at_level(logging.WARNING, logger="main"), TestClient(app):
        pass
    assert "STATS_TIMEOUT" in caplog.text
    assert "must be >= 1" in caplog.text


def test_lifespan_warns_missing_injuries_file(monkeypatch, caplog):
    """Lifespan warns when the CBS injuries file is absent at startup."""
    import logging

    monkeypatch.setattr("main.os.path.exists", lambda _: False)
    with caplog.at_level(logging.WARNING, logger="main"), TestClient(app):
        pass
    assert "CBS injuries file not found" in caplog.text


def test_security_headers_page_route(client):
    """Cover security.py: non-API, non-soccer routes get PAGE_CSP."""
    # Any non-/api/, non-/soccer path hits the else branch
    r = client.get("/not-an-api-route")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "fonts.googleapis.com" in csp  # PAGE_CSP includes Google Fonts


# ─── /api/players/{id}/profile coverage fill ─────────────────────────────────


def test_calc_age_handles_empty_and_invalid():
    from routes.players import _calc_age

    assert _calc_age(None) is None
    assert _calc_age("") is None
    assert _calc_age("not-a-date") is None


def test_player_profile_cached_branch(client):
    cache_key = f"player_profile_00_{PLAYER_ID}"
    payload = {"playerId": PLAYER_ID, "bio": {}, "career": []}
    cache.set(cache_key, payload, 60)
    r = client.get(f"/api/players/{PLAYER_ID}/profile")
    assert r.json() == payload


def test_player_profile_404_when_bio_and_career_both_fail(client, monkeypatch):
    """Cover the _not_found return + 404 raise."""
    cpi_fail = MagicMock(side_effect=ValueError("boom bio"))
    pcs_fail = MagicMock(side_effect=ValueError("boom career"))
    monkeypatch.setattr("routes.players.commonplayerinfo.CommonPlayerInfo", cpi_fail)
    monkeypatch.setattr("routes.players.playercareerstats.PlayerCareerStats", pcs_fail)
    r = client.get(f"/api/players/{PLAYER_ID}/profile")
    assert r.status_code == 404


def test_scoreboard_skips_phantom_scheduled_games(client, monkeypatch):
    from datetime import date
    from unittest.mock import patch

    from conftest import make_live_game, make_scoreboard_v3

    real_game = make_live_game(gameStatusText="Final")
    phantom = make_live_game(
        gameId="0042600105",
        gameStatusText="TBD",
        gameEt="2026-05-16T00:00:00Z",
    )
    sb_v3 = make_scoreboard_v3([real_game, phantom])
    with (
        patch("routes.scores.get_scoreboard_v3_by_date", return_value=sb_v3),
        patch("routes.scores.scoreboard_date", return_value=date(2026, 3, 7)),
        patch("routes.scores.get_cached_scoreboard", return_value=[]),
    ):
        r = client.get("/api/scoreboard")
    assert r.status_code == 200
    games = r.json()["games"]
    assert len(games) == 1
    assert games[0]["gameId"] == real_game["gameId"]
