# FMCG Price Intelligence — Tesco Ireland · Coca-Cola CSD

> A zero-cost, low-maintenance **Revenue Growth Management (RGM)** analytics system that
> reads Coca-Cola carbonated soft-drink shelf prices from Tesco Ireland daily, persists a
> versioned historical fact table, and surfaces the **Sugar-Tax spread** and **promotional
> depth** — the signals RGM teams use to balance premiumisation and affordability.

**Live dashboard:** _(GitHub Pages URL after deploy)_ · **Author:** [@GadielAnalytics](https://github.com/Gadx1)

---

## Why this project

Coca-Cola Europacific Partners (CCEP) frames its investor narrative around revenue per
unit case and RGM — data-driven price-pack architecture, promotion optimisation, and the
balance of premiumisation vs affordability. Ireland is a sharp test case: an active
supermarket price war and a Sugar-Sweetened Drinks Tax that splits the cola portfolio into
taxed (full-sugar) and untaxed (zero/diet) packs.

This system reproduces, at hobby scale and zero cost, the kind of daily price-intelligence
signal that underpins those decisions — and frames the output in RGM language.

## Architecture

```
GitHub Actions (daily cron)
        │
        ▼
  scraper.py  ──(httpx + BeautifulSoup)──►  Tesco IE public product pages
        │
        ▼
  datastore.py  ──(DuckDB, in-process OLAP)──►  data/fmcg_prices.parquet  (versioned data lake)
        │                                              │
        │                                       cube queries
        ▼                                              ▼
  reports/cube.json  ──►  reports/dashboard.html  (D3 trends + Sugar-Tax spread)
                                   │
                                   ▼
                            GitHub Pages (public)
```

Four core tools, deliberately. The design avoids over-engineering: no headless browser
(product prices render in static HTML — verified), no managed database, no paid services.

| Layer | Tool | Why |
|---|---|---|
| Orchestration | GitHub Actions | Free cron, open network egress, commit-back as audit trail |
| Ingestion | httpx + BeautifulSoup | Lightweight; static HTML confirmed sufficient |
| Storage / OLAP | DuckDB + Parquet | In-process analytical SQL, zero server, git-versioned history |
| Visualization | D3 + GitHub Pages | Static, fast, fully controllable design |

## The signature insight: Sugar-Tax spread

Normalised unit price (€/litre) of full-sugar vs zero/diet, per pack. A positive spread
is the visible pass-through of Ireland's sugar levy onto full-sugar price-packs — exactly
what an RGM analyst watches. See `datastore.sugar_tax_spread()`.

## Repository layout

```
config/catalog.yaml        # SKUs to track — edit here, never touch code
scrapers/scraper.py        # fetch + parse → PriceRecord
scrapers/datastore.py      # DuckDB ingest + cube queries
scrapers/fixtures/         # real-HTML fixture for offline parser tests
run.py                     # daily entrypoint (scrape → ingest → export); --dry-run for offline
reports/dashboard.html     # D3 dashboard (reads cube.json)
.github/workflows/         # daily cron
COMPLIANCE.md              # compliance-by-design statement
```

## Compliance

Public, non-personal, factual price data only; robots.txt-respecting; human-rate; provenance
logged. Full statement in [`COMPLIANCE.md`](COMPLIANCE.md). Not legal advice.

## Roadmap

- [x] M0 Compliance & feasibility
- [x] M1 Scraper core (parser validated on real HTML)
- [x] M2 DuckDB data layer + cube queries
- [x] M3 GitHub Actions orchestration
- [x] M4 D3 dashboard
- [ ] M5 Deploy + first live data (see DEPLOYMENT.md)
- [ ] Future: add SuperValu for cross-retailer comparison; dbt + Great Expectations as data grows
```
```
