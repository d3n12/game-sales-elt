import duckdb
import pandas as pd
import pytest

from transformers.silver import (
    _normalize_fiscal_year,
    _normalize_title,
    _to_units,
    transform_to_silver,
)

BRONZE_HEADER = [
    "Game Title", "Global", "Japan", "Outside of Japan",
    "Life-to-date Global", "system", "Fiscal Year", "as of", "source",
]


def make_bronze_row(
    title="Mario Kart 8",
    global_="1,250",
    japan="500",
    outside_japan="750",
    ltd="5,000",
    system="Nintendo Switch",
    fiscal_year="FY24",
    as_of="2024-03-31",
    source="test_src",
):
    return [title, global_, japan, outside_japan, ltd, system, fiscal_year, as_of, source]


@pytest.fixture
def conn():
    """In-memory DuckDB connection with bronze schema and a pre-populated table."""
    col_defs = ", ".join(f'"{col}" VARCHAR' for col in BRONZE_HEADER)
    c = duckdb.connect()
    c.execute("CREATE SCHEMA bronze")
    c.execute(f"CREATE TABLE bronze.raw_million_sellers ({col_defs})")
    yield c
    c.close()


def _insert(conn, rows):
    conn.executemany(
        f"INSERT INTO bronze.raw_million_sellers VALUES ({', '.join(['?'] * len(BRONZE_HEADER))})",
        rows,
    )


# ---------------------------------------------------------------------------
# _normalize_fiscal_year
# ---------------------------------------------------------------------------

def test_normalize_fiscal_year_core_case():
    # "FY3/20" ? the literal string "FY3/20" is replaced by "FY"
    assert _normalize_fiscal_year("FY3/20") == "FY"


def test_normalize_fiscal_year_longer_suffix():
    # "FY3/2020" ? "FY3/20" is replaced by "FY", trailing "20" remains ? "FY20"
    assert _normalize_fiscal_year("FY3/2020") == "FY20"


def test_normalize_fiscal_year_no_match_unchanged():
    assert _normalize_fiscal_year("FY24") == "FY24"


# ---------------------------------------------------------------------------
# _normalize_title
# ---------------------------------------------------------------------------

def test_normalize_title_typical():
    assert _normalize_title("mario kart 8") == "Mario Kart 8"


def test_normalize_title_smart_apostrophe():
    assert _normalize_title("mario\u2019s") == "Mario's"


def test_normalize_title_unicode_apostrophe():
    assert _normalize_title("mario\u02bcs") == "Mario's"


def test_normalize_title_en_dash_removed():
    assert _normalize_title("splatoon\u20133") == "Splatoon3"


def test_normalize_title_slash_no_spaces():
    assert _normalize_title("mario/luigi") == "Mario / Luigi"


def test_normalize_title_slash_extra_spaces():
    assert _normalize_title("a  /  b") == "A / B"


# ---------------------------------------------------------------------------
# _to_units
# ---------------------------------------------------------------------------

def test_to_units_comma_number():
    result = _to_units(pd.Series(["1,250"]))
    assert result.iloc[0] == 12_500_000


def test_to_units_zero():
    result = _to_units(pd.Series(["0"]))
    assert result.iloc[0] == 0


def test_to_units_dash_becomes_zero():
    result = _to_units(pd.Series(["-"]))
    assert result.iloc[0] == 0


def test_to_units_empty_string_becomes_zero():
    result = _to_units(pd.Series([""]))
    assert result.iloc[0] == 0


# ---------------------------------------------------------------------------
# transform_to_silver (integration)
# ---------------------------------------------------------------------------

def test_transform_returns_row_count(conn):
    _insert(conn, [make_bronze_row(), make_bronze_row(title="Zelda BOTW")])
    assert transform_to_silver(conn) == 2


def test_transform_filters_empty_title(conn):
    _insert(conn, [make_bronze_row(), make_bronze_row(title=""), make_bronze_row(title="-")])
    assert transform_to_silver(conn) == 1


def test_transform_filters_null_title(conn):
    _insert(conn, [make_bronze_row(), make_bronze_row(title=None)])
    assert transform_to_silver(conn) == 1


def test_transform_creates_silver_table(conn):
    _insert(conn, [make_bronze_row()])
    transform_to_silver(conn)
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'silver'"
    ).fetchall()
    assert any("stg_million_sellers" in t for t in tables)


def test_transform_output_columns(conn):
    _insert(conn, [make_bronze_row()])
    transform_to_silver(conn)
    cols = [col[0] for col in conn.execute("DESCRIBE silver.stg_million_sellers").fetchall()]
    expected = [
        "game_title", "platform_name", "fiscal_year", "snapshot_date",
        "global_sales", "japan_sales", "outside_japan_sales", "ltd_global_sales", "source",
    ]
    assert cols == expected


def test_transform_values_normalized(conn):
    _insert(conn, [make_bronze_row(
        title="mario kart 8",
        global_="1,250",
        system="Nintendo Switch",
        fiscal_year="FY3/2020",  # FY3/20 -> FY, remainder 20 appended -> FY20
    )])
    transform_to_silver(conn)
    row = conn.execute("SELECT * FROM silver.stg_million_sellers").fetchone()
    game_title, platform_name, fiscal_year, _, global_sales, *_ = row
    assert game_title == "Mario Kart 8"
    assert platform_name == "Nintendo Switch"
    assert fiscal_year == "FY20"
    assert global_sales == 12_500_000


def test_transform_invalid_date_becomes_null(conn):
    _insert(conn, [make_bronze_row(as_of="not-a-date")])
    transform_to_silver(conn)
    snapshot = conn.execute("SELECT snapshot_date FROM silver.stg_million_sellers").fetchone()[0]
    assert snapshot is None
