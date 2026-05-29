from pathlib import Path

from extractors.million_sellers import (
    _add_system_column,
    _detect_platform,
    _expand_rows,
    _is_old_format,
    _looks_like_number,
    _merge_continuation_rows,
    _normalize_text,
    _parse_data_line,
    _parse_date_from_filename,
    _parse_fy,
    _parse_rows_from_text,
)


# --- _normalize_text ---

def test_normalize_text_fixes_repeated_chars():
    assert _normalize_text("NNNNiiiinnnntttteeee") == "Ninte"

def test_normalize_text_leaves_normal_text_unchanged():
    assert _normalize_text("Nintendo Switch") == "Nintendo Switch"

def test_normalize_text_empty_string():
    assert _normalize_text("") == ""


# --- _parse_fy ---

def test_parse_fy_simple():
    assert _parse_fy("FY24") == "FY24"

def test_parse_fy_with_quarter():
    assert _parse_fy("FY24/Q2") == "FY24"

def test_parse_fy_strips_trailing_text():
    assert _parse_fy("FY24/Q2 Results") == "FY24"

def test_parse_fy_no_match_returns_original():
    assert _parse_fy("some text") == "some text"


# --- _looks_like_number ---

def test_looks_like_number_integer():
    assert _looks_like_number("1250") is True

def test_looks_like_number_with_comma():
    assert _looks_like_number("1,250") is True

def test_looks_like_number_dash():
    assert _looks_like_number("-") is True

def test_looks_like_number_text():
    assert _looks_like_number("abc") is False

def test_looks_like_number_empty():
    assert _looks_like_number("") is False


# --- _detect_platform ---

def test_detect_platform_exact_match():
    assert _detect_platform("Nintendo Switch") == "Nintendo Switch"

def test_detect_platform_with_suffix():
    assert _detect_platform("Nintendo Switch 2 titles") == "Nintendo Switch 2"

def test_detect_platform_switch2_preferred_over_switch():
    assert _detect_platform("Nintendo Switch 2") == "Nintendo Switch 2"

def test_detect_platform_no_match():
    assert _detect_platform("PlayStation 5") is None

def test_detect_platform_partial_no_match():
    assert _detect_platform("Nintendo") is None


# --- _parse_data_line ---

def test_parse_data_line_valid():
    result = _parse_data_line("Mario Kart 8 Deluxe 6,290 840 5,450 72,070")
    assert result == ("Mario Kart 8 Deluxe", "6,290", "840", "5,450", "72,070")

def test_parse_data_line_dash_as_number():
    result = _parse_data_line("Splatoon 3 500 - 500 2,000")
    assert result == ("Splatoon 3", "500", "-", "500", "2,000")

def test_parse_data_line_too_short():
    assert _parse_data_line("Mario 100 200") is None

def test_parse_data_line_non_numeric_suffix():
    assert _parse_data_line("Some Game 100 200 300 title") is None


# --- _is_old_format ---

def test_is_old_format_true_for_4_columns():
    assert _is_old_format([["a", "b", "c", "d"]]) is True

def test_is_old_format_false_for_5_columns():
    assert _is_old_format([["a", "b", "c", "d", "e"]]) is False

def test_is_old_format_empty():
    assert _is_old_format([]) is False


# --- _expand_rows ---

def test_expand_rows_no_linebreaks():
    table = [["Mario Kart", "6,290", "840", "5,450", "72,070"]]
    assert _expand_rows(table) == [["Mario Kart", "6,290", "840", "5,450", "72,070"]]

def test_expand_rows_splits_multiline_cell():
    table = [["Game A\nGame B", "100\n200", "-\n-", "-\n-", "-\n-"]]
    result = _expand_rows(table)
    assert result == [
        ["Game A", "100", "-", "-", "-"],
        ["Game B", "200", "-", "-", "-"],
    ]

def test_expand_rows_handles_none_cells():
    table = [[None, "100", None, None, None]]
    result = _expand_rows(table)
    assert result == [["", "100", "", "", ""]]

