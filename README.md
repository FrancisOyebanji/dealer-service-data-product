# Dealer Aftersales Analytics — Service Retention & Data Product

**Automotive Aftersales analytics: a predictive/prescriptive Service Retention layer (churn model, retention drivers, KPIs, and targeted outreach recommendations) on top of a governed, dimensional dealer-service data product (ETL → star-schema warehouse → KPIs → dashboard). SQL, Python, Snowflake-style marts, Power BI-style dashboards.**

> **In one breath (Service Retention focus):** Built a Service Retention analytics solution for automotive Aftersales — a predictive churn model (0.72 AUC, 1.7x lift on the top-decile at-risk customers) that surfaces the retention drivers (service recency, warranty status, vehicle age, repeat-repair rate), Service Retention KPIs segmented by region/warranty/model, and a prescriptive layer that recommends a targeted retention action per at-risk customer ranked by churn-risk × value — all sitting on a governed star-schema dealer-service data product with ETL, data-quality gates, and a CCPA/GDPR governance catalog.

---

## Service Retention analytics (headline for the Aftersales role)

The predictive/prescriptive layer that drives "insights and recommendations around Service Retention and related KPIs":

```bash
PYTHONPATH=src python src/retention/generate_service_history.py   # 15k customers w/ known churn drivers
PYTHONPATH=src python -m retention.retention_analytics            # model + KPIs + prescription
PYTHONPATH=src python src/retention/build_retention_dashboard.py  # Power BI-style readout
```

| Component | What it delivers |
|---|---|
| **Churn/retention model** ([retention_analytics.py](src/retention/retention_analytics.py)) | Predicts non-return; **0.72 AUC**, **1.7x lift** at top-10% risk; recovers the true drivers (recency, warranty, vehicle age) |
| **Service Retention KPIs** | Overall retention rate + segmented by region, warranty status, and model — the Aftersales scorecard |
| **Prescriptive outreach** | Per at-risk customer: recommended action (lapsed-maintenance reminder, warranty-expiry offer, service recovery, loyalty, recall follow-up) ranked by churn-risk × value |
| **Snowflake marts** ([service_retention_marts.sql](sql/service_retention_marts.sql)) | Retention feature view + KPI views feeding Power BI, with a QUALIFY-based at-risk targeting query |

The model is **graded against a known churn process** (the generator constructs the drivers), so a test asserts it recovers service recency and warranty status as the top retention levers — the domain-authentic Service Retention drivers.

---

## The underlying data product (foundation)

**A governed, dimensional data product for dealer service operations: heterogeneous source integration → ETL with data quality gates → star-schema warehouse → KPI library → dashboard, with a CCPA/GDPR-aligned governance catalog.**

> Architected an end-to-end analytics data product integrating heterogeneous dealer service sources (DMS extracts, nested survey APIs, vehicle master data) into a dimensional star-schema warehouse with automated data quality gates, ETL audit reconciliation, and UAT-style acceptance testing. Implemented a column-level data governance catalog with CCPA/GDPR-aligned privacy policies — PII minimization at transform time, erasure-safe key design, and role-based access tiers — feeding a curated KPI layer and interactive dashboard.

## The data product loop

```
 DMS repair orders (CSV) ─┐
 Survey API (nested JSON) ─┼─> validate (DQ gates) ─> transform (PII minimize,
 Vehicle master (CSV)     ─┤        │                  surrogate keys, conform)
 Dealer reference (CSV)   ─┘        ▼                        │
                              dq_rejects                     ▼
                          (quarantine + reason)      star schema warehouse
                                                     (SQLite local / BigQuery DDL)
                                                             │
                                        ┌────────────────────┼─────────────────┐
                                        ▼                    ▼                 ▼
                                  KPI SQL library      acceptance tests   dashboard.html
```

## Run it

```bash
python src/run_product.py        # sources -> ETL -> dashboard (≈5 seconds)
python -m pytest tests/ -q       # 7 UAT-style acceptance criteria
```

Sample run: `Extracted 12,000 | loaded 11,770 | rejected 230 (missing_vin:87, duplicate_ro_number:73, negative_amount:70)` — the sources deliberately seed bad rows; the pipeline must catch every one, and AC2 verifies extract = load + rejects.

Then open `reports/dashboard.html` — fixed-first-visit rate by region, satisfaction vs. cycle time, warranty/customer-pay mix, recall exposure by model.

## What each layer demonstrates

| Layer | File(s) | JD-relevant skill |
|---|---|---|
| Dimensional modeling | [sql/schema_bigquery.sql](sql/schema_bigquery.sql) | Star schema at declared grain, SCD2-ready dims, BigQuery partitioning/clustering design |
| Heterogeneous integration | [src/etl.py](src/etl.py) | CSV + nested JSON sources conformed into one model; ETL audit table makes reconciliation a query |
| Data quality / UAT | [tests/test_pipeline.py](tests/test_pipeline.py) | Acceptance criteria as executable tests: referential integrity, grain uniqueness, measure validity, reconciliation balance |
| Governance & privacy | [governance/data_catalog.yaml](governance/data_catalog.yaml) | Column-level classification and lineage (Informatica EDC-style), CCPA/GDPR policies: minimization, erasure, retention, opt-out |
| Consumption / BI | [sql/kpi_queries.sql](sql/kpi_queries.sql), [src/build_dashboard.py](src/build_dashboard.py) | Each KPI query is a dashboard tile's contract; the reporting layer reads only the curated warehouse |

## Design choices worth noting

- **Privacy by design, enforced by test.** Raw email/phone are transformed at ETL time (SHA-256 hash, last-4 truncation) and never land in the warehouse — and AC5 fails the build if any table ever grows a raw PII column.
- **Erasure-safe keys.** Deletion requests (CCPA §1798.105 / GDPR Art. 17) execute against `dim_customer` by hash; facts keep surrogate keys, so erasure never corrupts historical aggregates.
- **Rejects are data, not logs.** Quarantined rows carry machine-readable reasons in `dq_rejects`, so data quality trends are themselves queryable.
- **SQLite as the local engine, BigQuery as the target.** The star schema runs anywhere Python does; the production DDL shows the partition/cluster design decisions that matter at Ford scale.

## Data & compliance

All source data is synthetic, generated with a fixed seed by `src/generate_sources.py`. No real customer, dealer, or vehicle data is used or represented.

---

*Francis Oluwatobi · oluwatobi.ou@gmail.com*
