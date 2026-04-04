import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

import helpers.stats as hs  # noqa: E402
from helpers.common import cache  # noqa: E402
from helpers.logger import logger, log_exceptions  # noqa: E402
from main import app  # noqa: E402
from conftest import PLAYER_ID  # noqa: E402
from helpers.common import SimpleCache  # noqa: E402


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
        lambda: (_ for _ in ()).throw(HTTPException(status_code=418)),
    )
    r = client.get("/api/players/search?q=LeBron")
    assert r.status_code == 418


def test_last_n_games_cached_branch(client):
    cache_key = f"last_n_games_{PLAYER_ID}_5"
    cached_val = {"playerId": PLAYER_ID, "games": [{"gameId": "cached"}]}
    cache.set(cache_key, cached_val, 60)
    r = client.get(f"/api/players/{PLAYER_ID}/last-n-games?n=5")
    assert r.json() == cached_val


def test_last_n_games_playergamelog_path_with_dates(monkeypatch, client):
    # Force team_id=None to trigger gamelog fallback and provide a date to hit matchup_display else branch
    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda: {PLAYER_ID: [PLAYER_ID, "Test Player", None]},
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
        "routes.players.load_players_dict", lambda: {1: [1, "P1", None]}
    )
    monkeypatch.setattr(
        "routes.players.executor.submit", lambda fn, *a, **k: SlowFuture()
    )
    monkeypatch.setattr("routes.players.get_cached_scoreboard", lambda: [])
    r = client.get("/api/players/stats?ids=1")
    # should ignore timeouts and still return an empty list gracefully
    assert r.status_code == 200
    assert r.json()["players"] == []


def test_convert_et_to_cet_error_branch(monkeypatch):
    # Force datetime.now to raise to hit exception handler
    monkeypatch.setattr("helpers.stats.datetime", None)
    from helpers.stats import convert_et_to_cet

    assert convert_et_to_cet("7:00 pm ET") == "7:00 pm ET"


def test_cors_wildcard_allowed_when_env_set(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    sys.modules.pop("main", None)
    app_mod = importlib.import_module("main")
    cors = next(
        m for m in app_mod.app.user_middleware if m.cls.__name__ == "CORSMiddleware"
    )
    assert cors.kwargs.get("allow_origins") == ["*"]


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
    """Cover lines 32, 332-343: row has no date, game_summary provides it."""
    fake_pid = 9991
    cache._cache.pop(f"last_n_games_{fake_pid}_1", None)
    cache._cache.pop(f"player_games_raw_{fake_pid}", None)

    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda: {fake_pid: [fake_pid, "Test Player C", None]},
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
    """Cover lines 354-355: no date from row or summary, matchup has YYYY-MM-DD prefix."""
    fake_pid = 9992
    cache._cache.pop(f"last_n_games_{fake_pid}_1", None)
    cache._cache.pop(f"player_games_raw_{fake_pid}", None)

    monkeypatch.setattr(
        "routes.players.load_players_dict",
        lambda: {fake_pid: [fake_pid, "Test Player D", None]},
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
    """Cover stats.py 331-346: get_cached_boxscore_v3 body on cache miss."""
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
    """Cover main.py 56: warning when EXECUTOR_WORKERS is out of range."""
    import helpers.common as _common
    import logging

    monkeypatch.setattr(_common, "_DEFAULT_WORKERS", 0)
    with caplog.at_level(logging.WARNING, logger="main"):
        with TestClient(app):
            pass
    assert "EXECUTOR_WORKERS" in caplog.text
    assert "outside reasonable range" in caplog.text


def test_lifespan_warns_invalid_timeout(monkeypatch, caplog):
    """Cover main.py 59: warning when STATS_TIMEOUT is less than 1."""
    import helpers.common as _common
    import logging

    monkeypatch.setattr(_common, "STATS_TIMEOUT", 0)
    with caplog.at_level(logging.WARNING, logger="main"):
        with TestClient(app):
            pass
    assert "STATS_TIMEOUT" in caplog.text
    assert "must be >= 1" in caplog.text


def test_lifespan_warns_missing_injuries_file(monkeypatch, caplog):
    """Cover main.py 62: warning when CBS injuries file is absent at startup."""
    import logging

    monkeypatch.setattr("main.os.path.exists", lambda _: False)
    with caplog.at_level(logging.WARNING, logger="main"):
        with TestClient(app):
            pass
    assert "CBS injuries file not found" in caplog.text


def test_security_headers_soccer_route(client):
    """Cover security.py: /soccer route gets STATIC_CSP."""
    r = client.get("/soccer")
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    assert "site.api.espn.com" in csp
    assert "connect-src" in csp
    assert "sports.core.api.espn.com" in csp


def test_security_headers_page_route(client):
    """Cover security.py: non-API, non-soccer routes get PAGE_CSP."""
    # Any non-/api/, non-/soccer path hits the else branch
    r = client.get("/not-an-api-route")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "fonts.googleapis.com" in csp  # PAGE_CSP includes Google Fonts
