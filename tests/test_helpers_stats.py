"""Unit tests for helpers/stats.py pure functions."""

from datetime import date
from datetime import datetime as real_datetime
from typing import ClassVar
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from helpers.stats import (
    convert_et_to_cet,
    fetch_single_boxscore,
    find_category_leaders,
    fix_encoding,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
    parse_iso_minutes,
    reformat_player_minutes,
)

# ---------------------------------------------------------------------------
# reformat_player_minutes
# ---------------------------------------------------------------------------


class TestReformatPlayerMinutes:
    def test_exact_minutes(self):
        assert reformat_player_minutes(1800) == "30:00"

    def test_minutes_and_seconds(self):
        assert reformat_player_minutes(1837) == "30:37"

    def test_zero(self):
        assert reformat_player_minutes(0) == "0:00"

    def test_seconds_only(self):
        assert reformat_player_minutes(45) == "0:45"

    def test_pads_single_digit_seconds(self):
        assert reformat_player_minutes(65) == "1:05"

    def test_full_nba_game(self):
        # 48 minutes
        assert reformat_player_minutes(2880) == "48:00"

    def test_overtime(self):
        # 53 minutes (48 + 5 OT)
        assert reformat_player_minutes(3180) == "53:00"

    def test_one_second(self):
        assert reformat_player_minutes(1) == "0:01"

    def test_59_seconds(self):
        assert reformat_player_minutes(59) == "0:59"

    def test_large_value(self):
        # 100 minutes 0 seconds
        assert reformat_player_minutes(6000) == "100:00"


# ---------------------------------------------------------------------------
# parse_iso_minutes (ISO-8601 duration → MM:SS; regex-based, no isodate)
# ---------------------------------------------------------------------------


class TestParseIsoMinutes:
    def test_minutes_and_seconds(self):
        assert parse_iso_minutes("PT30M37.00S") == "30:37"

    def test_seconds_only(self):
        assert parse_iso_minutes("PT37.00S") == "0:37"

    def test_truncates_fractional_seconds(self):
        assert parse_iso_minutes("PT12M45.99S") == "12:45"

    def test_minutes_only(self):
        assert parse_iso_minutes("PT5M") == "5:00"

    def test_malformed_returns_zero(self):
        assert parse_iso_minutes("garbage") == "0:00"

    def test_empty_returns_zero(self):
        assert parse_iso_minutes("") == "0:00"


# ---------------------------------------------------------------------------
# fix_encoding
# ---------------------------------------------------------------------------


class TestFixEncoding:
    def test_plain_ascii_unchanged(self):
        assert fix_encoding("LeBron James") == "LeBron James"

    def test_empty_string(self):
        assert fix_encoding("") == ""

    def test_mojibake_special_c_with_caron(self):
        # "Jokić" — ć is U+0107, encoded as UTF-8 bytes \xc4\x87,
        # which when mis-decoded as Latin-1 becomes "Ä‡"
        original = "Joki\u0107"
        mojibake = original.encode("utf-8").decode("latin-1")
        assert fix_encoding(mojibake) == original

    def test_mojibake_diacritics(self):
        # Luka Dončić — č is U+010D
        original = "Don\u010di\u0107"
        mojibake = original.encode("utf-8").decode("latin-1")
        assert fix_encoding(mojibake) == original

    def test_mojibake_accented_vowels(self):
        # é as in "André"
        original = "Andr\u00e9"
        mojibake = original.encode("utf-8").decode("latin-1")
        assert fix_encoding(mojibake) == original

    def test_already_correct_returns_original(self):
        # If the string is already valid UTF-8 text (no mojibake),
        # encoding to latin-1 may raise UnicodeEncodeError → returns original
        s = "Steph Curry"
        assert fix_encoding(s) == s

    def test_returns_original_on_unencodable(self):
        # Chinese characters cannot be encoded as iso-8859-1 → returns original
        s = "\u4e2d\u6587"
        assert fix_encoding(s) == s


# ---------------------------------------------------------------------------
# get_display_date
# ---------------------------------------------------------------------------

_FIXED_DATE = date(2026, 3, 7)


