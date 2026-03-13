"""Unit tests for helpers/stats.py pure functions."""

from datetime import date
from datetime import datetime as real_datetime
from unittest.mock import MagicMock, patch

import pytest
from helpers.common import cache
from helpers.stats import (
    convert_et_to_cet,
    fetch_single_boxscore,
    fix_encoding,
    get_display_date,
    get_games_leaders_list,
    get_games_list,
    reformat_player_minutes,
)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


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

WINTER_NOW = real_datetime(2026, 1, 15, 12, 0, 0)


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
        assert _cet("7:00 pm") == "19:00 CET"

    def test_1pm_et_winter(self):
        # 13:00 EST → 19:00 CET
        assert _cet("1:00 pm") == "13:00 CET"

    def test_midnight_am_et_winter(self):
        # 12:00 am = 00:00 EST → 06:00 CET
        assert _cet("12:00 am") == "00:00 CET"

    def test_noon_pm_et_winter(self):
        # 12:00 pm = 12:00 EST → 18:00 CET
        assert _cet("12:00 pm") == "12:00 CET"

    def test_630pm_et_winter(self):
        # 18:30 EST → 00:30 CET
        assert _cet("6:30 pm") == "18:30 CET"

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


def _team_row(
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
    """boxscore team_stats row matching the column indices used in stats.py.

    Length 26 so that row[-2] == row[24] == score.
    """
    row = [None] * 26
    row[1] = team_id
    row[2] = city
    row[3] = name
    row[7] = fgm
    row[8] = fga
    row[9] = fg_pct
    row[10] = tpm
    row[11] = tpa
    row[12] = tp_pct
    row[13] = ftm
    row[14] = fta
    row[15] = ft_pct
    row[16] = off_reb
    row[18] = reb
    row[19] = ast
    row[20] = stl
    row[21] = blk
    row[22] = to
    row[23] = fouls
    row[24] = score  # team[-2]
    return row


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
        with patch(
            "helpers.stats.scoreboardv3.ScoreboardV3", side_effect=Exception("network")
        ):
            with patch("helpers.stats.log_exceptions"):
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
        with patch(
            "helpers.stats.scoreboardv3.ScoreboardV3", side_effect=Exception("timeout")
        ):
            with patch("helpers.stats.log_exceptions"):
                assert get_games_leaders_list(1) == {}

    def test_returns_dict_type(self):
        result = self._call([], [])
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# fetch_single_boxscore
# ---------------------------------------------------------------------------


class TestFetchSingleBoxscore:
    _TEAM_A = _team_row(
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
    _TEAM_B = _team_row(
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

    def _mock_bs(self, teams_data):
        bs = MagicMock()
        bs.team_stats.get_dict.return_value = {"data": teams_data}
        return bs

    def _call(self, leaders_data=None):
        bs = self._mock_bs([self._TEAM_A, self._TEAM_B])
        with patch(
            "helpers.stats.boxscoretraditionalv3.BoxScoreTraditionalV3", return_value=bs
        ):
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

    def test_returns_empty_dict_on_exception(self):
        with patch(
            "helpers.stats.boxscoretraditionalv3.BoxScoreTraditionalV3",
            side_effect=Exception("API error"),
        ):
            result = fetch_single_boxscore("0022300001", [])
        assert result == {}


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
# load_players_file stale-while-error
# ---------------------------------------------------------------------------


class TestLoadPlayersFile:
    def test_uses_stale_cache_on_error(self):
        import helpers.stats as hs

        with patch("helpers.stats._fetch_players") as fetch_mock:
            fetch_mock.side_effect = [[[1, "Player One", 1]], RuntimeError("boom")]
            first = hs.load_players_file()
            second = hs.load_players_file()
        assert first == [[1, "Player One", 1]]
        assert second == [[1, "Player One", 1]]
