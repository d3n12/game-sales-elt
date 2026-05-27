from pathlib import Path
import duckdb

DB_PATH = Path(__file__).parent.parent / "nintendo_sales.duckdb"


def load_to_bronze(
    table_name: str,
    header: list[str],
    rows: list[list[str]],
    db_path: Path = DB_PATH,
) -> int:
    """Load rows into bronze.<table_name>. Returns the number of newly inserted rows.

    Duplicate detection via (source, <first column>, as_of) — requires
    'source' and 'as_of' to be present in header.
    """
    if not rows:
        return 0

    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    col_defs = ", ".join(f'"{col}" VARCHAR' for col in header)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS bronze.{table_name} (
            {col_defs},
            ingested_at TIMESTAMP DEFAULT current_timestamp
        )
    """)

    first_col = header[0]
    source_idx = header.index("source")
    as_of_idx = header.index("as of")

    existing = set(
        con.execute(
            f'SELECT "{first_col}", source, "as of" FROM bronze.{table_name}'
        ).fetchall()
    )

    new_rows = [
        r for r in rows
        if (r[0], r[source_idx], r[as_of_idx]) not in existing
    ]

    if new_rows:
        placeholders = ", ".join(["?"] * len(header))
        cols = ", ".join(f'"{c}"' for c in header)
        con.executemany(
            f"INSERT INTO bronze.{table_name} ({cols}) VALUES ({placeholders})",
            new_rows,
        )

    con.close()
    return len(new_rows)
