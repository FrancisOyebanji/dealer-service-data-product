-- ============================================================================
-- BigQuery curated warehouse — optimized dimensional model (Standard SQL).
-- Partitioning + clustering + materialized views + nested/repeated design,
-- with the cost/performance rationale a Data Architect documents for the client.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS `dealer_service`
  OPTIONS (location = 'US', description = 'Curated dealer-service analytics');

-- Fact partitioned by service date (prunes scans to the queried window) and
-- clustered by the highest-cardinality common filters (dealer, service type).
CREATE TABLE IF NOT EXISTS `dealer_service.fact_repair_orders` (
  ro_key            INT64  NOT NULL,
  ro_number         STRING NOT NULL,
  dealer_key        INT64  NOT NULL,
  vehicle_key       INT64  NOT NULL,
  customer_key      INT64  NOT NULL,
  service_date      DATE   NOT NULL,
  service_type      STRING,
  pay_type          STRING,          -- warranty | customer
  labor_amount      NUMERIC,
  parts_amount      NUMERIC,
  total_amount      NUMERIC,
  satisfaction_score INT64
)
PARTITION BY service_date
CLUSTER BY dealer_key, service_type
OPTIONS (
  partition_expiration_days = 2555,          -- 7-yr retention, then auto-expire storage
  require_partition_filter  = true           -- forces cost-safe queries (no full scans)
);

-- Nested/repeated design avoids a join for line items that are always read together.
CREATE TABLE IF NOT EXISTS `dealer_service.fact_ro_with_lines` (
  ro_number    STRING,
  service_date DATE,
  dealer_key   INT64,
  line_items ARRAY<STRUCT<
    op_code     STRING,
    description STRING,
    labor_hours NUMERIC,
    amount      NUMERIC
  >>
)
PARTITION BY service_date
CLUSTER BY dealer_key;

-- Materialized view: pre-aggregated hot path for dashboards. BigQuery keeps it
-- fresh incrementally and auto-routes queries — sub-second BI at low scan cost.
CREATE MATERIALIZED VIEW IF NOT EXISTS `dealer_service.mv_monthly_dealer_revenue`
PARTITION BY month
CLUSTER BY dealer_key AS
SELECT
  DATE_TRUNC(service_date, MONTH) AS month,
  dealer_key,
  COUNT(*)                        AS ro_count,
  SUM(total_amount)               AS total_revenue,
  AVG(satisfaction_score)         AS avg_csat
FROM `dealer_service.fact_repair_orders`
GROUP BY month, dealer_key;

-- Authorized view for governed consumption: exposes only non-sensitive columns
-- to the analyst group, without granting access to the base table.
CREATE VIEW IF NOT EXISTS `dealer_service.v_dealer_performance` AS
SELECT service_date, dealer_key, service_type, pay_type, total_amount, satisfaction_score
FROM `dealer_service.fact_repair_orders`;

-- Cost/perf notes:
--   * require_partition_filter = true prevents accidental full-table scans.
--   * clustering on (dealer_key, service_type) makes the common WHERE cheap.
--   * the MV replaces repeated GROUP BY scans of the fact for dashboards.
--   * NUMERIC (not FLOAT64) for money — exact decimal arithmetic.
