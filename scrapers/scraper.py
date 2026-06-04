"""
FMCG Price Intelligence — Scraper Core (M1)
===========================================
Fetches public product pages from Tesco Ireland and extracts the RGM-relevant
price signals: base (shelf) price, normalised unit price, Clubcard promo price,
deposit, pack size and sugar content.

Design principles:
- Compliance-by-design: respects robots.txt path rules, human-rate delays,
  honest User-Agent, hard SKU cap.
- Zero heavy deps for the PoC: httpx + BeautifulSoup (no headless browser needed —
  validated that product pages render price data in static HTML).
- Self-documenting provenance: every row carries source URL + UTC timestamp.
"""

from __future__ import annotations

import random
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "catalog.yaml"


@dataclass
class PriceRecord:
    """One scraped observation — a row in the fact table / data cube."""
    scraped_at: str
    retailer: str
    market: str
    currency: str
    product_id: str
    brand: str
    variant: str
    sugar_class: str
    pack: str
    container: str
    title: str | None
    base_price: float | None
    unit_price: float | None         # e.g. €/litre as shown on page
    unit_price_basis: str | None     # the unit string, e.g. "litre"
    clubcard_price_text: str | None  # raw promo text (depth/frequency signal)
    deposit: float | None            # Deposit Return Scheme charge
    sugar_g_per_serving: float | None
    source_url: str
    status: str                      # OK | HTTP_<code> | PARSE_ERROR | SKIPPED_DISALLOWED


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def is_disallowed(url: str, fragments: list[str]) -> bool:
    """Compliance guard: never request URLs matching disallowed fragments."""
    return any(frag in url for frag in fragments)


# --- Parsing helpers ---------------------------------------------------------

_PRICE_RE = re.compile(r"€\s?(\d+\.\d{2})")
_UNIT_RE = re.compile(r"€\s?(\d+\.\d{2})\s*/\s*(\w+)")
_DEPOSIT_RE = re.compile(r"€\s?(\d+\.\d{2})\s*Deposit", re.IGNORECASE)
_SUGAR_RE = re.compile(r"of which sugars:?\s*\|?\s*[\d.]+g?\s*\|?\s*(\d+\.?\d*)g", re.IGNORECASE)


def _first_float(pattern: re.Pattern, text: str) -> float | None:
    m = pattern.search(text)
    return float(m.group(1)) if m else None


def parse_product(html: str) -> dict:
    """Extract structured price signals from a Tesco product page."""
    soup = BeautifulSoup(html, "html.parser")

    # Title — the <h1> on product pages
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else None

    # Work off the visible text for robust, layout-agnostic extraction.
    text = soup.get_text(separator=" ", strip=True)

    # Base price: first €X.XX that is NOT part of a unit ("/litre") or deposit string.
    base_price = None
    for m in _PRICE_RE.finditer(text):
        span_end = m.end()
        trailing = text[span_end: span_end + 12].lower()
        if "/" in trailing[:3] or "deposit" in trailing:
            continue
        base_price = float(m.group(1))
        break

    unit_m = _UNIT_RE.search(text)
    unit_price = float(unit_m.group(1)) if unit_m else None
    unit_basis = unit_m.group(2) if unit_m else None

    deposit = _first_float(_DEPOSIT_RE, text)

    # Clubcard promo text — capture the phrase for promo depth/frequency analysis.
    clubcard_text = None
    cc_idx = text.lower().find("clubcard price")
    if cc_idx != -1:
        raw = text[cc_idx: cc_idx + 90]
        clubcard_text = " ".join(raw.split())  # collapse whitespace/newlines

    sugar = _first_float(_SUGAR_RE, text)

    return {
        "title": title,
        "base_price": base_price,
        "unit_price": unit_price,
        "unit_price_basis": unit_basis,
        "clubcard_price_text": clubcard_text,
        "deposit": deposit,
        "sugar_g_per_serving": sugar,
    }


# --- Scrape orchestration ----------------------------------------------------

def scrape(config: dict) -> list[PriceRecord]:
    retailer = config["retailer"]
    comp = config["compliance"]
    products = config["products"]

    if len(products) > comp["max_skus_per_run"]:
        raise RuntimeError(
            f"SKU count {len(products)} exceeds compliance cap "
            f"{comp['max_skus_per_run']}. Refusing to run."
        )

    delay_lo, delay_hi = comp["request_delay_seconds"]
    headers = {"User-Agent": comp["user_agent"], "Accept-Language": "en-IE,en;q=0.9"}
    records: list[PriceRecord] = []

    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for i, p in enumerate(products):
            url = f"{retailer['base_url']}/{p['id']}"
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")

            base = dict(
                scraped_at=now,
                retailer=retailer["code"],
                market=retailer["market"],
                currency=retailer["currency"],
                product_id=p["id"],
                brand=p["brand"],
                variant=p["variant"],
                sugar_class=p["sugar_class"],
                pack=p["pack"],
                container=p["container"],
                title=None, base_price=None, unit_price=None,
                unit_price_basis=None, clubcard_price_text=None,
                deposit=None, sugar_g_per_serving=None,
                source_url=url, status="OK",
            )

            if is_disallowed(url, comp["disallowed_path_fragments"]):
                records.append(PriceRecord(**{**base, "status": "SKIPPED_DISALLOWED"}))
                continue

            try:
                resp = client.get(url)
                if resp.status_code != 200:
                    records.append(PriceRecord(**{**base, "status": f"HTTP_{resp.status_code}"}))
                else:
                    parsed = parse_product(resp.text)
                    records.append(PriceRecord(**{**base, **parsed, "status": "OK"}))
            except Exception as exc:  # noqa: BLE001 — PoC: record, don't crash the run
                records.append(PriceRecord(**{**base, "status": f"PARSE_ERROR:{type(exc).__name__}"}))

            if i < len(products) - 1:
                time.sleep(random.uniform(delay_lo, delay_hi))

    return records


def main() -> int:
    config = load_config()
    records = scrape(config)
    ok = sum(1 for r in records if r.status == "OK")
    print(f"Scraped {len(records)} SKUs — {ok} OK")
    for r in records:
        print(f"  [{r.status:>6}] {r.product_id} {r.pack:>10} "
              f"base=€{r.base_price} unit=€{r.unit_price}/{r.unit_price_basis} "
              f"sugar={r.sugar_g_per_serving}g  | {r.clubcard_price_text}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
