import duckdb

from loaders.bronze import load_to_bronze

HEADER = ["Game Title", "Global", "Japan", "source", "as of"]


def make_row(title, source="src_a", as_of="2024-03-31"):
    return [title, "1.00", "0.50", source, as_of]


# --- load_to_bronze ---

def test_empty_rows_returns_zero(tmp_path):
    result = load_to_bronze("test_table", HEADER, [], db_path=tmp_path / "test.duckdb")
    assert result == 0


def test_inserts_new_rows_returns_count(tmp_path):
    rows = [make_row("Mario Kart 8"), make_row("Zelda BOTW")]
    result = load_to_bronze("test_table", HEADER, rows, db_path=tmp_path / "test.duckdb")
    assert result == 2


def test_duplicate_second_call_returns_zero(tmp_path):
    db = tmp_path / "test.duckdb"
    rows = [make_row("Mario Kart 8")]
    load_to_bronze("test_table", HEADER, rows, db_path=db)
    result = load_to_bronze("test_table", HEADER, rows, db_path=db)
    assert result == 0


def test_partial_duplicate_only_new_inserted(tmp_path):
    db = tmp_path / "test.duckdb"
    old = [make_row("Mario Kart 8")]
    new = [make_row("Zelda BOTW")]
    load_to_bronze("test_table", HEADER, old, db_path=db)
    result = load_to_bronze("test_table", HEADER, old + new, db_path=db)
    assert result == 1


def test_different_source_is_not_duplicate(tmp_path):
    db = tmp_path / "test.duckdb"
    row_a = [make_row("Mario Kart 8", source="src_a")]
    row_b = [make_row("Mario Kart 8", source="src_b")]
    r1 = load_to_bronze("test_table", HEADER, row_a, db_path=db)
    r2 = load_to_bronze("test_table", HEADER, row_b, db_path=db)
    assert r1 == 1
    assert r2 == 1


def test_different_as_of_is_not_duplicate(tmp_path):
    db = tmp_path / "test.duckdb"
    row_a = [make_row("Mario Kart 8", as_of="2024-03-31")]
    row_b = [make_row("Mario Kart 8", as_of="2024-09-30")]
    r1 = load_to_bronze("test_table", HEADER, row_a, db_path=db)
    r2 = load_to_bronze("test_table", HEADER, row_b, db_path=db)
    assert r1 == 1
    assert r2 == 1


def test_bronze_schema_created(tmp_path):
    db = tmp_path / "test.duckdb"
    load_to_bronze("test_table", HEADER, [make_row("Mario")], db_path=db)
    con = duckdb.connect(str(db))
    schemas = [r[0] for r in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()]
    con.close()
    assert "bronze" in schemas


def test_table_has_all_header_columns(tmp_path):
    db = tmp_path / "test.duckdb"
    load_to_bronze("test_table", HEADER, [make_row("Mario")], db_path=db)
    con = duckdb.connect(str(db))
    cols = [r[0] for r in con.execute("DESCRIBE bronze.test_table").fetchall()]
    con.close()
    assert all(col in cols for col in HEADER)
    assert "ingested_at" in cols


def test_rows_actually_stored_in_db(tmp_path):
    db = tmp_path / "test.duckdb"
    rows = [make_row("Mario Kart 8"), make_row("Zelda BOTW"), make_row("Splatoon 3")]
    inserted = load_to_bronze("test_table", HEADER, rows, db_path=db)
    con = duckdb.connect(str(db))
    count = con.execute("SELECT COUNT(*) FROM bronze.test_table").fetchone()[0]
    con.close()
    assert count == inserted == 3


def test_two_tables_are_independent(tmp_path):
    db = tmp_path / "test.duckdb"
    r1 = load_to_bronze("table_a", HEADER, [make_row("Mario")], db_path=db)
    r2 = load_to_bronze("table_b", HEADER, [make_row("Mario")], db_path=db)
    assert r1 == 1
    assert r2 == 1