class TestGetDisplayDate:
    def _patch_today(self):
        return patch("helpers.stats._today_et", return_value=_FIXED_DATE)

    def test_today_format(self):
        with self._patch_today():
            assert get_display_date(0) == "March 07, 2026"

    def test_yesterday(self):
        with self._patch_today():
            assert get_display_date(1) == "March 06, 2026"

    def test_contains_comma(self):
        with self._patch_today():
            assert "," in get_display_date(0)

    def test_contains_space(self):
        with self._patch_today():
            assert " " in get_display_date(0)

    def test_ends_with_year(self):
        with self._patch_today():
            result = get_display_date(0)
        assert result.endswith("2026")

    def test_month_name_is_alpha(self):
        with self._patch_today():
            month_name = get_display_date(0).split(" ")[0]
        assert month_name.isalpha()


# ---------------------------------------------------------------------------
# convert_et_to_cet
# ---------------------------------------------------------------------------
# Pin datetime.now() to a fixed winter date (January 15 2026, EST active)
# so DST cannot affect results. Winter: EST=UTC-5, CET=UTC+1 → +6h offset.

WINTER_NOW = real_datetime(2026, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("US/Eastern"))


def _cet(time_str):
    """Call convert_et_to_cet with datetime.now() pinned to a winter date."""
    import helpers.stats as _stats_mod

    with patch.object(_stats_mod, "datetime") as mock_dt:
        mock_dt.now.return_value = WINTER_NOW
        return convert_et_to_cet(time_str)


class TestConvertETtoCET:
    def test_invalid_format_returns_original(self):
        assert convert_et_to_cet("TBD") == "TBD"

    def test_empty_string_returns_original(self):
        assert convert_et_to_cet("") == ""

    def test_final_status_returns_original(self):
        assert convert_et_to_cet("Final") == "Final"

    def test_valid_output_contains_cet(self):
        result = _cet("7:00 pm")
        assert "CET" in result

    def test_valid_output_format(self):
        # Must match HH:MM CET
        import re

        result = _cet("7:00 pm")
        assert re.match(r"\d{2}:\d{2} CET", result)

    # Winter offset: ET→CET = +6 hours
    def test_7pm_et_winter(self):
        # 19:00 EST → 01:00 CET (next day)
        assert _cet("7:00 pm") == "01:00 CET"

    def test_1pm_et_winter(self):
        # 13:00 EST → 19:00 CET
        assert _cet("1:00 pm") == "19:00 CET"

    def test_midnight_am_et_winter(self):
        # 12:00 am = 00:00 EST → 06:00 CET
        assert _cet("12:00 am") == "06:00 CET"

    def test_noon_pm_et_winter(self):
        # 12:00 pm = 12:00 EST → 18:00 CET
        assert _cet("12:00 pm") == "18:00 CET"

    def test_630pm_et_winter(self):
        # 18:30 EST → 00:30 CET
        assert _cet("6:30 pm") == "00:30 CET"

    def test_case_insensitive_am(self):
        assert _cet("10:00 AM") == _cet("10:00 am")

    def test_case_insensitive_pm(self):
        assert _cet("8:00 PM") == _cet("8:00 pm")

    def test_no_space_before_ampm(self):
        # regex allows optional whitespace between time and am/pm
        result = _cet("7:00pm")
        assert "CET" in result


# ---------------------------------------------------------------------------
# Helpers for API-backed functions
# ---------------------------------------------------------------------------


def _game_row(game_id, status):
    """Minimal game_header row: g[0]=game_id, g[2]=status."""
    row = [None] * 10
    row[0] = game_id
    row[2] = status
    return row


def _leader_row(game_id, team_id, player_name, pts, reb, ast):
    """game_leaders row at the indices stats.py reads."""
    row = [None] * 12
    row[0] = game_id
    row[1] = team_id
    row[4] = player_name
    row[9] = pts
    row[10] = reb
    row[11] = ast
    return row


