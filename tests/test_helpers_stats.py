"""Unit tests for helpers/stats.py pure functions."""
from datetime import date, datetime as real_datetime, timedelta
from unittest.mock import patch


from helpers.stats import (
    convert_et_to_cet,
    fix_encoding,
    get_date_str,
    get_display_date,
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
# get_date_str
# ---------------------------------------------------------------------------

class TestGetDateStr:
    def test_today_format(self):
        result = get_date_str(0)
        today = date.today().strftime("%Y-%m-%d")
        assert result == today

    def test_yesterday(self):
        expected = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert get_date_str(1) == expected

    def test_seven_days_ago(self):
        expected = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        assert get_date_str(7) == expected

    def test_parts_count(self):
        parts = get_date_str(0).split("-")
        assert len(parts) == 3

    def test_year_length(self):
        assert len(get_date_str(0).split("-")[0]) == 4

    def test_month_zero_padded(self):
        # Month must always be 2 digits
        assert len(get_date_str(0).split("-")[1]) == 2

    def test_day_zero_padded(self):
        # Day must always be 2 digits
        assert len(get_date_str(0).split("-")[2]) == 2


# ---------------------------------------------------------------------------
# get_display_date
# ---------------------------------------------------------------------------

class TestGetDisplayDate:
    def test_today_format(self):
        expected = date.today().strftime("%B %d, %Y")
        assert get_display_date(0) == expected

    def test_yesterday(self):
        expected = (date.today() - timedelta(days=1)).strftime("%B %d, %Y")
        assert get_display_date(1) == expected

    def test_contains_comma(self):
        assert "," in get_display_date(0)

    def test_contains_space(self):
        assert " " in get_display_date(0)

    def test_ends_with_year(self):
        result = get_display_date(0)
        assert result.endswith(str(date.today().year))

    def test_month_name_is_alpha(self):
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
