import re

import duckdb
import pandas as pd


def _normalize_fiscal_year(value: str) -> str:
    return value.replace("FY3/20", "FY")


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = title.replace("\u2019", "'").replace("\u02bc", "'")  # normalize apostrophes
    title = title.replace("\u2013", "")                          # remove en-dash
    title = re.sub(r"\s*/\s*", " / ", title)                    # normalize slashes
    return " ".join(w.capitalize() for w in title.split())


def _to_units(series: pd.Series) -> pd.Series:
    return (
        pd.to_numeric(series.str.replace(",", "", regex=False), errors="coerce")
        .fillna(0)
        .astype(int) * 10000
    )


def transform_to_silver(conn: duckdb.DuckDBPyConnection) -> int:
    """Clean and normalize bronze data into silver.stg_million_sellers. Returns row count."""
    df = conn.execute("SELECT * FROM bronze.raw_million_sellers").df()

    df = df[df["Game Title"].notna() & ~df["Game Title"].isin(["-", ""])]

    df["game_title"]           = df["Game Title"].apply(_normalize_title)
    df["platform_name"]        = df["system"]
    df["fiscal_year"]          = df["Fiscal Year"].apply(_normalize_fiscal_year)
    df["snapshot_date"]        = pd.to_datetime(df["as of"], errors="coerce")
    df["global_sales"]         = _to_units(df["Global"])
    df["japan_sales"]          = _to_units(df["Japan"])
    df["outside_japan_sales"]  = _to_units(df["Outside of Japan"])
    df["ltd_global_sales"]     = _to_units(df["Life-to-date Global"])

    silver_cols = [
        "game_title", "platform_name", "fiscal_year", "snapshot_date",
        "global_sales", "japan_sales", "outside_japan_sales", "ltd_global_sales", "source",
    ]

    conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
    conn.execute("DROP TABLE IF EXISTS silver.stg_million_sellers")
    conn.register("_silver_df", df[silver_cols])
    conn.execute("CREATE TABLE silver.stg_million_sellers AS SELECT * FROM _silver_df")

    return len(df)