def _team_dict(
    team_id,
    city,
    name,
    score,
    fgm=30,
    fga=80,
    fg_pct=0.375,
    tpm=10,
    tpa=30,
    tp_pct=0.333,
    ftm=15,
    fta=20,
    ft_pct=0.75,
    off_reb=10,
    reb=40,
    ast=20,
    stl=7,
    blk=3,
    to=10,
    fouls=18,
):
    """Live boxscore team dict matching the structure returned by get_cached_live_boxscore."""
    return {
        "teamId": team_id,
        "teamCity": city,
        "teamName": name,
        "score": score,
        "statistics": {
            "fieldGoalsMade": fgm,
            "fieldGoalsAttempted": fga,
            "fieldGoalsPercentage": fg_pct,
            "threePointersMade": tpm,
            "threePointersAttempted": tpa,
            "threePointersPercentage": tp_pct,
            "freeThrowsMade": ftm,
            "freeThrowsAttempted": fta,
            "freeThrowsPercentage": ft_pct,
            "reboundsOffensive": off_reb,
            "reboundsTotal": reb,
            "assists": ast,
            "steals": stl,
            "blocks": blk,
            "turnovers": to,
            "foulsPersonal": fouls,
        },
    }


def _scoreboard_mock(games_data, leaders_data=None):
    sb = MagicMock()
    sb.game_header.get_dict.return_value = {"data": games_data}
    if leaders_data is not None:
        sb.game_leaders.get_dict.return_value = {"data": leaders_data}
    return sb


# ---------------------------------------------------------------------------
# get_games_list
# ---------------------------------------------------------------------------


class TestGetGamesList:
    def _call(self, games_data, days_offset=1):
        sb = _scoreboard_mock(games_data)
        with patch("helpers.stats.scoreboardv3.ScoreboardV3", return_value=sb):
            return get_games_list(days_offset)

    def test_returns_game_ids_when_status_gt_1(self):
        result = self._call([_game_row("001", 2), _game_row("002", 3)])
        assert sorted(result) == ["001", "002"]

    def test_excludes_games_with_status_one(self):
        result = self._call([_game_row("001", 1)])
        assert result == []

    def test_excludes_games_with_status_zero(self):
        result = self._call([_game_row("001", 0)])
        assert result == []

    def test_mixed_statuses(self):
        result = self._call(
            [_game_row("001", 2), _game_row("002", 1), _game_row("003", 3)]
        )
        assert sorted(result) == ["001", "003"]

    def test_deduplicates_game_ids(self):
        result = self._call([_game_row("001", 2), _game_row("001", 2)])
        assert result == ["001"]

    def test_empty_games_returns_empty_list(self):
        assert self._call([]) == []

    def test_returns_empty_on_api_exception(self):
        with (
            patch(
                "helpers.stats.scoreboardv3.ScoreboardV3",
                side_effect=Exception("network"),
            ),
            patch("helpers.stats.log_exceptions"),
        ):
            assert get_games_list(1) == []

    def test_returns_list_type(self):
        result = self._call([_game_row("001", 2)])
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_games_leaders_list
# ---------------------------------------------------------------------------