def test_expand_rows_skips_empty_rows():
    table = [["", "", "", "", ""], ["Mario", "1", "2", "3", "4"]]
    result = _expand_rows(table)
    assert result == [["Mario", "1", "2", "3", "4"]]


# --- _merge_continuation_rows ---

def test_merge_continuation_rows_multiline_title():
    rows = [
        ["The Legend of Zelda", "1,000", "200", "800", "5,000"],
        ["Tears of the Kingdom", "", "", "", ""],
    ]
    result = _merge_continuation_rows(rows)
    assert len(result) == 1
    assert result[0][0] == "The Legend of Zelda Tears of the Kingdom"

def test_merge_continuation_rows_independent_rows():
    rows = [
        ["Mario Kart 8", "6,290", "840", "5,450", "72,070"],
        ["Splatoon 3", "500", "100", "400", "2,000"],
    ]
    result = _merge_continuation_rows(rows)
    assert len(result) == 2

def test_merge_continuation_rows_preserves_numbers():
    rows = [
        ["Animal Crossing", "1,000", "200", "800", "5,000"],
        ["New Horizons", "", "", "", ""],
    ]
    result = _merge_continuation_rows(rows)
    assert result[0][1] == "1,000"


# --- _parse_date_from_filename ---

def test_parse_date_from_filename():
    path = Path("240115_results.pdf")
    assert _parse_date_from_filename(path) == "2024-01-15"

def test_parse_date_from_filename_older_year():
    path = Path("160430_results.pdf")
    assert _parse_date_from_filename(path) == "2016-04-30"


# --- _add_system_column ---

def test_add_system_column_basic():
    rows = [
        ["Game Title", "Global", "Japan", "Outside of Japan", "Life-to-date Global"],
        ["Nintendo Switch", "FY24", "-", "-", "-"],
        ["Mario Kart 8 Deluxe", "6,290", "840", "5,450", "72,070"],
    ]
    result = _add_system_column(rows)
    assert result[2][-2] == "Nintendo Switch"
    assert result[2][-1] == "FY24"

def test_add_system_column_header_row_appended():
    rows = [["Game Title", "Global", "Japan", "Outside of Japan", "Life-to-date Global"]]
    result = _add_system_column(rows)
    assert result[0][-2] == "system"
    assert result[0][-1] == "Fiscal Year"

def test_add_system_column_switches_platform():
    rows = [
        ["Game Title", "Global", "Japan", "Outside of Japan", "Life-to-date Global"],
        ["Nintendo Switch", "FY24", "-", "-", "-"],
        ["Mario Kart 8 Deluxe", "6,290", "840", "5,450", "72,070"],
        ["Nintendo Switch 2", "FY25", "-", "-", "-"],
        ["Mario Kart World", "1,000", "200", "800", "1,000"],
    ]
    result = _add_system_column(rows)
    assert result[2][-2] == "Nintendo Switch"
    assert result[4][-2] == "Nintendo Switch 2"


# --- _parse_rows_from_text ---

def test_parse_rows_from_text_extracts_games():
    text = "FY24/Q2\nMario Kart 8 Deluxe 6,290 840 5,450 72,070\nSplatoon 3 500 100 400 2,000"
    rows = _parse_rows_from_text(text, "2024-01-15", "report.pdf")
    assert len(rows) == 2
    assert rows[0][0] == "Mario Kart 8 Deluxe"
    assert rows[0][1] == "6,290"

def test_parse_rows_from_text_detects_platform_switch():
    text = "FY24\nNintendo Switch\nMario Kart 8 Deluxe 6,290 840 5,450 72,070"
    rows = _parse_rows_from_text(text, "2024-01-15", "report.pdf")
    assert rows[0][5] == "Nintendo Switch"

def test_parse_rows_from_text_metadata():
    text = "FY24\nMario Kart 8 Deluxe 6,290 840 5,450 72,070"
    rows = _parse_rows_from_text(text, "2024-01-15", "report.pdf")
    assert rows[0][7] == "2024-01-15"
    assert rows[0][8] == "report.pdf"

def test_parse_rows_from_text_empty():
    rows = _parse_rows_from_text("No games here", "2024-01-15", "report.pdf")
    assert rows == []
