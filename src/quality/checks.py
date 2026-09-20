import duckdb

EXPECTED_COLUMN_COUNT = 9

KNOWN_PLATFORMS = {
    "Nintendo Switch",
    "Nintendo Switch 2",
    "Nintendo 3DS",
    "Wii U",
    "Nintendo DS",
    "Wii",
    "Game Boy Advance",
    "Nintendo GameCube",
}


def check_extraction_results(rows: list[list]) -> list[str]:
    """Check raw extracted rows for structural integrity. Returns list of warning strings."""
    warnings = []
    if not rows:
        warnings.append("Extraction returned 0 rows")
        return warnings
    for i, row in enumerate(rows):
        if len(row) != EXPECTED_COLUMN_COUNT:
            warnings.append(f"Row {i}: expected {EXPECTED_COLUMN_COUNT} columns, got {len(row)}")
            continue
        if not row[0]:
            warnings.append(f"Row {i}: empty Game Title")
        if not row[5]:
            warnings.append(f"Row {i}: empty system (platform)")
        if not row[8]:
            warnings.append(f"Row {i}: empty source")
    return warnings


def check_silver_data(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """Check silver.stg_million_sellers for data quality issues. Returns list of warning strings."""
    warnings = []

    count = conn.execute(
        "SELECT COUNT(*) FROM silver.stg_million_sellers"
        " WHERE game_title IS NULL OR TRIM(game_title) = ''"
    ).fetchone()[0]
    if count:
        warnings.append(f"{count} rows with NULL or empty game_title")

    count = conn.execute(
        "SELECT COUNT(*) FROM silver.stg_million_sellers"
        " WHERE global_sales < 0 OR japan_sales < 0"
        " OR outside_japan_sales < 0 OR ltd_global_sales < 0"
    ).fetchone()[0]
    if count:
        warnings.append(f"{count} rows with negative sales values")

    count = conn.execute(
        "SELECT COUNT(*) FROM silver.stg_million_sellers"
        " WHERE ltd_global_sales < global_sales"
    ).fetchone()[0]
    if count:
        warnings.append(f"{count} rows where ltd_global_sales < global_sales")

    placeholders = ", ".join("?" * len(KNOWN_PLATFORMS))
    unknown = conn.execute(
        f"SELECT DISTINCT platform_name FROM silver.stg_million_sellers"
        f" WHERE platform_name NOT IN ({placeholders})",
        list(KNOWN_PLATFORMS),
    ).fetchall()
    for (platform,) in unknown:
        warnings.append(f"Unknown platform: '{platform}'")

    return warnings