class TestGetGamesLeadersList:
    def _call(self, games_data, leaders_data, days_offset=1):
        sb = _scoreboard_mock(games_data, leaders_data)
        with patch("helpers.stats.scoreboardv3.ScoreboardV3", return_value=sb):
            return get_games_leaders_list(days_offset)

    def test_returns_dict_with_game_id_keys(self):
        result = self._call([_game_row("001", 2)], [])
        assert "001" in result

    def test_excludes_games_with_status_lte_1(self):
        result = self._call([_game_row("001", 1)], [])
        assert "001" not in result

    def test_leader_data_mapped_to_correct_game(self):
        ld = _leader_row("001", 101, "Player A", 30, 10, 5)
        result = self._call([_game_row("001", 2)], [ld])
        assert result["001"] == [["Player A", 30, 10, 5, 101]]

    def test_leader_for_unknown_game_ignored(self):
        ld = _leader_row("999", 101, "Ghost Player", 20, 5, 3)
        result = self._call([_game_row("001", 2)], [ld])
        assert result["001"] == []

    def test_multiple_leaders_per_game(self):
        ld1 = _leader_row("001", 101, "Player A", 30, 10, 5)
        ld2 = _leader_row("001", 102, "Player B", 25, 8, 6)
        result = self._call([_game_row("001", 2)], [ld1, ld2])
        assert len(result["001"]) == 2

    def test_leaders_across_multiple_games(self):
        ld1 = _leader_row("001", 101, "Player A", 30, 10, 5)
        ld2 = _leader_row("002", 201, "Player B", 25, 8, 6)
        result = self._call(
            [_game_row("001", 2), _game_row("002", 2)],
            [ld1, ld2],
        )
        assert "001" in result and "002" in result

    def test_applies_fix_encoding_to_player_name(self):
        original = "Joki\u0107"
        mojibake = original.encode("utf-8").decode("latin-1")
        ld = _leader_row("001", 101, mojibake, 30, 10, 5)
        result = self._call([_game_row("001", 2)], [ld])
        assert result["001"][0][0] == original

    def test_returns_empty_dict_on_api_exception(self):
        with (
            patch(
                "helpers.stats.scoreboardv3.ScoreboardV3",
                side_effect=Exception("timeout"),
            ),
            patch("helpers.stats.log_exceptions"),
        ):
            assert get_games_leaders_list(1) == {}

    def test_returns_dict_type(self):
        result = self._call([], [])
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# fetch_single_boxscore
# ---------------------------------------------------------------------------


class TestFetchSingleBoxscore:
    _TEAM_A = _team_dict(
        101,
        "Los Angeles",
        "Lakers",
        110,
        fgm=40,
        fga=85,
        fg_pct=0.471,
        tpm=12,
        tpa=35,
        tp_pct=0.343,
        ftm=18,
        fta=22,
        ft_pct=0.818,
        off_reb=8,
        reb=42,
        ast=25,
        stl=9,
        blk=5,
        to=11,
        fouls=20,
    )
    _TEAM_B = _team_dict(
        202,
        "Golden State",
        "Warriors",
        105,
        fgm=38,
        fga=88,
        fg_pct=0.432,
        tpm=14,
        tpa=40,
        tp_pct=0.350,
        ftm=15,
        fta=18,
        ft_pct=0.833,
        off_reb=7,
        reb=38,
        ast=22,
        stl=8,
        blk=4,
        to=13,
        fouls=19,
    )

    def _mock_live_bs(self, home, away):
        return {"game": {"homeTeam": home, "awayTeam": away}}

    def _call(self, leaders_data=None):
        data = self._mock_live_bs(self._TEAM_A, self._TEAM_B)
        with patch("helpers.stats.get_cached_live_boxscore", return_value=data):
            return fetch_single_boxscore("0022300001", leaders_data or [])

    def test_returns_game_id(self):
        result = self._call()
        assert result["gameId"] == "0022300001"

    def test_returns_two_teams(self):
        result = self._call()
        assert len(result["teams"]) == 2

    def test_team_name_is_city_plus_nickname(self):
        result = self._call()
        assert result["teams"][0]["name"] == "Los Angeles Lakers"
        assert result["teams"][1]["name"] == "Golden State Warriors"

    def test_team_scores(self):
        result = self._call()
        assert result["teams"][0]["score"] == 110
        assert result["teams"][1]["score"] == 105

    def test_stats_fg_format(self):
        result = self._call()
        assert result["teams"][0]["stats"]["fg"] == "40/85"

    def test_stats_three_pt_format(self):
        result = self._call()
        assert result["teams"][0]["stats"]["threePt"] == "12/35"

    def test_stats_ft_format(self):
        result = self._call()
        assert result["teams"][0]["stats"]["ft"] == "18/22"

    def test_stats_percentages(self):
        stats = self._call()["teams"][0]["stats"]
        assert stats["fgPct"] == 0.471
        assert stats["threePtPct"] == 0.343
        assert stats["ftPct"] == 0.818

    def test_stats_counting_stats(self):
        stats = self._call()["teams"][0]["stats"]
        assert stats["rebounds"] == 42
        assert stats["offRebounds"] == 8
        assert stats["assists"] == 25
        assert stats["steals"] == 9
        assert stats["blocks"] == 5
        assert stats["turnovers"] == 11
        assert stats["fouls"] == 20

    def test_leader_matched_by_team_id(self):
        leaders = [["LeBron James", 35, 8, 7, 101]]
        result = self._call(leaders_data=leaders)
        laker_team = next(
            t for t in result["teams"] if t["name"] == "Los Angeles Lakers"
        )
        assert laker_team["leader"]["name"] == "LeBron James"
        assert laker_team["leader"]["points"] == 35

    def test_leader_not_matched_uses_defaults(self):
        result = self._call(leaders_data=[])
        assert result["teams"][0]["leader"] == {
            "name": "",
            "points": 0,
            "rebounds": 0,
            "assists": 0,
        }

    def test_leader_with_insufficient_length_skipped(self):
        # len(leader) <= 4 should be ignored
        leaders = [["Short", 10, 5, 3]]  # only 4 elements, index 4 missing
        result = self._call(leaders_data=leaders)
        assert result["teams"][0]["leader"]["name"] == ""

    def test_returns_none_on_exception(self):
        with patch(
            "helpers.stats.get_cached_live_boxscore",
            side_effect=Exception("API error"),
        ):
            result = fetch_single_boxscore("0022300001", [])
        assert result is None


