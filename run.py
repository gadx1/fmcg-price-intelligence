"""
FMCG Price Intelligence — Daily Run Entrypoint (M3)
===================================================
Wires the scraper (M1) to the DuckDB data layer (M2), then exports the
cube slices the dashboard (M4) consumes. This is what the GitHub Actions
cron invokes once per day.

Usage:
    python run.py            # live scrape + ingest + export
    python run.py --dry-run  # parse local fixtures only, no network, no write
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scrapers"))

from scraper import load_config, scrape, parse_product, PriceRecord  # noqa: E402
from datastore import (  # noqa: E402
    ingest, latest_prices, sugar_tax_spread, price_trend, DATA_DIR,
)

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def export_cube_json() -> dict:
    """Flatten the three cube slices to JSON for the static dashboard (M4)."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "latest": json.loads(latest_prices().to_json(orient="records")),
        "sugar_tax_spread": json.loads(sugar_tax_spread().to_json(orient="records")),
        "trend": json.loads(price_trend().to_json(orient="records")),
    }
    out = REPORTS_DIR / "cube.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"path": str(out), "latest_rows": len(payload["latest"])}


def main(argv: list[str]) -> int:
    config = load_config()

    if "--dry-run" in argv:
        # No network: validate the parser against the committed fixture.
        fixture = Path(__file__).resolve().parent / "scrapers" / "fixtures" / "tesco_cola_2l.html"
        parsed = parse_product(fixture.read_text(encoding="utf-8"))
        print("DRY RUN — parser output from fixture:")
        for k, v in parsed.items():
            print(f"  {k:24} = {v!r}")
        return 0 if parsed["base_price"] is not None else 1

    records = scrape(config)
    ok = sum(1 for r in records if r.status == "OK")
    total = len(records)
    print(f"Scrape: {ok}/{total} SKUs OK")

    if ok == 0:
        print("WARNING: zero successful scrapes — not updating the cube.")
        return 1

    n = ingest(records)
    print(f"Ingested. Historical fact table now holds {n} rows.")
    print(f"Data lake: {DATA_DIR / 'fmcg_prices.parquet'}")

    exp = export_cube_json()
    print(f"Dashboard cube: {exp['path']} ({exp['latest_rows']} latest rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
