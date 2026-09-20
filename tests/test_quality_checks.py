import duckdb
import pytest

from quality.checks import check_extraction_results, check_silver_data

VALID_ROW = ["Mario Kart 8", "1,250", "500", "750", "5,000", "Nintendo Switch", "FY24", "2024-03-31", "test.pdf"]

SILVER_DDL = """
    CREATE SCHEMA silver;
    CREATE TABLE silver.stg_million_sellers (
        game_title VARCHAR,
        platform_name VARCHAR,
        fiscal_year VARCHAR,
        snapshot_date DATE,
        global_sales BIGINT,
        japan_sales BIGINT,
        outside_japan_sales BIGINT,
        ltd_global_sales BIGINT
    )
"""


@pytest.fixture
def silver_conn():
    conn = duckdb.connect()
    conn.execute(SILVER_DDL)
    yield conn
    conn.close()


def _insert_silver(conn, rows):
    conn.executemany(
        "INSERT INTO silver.stg_million_sellers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def valid_silver_row(**overrides):
    defaults = {
        "game_title": "Mario Kart 8",
        "platform_name": "Nintendo Switch",
        "fiscal_year": "FY24",
        "snapshot_date": "2024-03-31",
        "global_sales": 12500000,
        "japan_sales": 5000000,
        "outside_japan_sales": 7500000,
        "ltd_global_sales": 60000000,
    }
    defaults.update(overrides)
    return list(defaults.values())


# ---------------------------------------------------------------------------
# check_extraction_results
# ---------------------------------------------------------------------------

def test_extraction_empty_rows():
    assert check_extraction_results([]) == ["Extraction returned 0 rows"]


def test_extraction_valid_rows():
    assert check_extraction_results([VALID_ROW, VALID_ROW]) == []


def test_extraction_wrong_column_count():
    short_row = VALID_ROW[:7]
    warnings = check_extraction_results([short_row])
    assert len(warnings) == 1
    assert "expected 9 columns, got 7" in warnings[0]


def test_extraction_empty_game_title():
    row = VALID_ROW[:]
    row[0] = ""
    warnings = check_extraction_results([row])
    assert any("Game Title" in w for w in warnings)


def test_extraction_empty_system():
    row = VALID_ROW[:]
    row[5] = ""
    warnings = check_extraction_results([row])
    assert any("system" in w for w in warnings)


def test_extraction_empty_source():
    row = VALID_ROW[:]
    row[8] = ""
    warnings = check_extraction_results([row])
    assert any("source" in w for w in warnings)


def test_extraction_multiple_issues():
    bad_row = ["", "1,250", "500", "750", "5,000", "", "FY24", "2024-03-31", ""]
    warnings = check_extraction_results([bad_row])
    assert len(warnings) == 3


# ---------------------------------------------------------------------------
# check_silver_data
# ---------------------------------------------------------------------------

def test_silver_valid_data(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row()])
    assert check_silver_data(silver_conn) == []


def test_silver_null_game_title(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(game_title=None)])
    warnings = check_silver_data(silver_conn)
    assert any("game_title" in w for w in warnings)


def test_silver_empty_game_title(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(game_title="   ")])
    warnings = check_silver_data(silver_conn)
    assert any("game_title" in w for w in warnings)


def test_silver_negative_global_sales(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(global_sales=-100)])
    warnings = check_silver_data(silver_conn)
    assert any("negative" in w for w in warnings)


def test_silver_negative_japan_sales(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(japan_sales=-1)])
    warnings = check_silver_data(silver_conn)
    assert any("negative" in w for w in warnings)


def test_silver_ltd_less_than_global(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(global_sales=5000000, ltd_global_sales=1000000)])
    warnings = check_silver_data(silver_conn)
    assert any("ltd_global_sales < global_sales" in w for w in warnings)


def test_silver_unknown_platform(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(platform_name="PlayStation 5")])
    warnings = check_silver_data(silver_conn)
    assert any("PlayStation 5" in w for w in warnings)


def test_silver_known_platform_no_warning(silver_conn):
    for platform in ["Nintendo Switch", "Nintendo Switch 2", "Nintendo 3DS", "Wii U", "Nintendo DS", "Wii", "Game Boy Advance"]:
        conn = duckdb.connect()
        conn.execute(SILVER_DDL)
        _insert_silver(conn, [valid_silver_row(platform_name=platform)])
        warnings = check_silver_data(conn)
        assert not any("Unknown platform" in w for w in warnings), f"False positive for '{platform}'"
        conn.close()


def test_silver_zero_sales_no_plausibility_warning(silver_conn):
    _insert_silver(silver_conn, [valid_silver_row(global_sales=0, ltd_global_sales=0)])
    warnings = check_silver_data(silver_conn)
    assert not any("ltd_global_sales < global_sales" in w for w in warnings)


def test_silver_ltd_zero_while_global_positive_flagged(silver_conn):
    # Regression: a parse error (e.g. an unstripped footnote marker) can coerce
    # ltd_global_sales to 0 while global_sales is genuinely positive - must not
    # be silently treated as a legitimate "no data yet" case.
    _insert_silver(silver_conn, [valid_silver_row(global_sales=7940000, ltd_global_sales=0)])
    warnings = check_silver_data(silver_conn)
    assert any("ltd_global_sales < global_sales" in w for w in warnings)