# ---------------------------------------------------------------------------
# find_category_leaders
# ---------------------------------------------------------------------------


class TestFindCategoryLeaders:
    _CATS: ClassVar = [("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists")]

    def _item(self, name, pts, reb, ast):
        return {"name": name, "pts": pts, "reb": reb, "ast": ast}

    def test_single_leader(self):
        items = [self._item("A", 30, 5, 3), self._item("B", 20, 5, 8)]
        _, entries = find_category_leaders(items, self._CATS)
        assert entries["pts"] == [items[0]]
        assert entries["ast"] == [items[1]]

    def test_tied_leaders_both_included(self):
        items = [self._item("A", 25, 8, 5), self._item("B", 25, 6, 5)]
        _, entries = find_category_leaders(items, self._CATS)
        assert len(entries["pts"]) == 2
        assert len(entries["ast"]) == 2

    def test_all_zeros_returns_empty_leaders(self):
        """No leaders shown when all values are 0 (val != 0 guard)."""
        items = [self._item("A", 0, 0, 0), self._item("B", 0, 0, 0)]
        max_vals, entries = find_category_leaders(items, self._CATS)
        assert max_vals["pts"] == 0
        assert entries["pts"] == []

    def test_empty_items(self):
        max_vals, entries = find_category_leaders([], self._CATS)
        assert all(v == 0 for v in max_vals.values())
        assert all(v == [] for v in entries.values())

    def test_none_value_treated_as_zero(self):
        """item.get(key) or 0 coerces None to 0."""
        items = [{"name": "A", "pts": None, "reb": 10, "ast": 5}]
        max_vals, entries = find_category_leaders(items, self._CATS)
        assert max_vals["pts"] == 0
        assert entries["pts"] == []
        assert entries["reb"] == [items[0]]

    def test_max_vals_correct(self):
        items = [self._item("A", 40, 12, 8), self._item("B", 35, 15, 10)]
        max_vals, _ = find_category_leaders(items, self._CATS)
        assert max_vals["pts"] == 40
        assert max_vals["reb"] == 15
        assert max_vals["ast"] == 10

    def test_later_item_beats_earlier(self):
        items = [self._item("A", 20, 5, 5), self._item("B", 30, 5, 5)]
        _, entries = find_category_leaders(items, self._CATS)
        assert entries["pts"] == [items[1]]


# ---------------------------------------------------------------------------
# _today_et / scoreboard_date
# ---------------------------------------------------------------------------


class TestTodayEt:
    def test_returns_date_object(self):
        from helpers.stats import _today_et

        result = _today_et()
        assert isinstance(result, date)


