# Nintendo Sales ELT

Reads Nintendo quarterly reports (PDFs), extracts the million-seller tables, and transforms the data into a structured database with Bronze/Silver/Gold layers.

## What this project does

Nintendo publishes quarterly financial reports as PDFs containing tables of their best-selling games ("million-sellers"). This project:

1. **Extracts** the million-seller tables from all PDFs in `pdfs/`
2. **Loads** the raw data unchanged into the Bronze layer (`bronze.raw_million_sellers`)
3. **Transforms** via Python into cleaned data in the Silver layer (`silver.stg_million_sellers`)
4. **Models** via dbt into dimensions and facts in the Gold layer
5. **Visualises** the results via a Streamlit dashboard (`dashboard/app.py`)

## Prerequisites

Python 3.11+ and the dependencies from `requirements.txt`:

```
pip install -r requirements.txt
```

dbt is included in `requirements.txt`.

## Commands

### Run the full pipeline (PDFs → Bronze → Silver → Gold)

The pipeline is orchestrated with [Prefect](https://docs.prefect.io/). Each step (extract, quality check, bronze load, silver transform, silver quality check, dbt run, dbt test) is a Prefect task inside the `nintendo-elt-pipeline` flow.

**Linux/macOS:**
```
PYTHONPATH=src python src/pipeline.py
```

**Windows (PowerShell):**
```powershell
$env:PYTHONPATH="src"; python src/pipeline.py
```

Reads all PDFs in `pdfs/`, loads new rows into Bronze, transforms them via Python into Silver, then runs `dbt run` for Gold and `dbt test` to validate data quality.

**Linux/macOS:**
```
PYTHONPATH=src python src/pipeline.py --reset
```

**Windows (PowerShell):**
```powershell
$env:PYTHONPATH="src"; python src/pipeline.py --reset
```

Deletes the entire database and re-ingests all data from scratch.

### Start the dashboard

```powershell
streamlit run dashboard/app.py
```

Opens at `localhost:8501`. Requires the database to exist (run the pipeline first). Three tabs: time series comparison, top-sellers, platform overview.

### Run only dbt (without re-extraction)

```
cd src/nintendo_dbt
dbt run --profiles-dir .
```

### Run tests

```
pytest tests/
```

Python unit tests run automatically on every push/pull request via GitHub Actions (`.github/workflows/tests.yml`).

### Run dbt tests (data quality)

```
cd src/nintendo_dbt
dbt test --profiles-dir .
```

Validates uniqueness, not-null constraints, and referential integrity across all Gold tables. Also runs automatically at the end of every pipeline run.

## Database layers

### Bronze - Raw data

Table `bronze.raw_million_sellers`: data exactly as in the PDF, no transformation.

| Column | Description |
|---|---|
| `Game Title` | Game title as printed in the PDF (may contain special characters) |
| `Global` | Worldwide sales in this quarter (millions, as text) |
| `Japan` | Japan sales |
| `Outside of Japan` | Sales outside Japan |
| `Life-to-date Global` | Cumulative total sales since launch |
| `system` | e.g. "Nintendo Switch", "Nintendo 3DS" |
| `Fiscal Year` | e.g. "FY24" |
| `as of` | Report reference date (YYYY-MM-DD) |
| `source` | Source PDF filename |
| `ingested_at` | Timestamp of ingestion |

### Silver - Cleaned

Table `silver.stg_million_sellers`: Bronze data cleaned via Python - titles normalized to Title Case, sales figures converted to integers (× 10,000), date as `DATE`.

### Gold - Dimensions and facts

| Table | Content |
|---|---|
| `gold.dim_game` | Distinct game titles with MD5 surrogate key |
| `gold.dim_platform` | Distinct platforms with MD5 surrogate key |
| `gold.fct_sales` | All sales rows with foreign keys to dim_game/dim_platform |

## Project structure

```
game-sales-elt/
├── pdfs/                            # Source PDFs from Nintendo
├── src/
│   ├── extractors/
│   │   └── million_sellers.py       # Extraction logic (2 PDF formats + split-column layout)
│   ├── loaders/
│   │   └── bronze.py                # Loads extracted rows into DuckDB (Bronze)
│   ├── transformers/
│   │   └── silver.py                # Python cleaning Bronze → Silver
│   ├── quality/
│   │   └── checks.py                # Data quality checks (extraction + silver)
│   ├── nintendo_dbt/
│   │   ├── models/
│   │   │   └── gold/
│   │   │       ├── dim_game.sql
│   │   │       ├── dim_platform.sql
│   │   │       ├── fct_sales.sql
│   │   │       └── schema.yml           # dbt tests (unique, not_null, relationships)
│   │   ├── dbt_project.yml
│   │   └── profiles.yml                 # dbt connection config (DuckDB path)
│   └── pipeline.py                  # Prefect flow: Extract → Bronze → Silver → dbt
├── dashboard/
│   └── app.py                       # Streamlit dashboard (Zeitreihe, Top-Seller, Plattformen)
├── tests/
│   ├── test_extractor.py            # Unit tests for extraction helpers
│   ├── test_bronze_loader.py        # Unit tests for bronze loader (deduplication etc.)
│   ├── test_silver_transformer.py   # Unit tests for silver transformer
│   └── test_quality_checks.py       # Unit tests for data quality checks
├── .github/
│   └── workflows/
│       └── tests.yml                # CI: runs pytest on push/PR
├── conftest.py                      # pytest path setup (src/ on PYTHONPATH)
├── prefect.yaml                     # Prefect logging config
├── nintendo_sales.duckdb            # Database (not in git)
└── requirements.txt
```

## Browsing the database

The database is stored in `nintendo_sales.duckdb`. **DBeaver** is recommended for browsing:

1. New connection → select "DuckDB"
2. Point to the `nintendo_sales.duckdb` file
3. Schemas: `bronze`, `silver`, `gold`

**Note:** Disconnect DBeaver before running `pipeline.py` - DuckDB only allows one concurrent writer.

## PDF formats

The extraction script supports three different PDF layouts Nintendo has used over the years:

| Format | Period | Detection |
|---|---|---|
| New | from ~FY24 | 5-column table, title in column 1 |
| Old | FY07–FY23 | 4-column table (numbers only), game titles parsed from page text |

FY21–FY24 PDFs additionally use a **split-column layout** within the new format: the table is divided into a left and a right half (or a 3×2 grid) on the same page. This is a layout variation, not a separate format.

**Known edge cases:**
- Multi-line titles are reassembled in `_merge_continuation_rows`
- Broken fonts (each character repeated 4 times) are fixed via `_normalize_text()` - affects e.g. `171030_4e.pdf`
- Full-width Unicode platform labels (e.g. `Ｗｉｉ` instead of `Wii`) in PDFs from FY07–FY10 are normalized via NFKC in `_normalize_text()`
- Some older PDFs (e.g. `160727_3e.pdf`) return 0 rows - there were no million-sellers
- **Split left/right layout** (FY21–FY24 era): the million-seller table is split into two side-by-side columns on the same page (sometimes a 3×2 grid)
