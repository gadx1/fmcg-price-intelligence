"""
FMCG Price Intelligence — Data Layer (M2)
=========================================
DuckDB-backed OLAP layer. Ingests daily PriceRecord rows, persists an append-only
historical fact table to Parquet (versioned in git), and exposes the analytical
"cube" queries — including the signature Sugar-Tax spread.

Why DuckDB: in-process analytical SQL over Parquet, zero server, runs anywhere
(CI runner, laptop, browser via Wasm). The modern analytics-engineering signal.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FACT_PARQUET = DATA_DIR / "fmcg_prices.parquet"


# --- Schema ------------------------------------------------------------------

FACT_COLUMNS = [
    "scraped_at", "retailer", "market", "currency", "product_id", "brand",
    "variant", "sugar_class", "pack", "container", "title", "base_price",
    "unit_price", "unit_price_basis", "clubcard_price_text", "deposit",
    "sugar_g_per_serving", "source_url", "status",
]


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database=":memory:")


def _schema_ddl() -> str:
    types = {
        "base_price": "DOUBLE", "unit_price": "DOUBLE", "deposit": "DOUBLE",
        "sugar_g_per_serving": "DOUBLE",
    }
    return ", ".join(f"{c} {types.get(c, 'VARCHAR')}" for c in FACT_COLUMNS)


def ingest(records: list, parquet_path: Path = FACT_PARQUET) -> int:
    """
    Append today's records to the historical fact table (Parquet).
    Append-only by design: every day is a new immutable snapshot, so the
    git history of the Parquet file *is* the audit trail.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = [dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r for r in records]

    con = _connect()
    # parquet is statically linked in modern DuckDB; no INSTALL/LOAD needed.

    con.execute(f"CREATE TABLE incoming ({_schema_ddl()})")
    con.executemany(
        f"INSERT INTO incoming VALUES ({', '.join(['?'] * len(FACT_COLUMNS))})",
        [[row[c] for c in FACT_COLUMNS] for row in rows],
    )

    if parquet_path.exists():
        con.execute(f"CREATE TABLE hist AS SELECT * FROM read_parquet('{parquet_path}')")
        con.execute("INSERT INTO hist SELECT * FROM incoming")
    else:
        con.execute("CREATE TABLE hist AS SELECT * FROM incoming")

    con.execute(f"COPY hist TO '{parquet_path}' (FORMAT PARQUET)")
    total = con.execute("SELECT COUNT(*) FROM hist").fetchone()[0]
    con.close()
    return total


# --- Cube queries ------------------------------------------------------------

def latest_prices(parquet_path: Path = FACT_PARQUET):
    """Most recent observation per SKU — the 'current state' slice of the cube."""
    con = _connect()
    df = con.execute(f"""
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY retailer, product_id ORDER BY scraped_at DESC
            ) AS rn
            FROM read_parquet('{parquet_path}')
            WHERE status = 'OK'
        )
        SELECT brand, variant, pack, container, sugar_class,
               base_price, unit_price, unit_price_basis, deposit,
               clubcard_price_text, scraped_at
        FROM ranked WHERE rn = 1
        ORDER BY brand, variant, pack
    """).df()
    con.close()
    return df


def sugar_tax_spread(parquet_path: Path = FACT_PARQUET):
    """
    SIGNATURE INSIGHT: compare normalised unit price of full-sugar vs zero/diet
    on the latest snapshot. Quantifies how the IE Sugar-Sweetened Drinks Tax
    pass-through shows up in shelf price-pack architecture.
    """
    con = _connect()
    df = con.execute(f"""
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY retailer, product_id ORDER BY scraped_at DESC
            ) AS rn
            FROM read_parquet('{parquet_path}')
            WHERE status = 'OK' AND unit_price IS NOT NULL
        ),
        latest AS (SELECT * FROM ranked WHERE rn = 1),
        by_class AS (
            SELECT pack,
                   AVG(CASE WHEN sugar_class = 'full' THEN unit_price END) AS full_unit,
                   AVG(CASE WHEN sugar_class IN ('zero','diet') THEN unit_price END) AS nosugar_unit
            FROM latest GROUP BY pack
        )
        SELECT pack, full_unit, nosugar_unit,
               ROUND(full_unit - nosugar_unit, 3) AS spread_per_unit,
               ROUND(100.0 * (full_unit - nosugar_unit) / NULLIF(nosugar_unit,0), 1) AS spread_pct
        FROM by_class
        WHERE full_unit IS NOT NULL AND nosugar_unit IS NOT NULL
        ORDER BY pack
    """).df()
    con.close()
    return df


def price_trend(parquet_path: Path = FACT_PARQUET):
    """Daily base-price trend per SKU — feeds the visual trend report (M4)."""
    con = _connect()
    df = con.execute(f"""
        SELECT CAST(scraped_at AS DATE) AS date, brand, variant, pack,
               AVG(base_price) AS base_price,
               AVG(unit_price) AS unit_price
        FROM read_parquet('{parquet_path}')
        WHERE status = 'OK'
        GROUP BY 1,2,3,4
        ORDER BY date, brand, variant, pack
    """).df()
    con.close()
    return df