class TestScoreboardDate:
    def test_before_13_cet_returns_yesterday(self):
        from helpers.stats import _TZ_CET, scoreboard_date

        morning = real_datetime(2026, 3, 8, 10, 0, tzinfo=_TZ_CET)
        with patch("helpers.stats.datetime") as mock_dt:
            mock_dt.now.return_value = morning
            result = scoreboard_date()
        assert result == date(2026, 3, 7)

    def test_after_13_cet_returns_today(self):
        from helpers.stats import _TZ_CET, scoreboard_date

        afternoon = real_datetime(2026, 3, 8, 14, 0, tzinfo=_TZ_CET)
        with patch("helpers.stats.datetime") as mock_dt:
            mock_dt.now.return_value = afternoon
            result = scoreboard_date()
        assert result == date(2026, 3, 8)

    def test_exactly_13_cet_returns_today(self):
        from helpers.stats import _TZ_CET, scoreboard_date

        exact = real_datetime(2026, 3, 8, 13, 0, tzinfo=_TZ_CET)
        with patch("helpers.stats.datetime") as mock_dt:
            mock_dt.now.return_value = exact
            result = scoreboard_date()
        assert result == date(2026, 3, 8)


# ---------------------------------------------------------------------------
# _parse_minutes
# ---------------------------------------------------------------------------


class TestParseMinutes:
    def test_valid_input(self):
        from helpers.stats import parse_minutes

        assert parse_minutes("32:15") == (32, 15)

    def test_malformed_returns_zero_tuple(self):
        from helpers.stats import parse_minutes

        assert parse_minutes("invalid") == (0, 0)
        assert parse_minutes("") == (0, 0)


# ---------------------------------------------------------------------------
# load_players_file stale-while-error
# ---------------------------------------------------------------------------


class TestLoadPlayersFile:
    def test_uses_stale_cache_on_error(self):
        import helpers.stats as hs

        with patch("helpers.stats._fetch_players") as fetch_mock:
            fetch_mock.side_effect = [[[1, "Player One", 1]], RuntimeError("boom")]
            first = hs.load_players_file()
            hs._players_cache_expires["00"] = 0  # expire cache to force second fetch
            second = hs.load_players_file()
        assert fetch_mock.call_count == 2
        assert first == [[1, "Player One", 1]]
        assert second == [[1, "Player One", 1]]


# ---------------------------------------------------------------------------
# _reset_nba_stats_http_session
# ---------------------------------------------------------------------------


class TestResetNbaStatsHttpSession:
    def test_closes_and_clears_the_shared_session(self):
        from nba_api.library.http import NBAHTTP
        from nba_api.stats.library.http import NBAStatsHTTP

        import helpers.stats as hs

        class FakeSession:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        live_sess, stats_sess = FakeSession(), FakeSession()
        NBAHTTP._session = live_sess
        NBAStatsHTTP._session = stats_sess
        try:
            hs._reset_nba_stats_http_session()
            assert live_sess.closed is True
            assert stats_sess.closed is True
            assert NBAHTTP._session is None
            assert NBAStatsHTTP._session is None
        finally:
            NBAHTTP._session = None
            NBAStatsHTTP._session = None


# ---------------------------------------------------------------------------
# Player side-caches
# ---------------------------------------------------------------------------


class TestPlayerSideCaches:
    def test_dict_and_lower_track_the_fetched_rows(self):
        import helpers.stats as hs

        rows = [[1, "Alpha One"], [2, "Beta Two"]]
        with patch("helpers.stats._fetch_players", return_value=rows) as fetch:
            assert hs.load_players_dict() == {1: rows[0], 2: rows[1]}
            assert hs.load_players_with_lower() == [
                (rows[0], "alpha one"),
                (rows[1], "beta two"),
            ]
        # second call is served from the 12h cache, not refetched
        fetch.assert_called_once()

    def test_side_caches_are_keyed_per_league(self):
        import helpers.stats as hs

        nba = [[1, "NBA Player"]]
        wnba = [[9, "WNBA Player"]]
        with patch(
            "helpers.stats._fetch_players",
            side_effect=lambda league_id="00": wnba if league_id == "10" else nba,
        ):
            assert hs.load_players_dict() == {1: nba[0]}
            assert hs.load_players_dict(league_id="10") == {9: wnba[0]}
            assert hs.load_players_with_lower(league_id="10") == [
                (wnba[0], "wnba player")
            ]


# ---------------------------------------------------------------------------
# get_cached_scoreboard
# ---------------------------------------------------------------------------


