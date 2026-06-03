import argparse
import subprocess
from pathlib import Path

import duckdb
from prefect import flow, task, get_run_logger

from extractors.million_sellers import PDF_DIR, FIXED_HEADER, extract_all_pdfs
from extractors.wiki_best_sellers import WIKI_HEADER, extract_rows as extract_wiki_rows
from loaders.bronze import DB_PATH, load_to_bronze
from transformers.silver import transform_to_silver
from quality.checks import check_extraction_results, check_silver_data

DBT_DIR = Path(__file__).resolve().parent / "nintendo_dbt"


@task(name="extract-million-sellers")
def extract_million_sellers() -> list[list[str]]:
    logger = get_run_logger()
    rows = extract_all_pdfs(PDF_DIR, logger)
    logger.info(f"Extracted: {len(rows)} rows")
    return rows


@task(name="load-million-sellers-to-bronze")
def load_million_sellers(rows: list[list[str]]) -> int:
    logger = get_run_logger()
    inserted = load_to_bronze("raw_million_sellers", FIXED_HEADER, rows)
    logger.info(f"Bronze: {inserted} new rows inserted")
    return inserted


@task(name="extract-wiki-best-sellers")
def extract_wiki_best_sellers() -> list[list[str]]:
    logger = get_run_logger()
    rows = extract_wiki_rows()
    logger.info(f"Extracted: {len(rows)} wiki rows")
    return rows


@task(name="load-wiki-best-sellers-to-bronze")
def load_wiki_best_sellers(rows: list[list[str]]) -> int:
    logger = get_run_logger()
    inserted = load_to_bronze("raw_wiki_best_sellers", WIKI_HEADER, rows)
    logger.info(f"Bronze: {inserted} new wiki rows inserted")
    return inserted


@task(name="transform-to-silver")
def transform_million_sellers() -> int:
    logger = get_run_logger()
    with duckdb.connect(str(DB_PATH)) as conn:
        count = transform_to_silver(conn)
    logger.info(f"Silver: {count} rows transformed")
    return count


@task(name="quality-check-extraction")
def quality_check_extraction(rows: list[list[str]]) -> None:
    logger = get_run_logger()
    for w in check_extraction_results(rows):
        logger.warning(f"[QUALITY] {w}")


@task(name="quality-check-silver")
def quality_check_silver() -> None:
    logger = get_run_logger()
    with duckdb.connect(str(DB_PATH)) as conn:
        warnings = check_silver_data(conn)
    for w in warnings:
        logger.warning(f"[QUALITY] {w}")


@task(name="dbt-run")
def run_dbt() -> None:
    logger = get_run_logger()
    result = subprocess.run(
        "dbt run --profiles-dir .",
        cwd=str(DBT_DIR),
        capture_output=True,
        text=True,
        shell=True,
    )
    if result.stdout:
        logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"dbt run failed:\n{result.stderr}")
    logger.info("dbt run successful")


@task(name="dbt-test")
def test_dbt() -> None:
    logger = get_run_logger()
    result = subprocess.run(
        "dbt test --profiles-dir .",
        cwd=str(DBT_DIR),
        capture_output=True,
        text=True,
        shell=True,
    )
    if result.stdout:
        logger.info(result.stdout)
    if result.returncode != 0:
        logger.error(result.stderr)
        raise RuntimeError(f"dbt test failed:\n{result.stderr}")
    logger.info("dbt test successful")


@flow(name="nintendo-elt-pipeline")
def nintendo_pipeline(reset: bool = False) -> None:
    logger = get_run_logger()
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        logger.info(f"Database deleted: {DB_PATH}")
    rows = extract_million_sellers()
    quality_check_extraction(rows)
    load_million_sellers(rows)
    wiki_rows = extract_wiki_best_sellers()
    load_wiki_best_sellers(wiki_rows)
    transform_million_sellers()
    quality_check_silver()
    run_dbt()
    test_dbt()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete database and re-ingest all data")
    args = parser.parse_args()
    nintendo_pipeline(reset=args.reset)
