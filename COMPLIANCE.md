# Compliance & Data Provenance

> Compliance-by-design statement for the FMCG Price Intelligence PoC.
> Maintained as a first-class project artifact, not an afterthought.

## Scope of collection

| Dimension | Decision | Rationale |
|---|---|---|
| **Data type** | Public product attributes & shelf prices only | Factual, non-personal — lowest legal-risk category |
| **Personal data** | None collected | Keeps project fully outside GDPR subject-data scope |
| **Source** | `tesco.ie` public grocery product pages | Publicly accessible without authentication |
| **Volume** | ~20–40 SKUs, once daily | Traffic indistinguishable from a single human shopper |
| **Purpose** | Price-monitoring / market research / portfolio demonstration | Recognised legitimate-interest use case |

## robots.txt adherence (checked 2026-06-02)

The Tesco platform `robots.txt` disallows specific paths — promotion query-string
URLs (`/groceries/*-*/promotions/*?*=*`), paginated `offset=` parameters, login,
registration and cookie-preference routes. It does **not** disallow:

- Product detail pages: `/groceries/en-IE/products/{id}`
- Base category listing pages

**Our crawler targets only allowed paths** and never appends disallowed query
parameters. Disallowed routes are hard-excluded in code.

## Operating principles

1. **Respect robots.txt** — disallowed paths are never requested.
2. **Human-rate access** — sequential requests, randomised delay, daily cadence only.
3. **Identify honestly** — descriptive User-Agent with project contact.
4. **No authentication bypass** — only publicly rendered, non-logged-in content.
5. **Provenance logged** — every run records source domain, SKU set, timestamp (UTC).
6. **No redistribution of copyrighted descriptive text** — we retain numeric/price
   facts and structured attributes for analysis, not Tesco's prose product copy.

## Legal posture (informational, not legal advice)

Public, non-personal, factual price data collected at human rate for market-research
purposes sits in the lowest-risk band under both EU and US frameworks. This is a
non-commercial, personal portfolio project. This document is a good-faith compliance
statement and does not constitute legal advice.

_Last reviewed: 2026-06-02_