class TestGetCachedScoreboard:
    def test_nba_overrides_the_cdn_endpoint_url(self):
        import helpers.stats as hs
        from helpers.common import CACHE_TTL

        sb = MagicMock()
        sb.games.data = [{"gameId": "0022300001"}]
        with (
            patch("helpers.stats.live_scoreboard.ScoreBoard", return_value=sb),
            patch("helpers.stats.cache.set") as set_mock,
        ):
            out = hs.get_cached_scoreboard()
        assert out == [{"gameId": "0022300001"}]
        assert sb.endpoint_url == "scoreboard/todaysScoreboard_00.json"
        sb.get_request.assert_called_once()
        assert set_mock.call_args.args[2] == CACHE_TTL["scoreboard"]

    def test_wnba_goes_through_the_wnba_cdn_helper(self):
        import helpers.stats as hs

        with patch(
            "helpers.stats._fetch_wnba_live_scoreboard",
            return_value=[{"gameId": "1022600001"}],
        ) as fetch:
            out = hs.get_cached_scoreboard(league_id="10")
        assert out == [{"gameId": "1022600001"}]
        fetch.assert_called_once()

    def test_second_call_is_served_from_cache(self):
        import helpers.stats as hs

        with patch(
            "helpers.stats._fetch_wnba_live_scoreboard", return_value=[]
        ) as fetch:
            hs.get_cached_scoreboard(league_id="10")
            hs.get_cached_scoreboard(league_id="10")
        fetch.assert_called_once()

    def test_failure_resets_the_session_and_reraises(self):
        import helpers.stats as hs

        with (
            patch(
                "helpers.stats.live_scoreboard.ScoreBoard",
                side_effect=RuntimeError("cdn down"),
            ),
            patch("helpers.stats._reset_nba_stats_http_session") as reset,
            pytest.raises(RuntimeError),
        ):
            hs.get_cached_scoreboard()
        reset.assert_called()


# ---------------------------------------------------------------------------
# get_cached_live_boxscore — TTL depends on whether the game is final
# ---------------------------------------------------------------------------


class TestGetCachedLiveBoxscore:
    @staticmethod
    def _payload(status):
        return {"game": {"gameStatusText": status}}

    def _run(self, status):
        import helpers.stats as hs

        data = self._payload(status)
        box = MagicMock()
        box.return_value.get_dict.return_value = data
        with (
            patch("helpers.stats.live_boxscore.BoxScore", box),
            patch("helpers.stats.cache.set") as set_mock,
        ):
            out = hs.get_cached_live_boxscore("0022300001")
        assert out == data
        return set_mock.call_args.args[2]

    def test_final_game_gets_the_24h_ttl(self):
        from helpers.common import CACHE_TTL

        assert self._run("Final") == CACHE_TTL["historical"]

    def test_live_game_gets_the_short_ttl(self):
        from helpers.common import CACHE_TTL

        assert self._run("Q3 05:12") == CACHE_TTL["boxscores"]

    def test_second_call_is_served_from_cache(self):
        import helpers.stats as hs

        box = MagicMock()
        box.return_value.get_dict.return_value = self._payload("Final")
        with patch("helpers.stats.live_boxscore.BoxScore", box):
            hs.get_cached_live_boxscore("0022300001")
            hs.get_cached_live_boxscore("0022300001")
        box.assert_called_once()

    def test_wnba_goes_through_the_wnba_cdn_helper(self):
        import helpers.stats as hs

        with patch(
            "helpers.stats._fetch_wnba_live_boxscore",
            return_value=self._payload("Final"),
        ) as fetch:
            hs.get_cached_live_boxscore("1022600001", league_id="10")
        fetch.assert_called_once_with("1022600001")

    def test_failure_resets_the_session_and_reraises(self):
        import helpers.stats as hs

        with (
            patch(
                "helpers.stats.live_boxscore.BoxScore",
                side_effect=RuntimeError("cdn down"),
            ),
            patch("helpers.stats._reset_nba_stats_http_session") as reset,
            pytest.raises(RuntimeError),
        ):
            hs.get_cached_live_boxscore("0022300001")
        reset.assert_called()
