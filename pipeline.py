import argparse
import subprocess
from pathlib import Path

import duckdb
from prefect import flow, task, get_run_logger

from extractors.million_sellers import PDF_DIR, FIXED_HEADER, extract_all_pdfs
from loaders.bronze import DB_PATH, load_to_bronze
from transformers.silver import transform_to_silver

DBT_DIR = Path(__file__).parent / "nintendo_dbt"


@task(name="extract-million-sellers")
def extract_million_sellers() -> list[list[str]]:
    logger = get_run_logger()
    rows = extract_all_pdfs(PDF_DIR)
    logger.info(f"Extracted: {len(rows)} rows")
    return rows


@task(name="load-million-sellers-to-bronze")
def load_million_sellers(rows: list[list[str]]) -> int:
    logger = get_run_logger()
    inserted = load_to_bronze("raw_million_sellers", FIXED_HEADER, rows)
    logger.info(f"Bronze: {inserted} new rows inserted")
    return inserted


@task(name="transform-to-silver")
def transform_million_sellers() -> int:
    logger = get_run_logger()
    with duckdb.connect(str(DB_PATH)) as conn:
        count = transform_to_silver(conn)
    logger.info(f"Silver: {count} rows transformed")
    return count


@task(name="dbt-run")
def run_dbt() -> None:
    logger = get_run_logger()
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", "."],
        cwd=DBT_DIR,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"dbt run failed:\n{result.stderr}")
    logger.info("dbt run successful")


@flow(name="nintendo-elt-pipeline")
def nintendo_pipeline(reset: bool = False) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Database deleted: {DB_PATH}")
    rows = extract_million_sellers()
    load_million_sellers(rows)
    transform_million_sellers()
    run_dbt()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete database and re-ingest all data")
    args = parser.parse_args()
    nintendo_pipeline(reset=args.reset)
