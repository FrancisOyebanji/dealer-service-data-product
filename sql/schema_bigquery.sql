-- Dealer Service Analytics — dimensional model (BigQuery dialect)
-- Star schema: fact_repair_orders at RO grain, conformed dimensions.
-- SQLite is used as the local execution engine in this repo; this file is the
-- production-target DDL showing partitioning/clustering design for BigQuery.

CREATE SCHEMA IF NOT EXISTS `dealer_service`;

CREATE TABLE IF NOT EXISTS `dealer_service.dim_dealer` (
  dealer_key     INT64 NOT NULL,
  dealer_id      STRING NOT NULL,
  dealer_name    STRING,
  region         STRING,
  service_bays   INT64,
  effective_from DATE,          -- SCD2-ready
  effective_to   DATE,
  is_current     BOOL
);

CREATE TABLE IF NOT EXISTS `dealer_service.dim_vehicle` (
  vehicle_key     INT64 NOT NULL,
  vin             STRING NOT NULL,   -- classified: INTERNAL (indirect identifier)
  model           STRING,
  model_year      INT64,
  warranty_months INT64,
  in_service_date DATE
);

CREATE TABLE IF NOT EXISTS `dealer_service.dim_customer` (
  customer_key    INT64 NOT NULL,
  email_hash      STRING,   -- SHA-256; raw email never lands in the warehouse
  phone_last4     STRING,   -- minimal retention per governance policy DP-2
  consent_status  STRING    -- ccpa_opt_out | consented | unknown
);

CREATE TABLE IF NOT EXISTS `dealer_service.dim_date` (
  date_key   INT64 NOT NULL,
  full_date  DATE NOT NULL,
  year       INT64, quarter INT64, month INT64,
  month_name STRING, is_weekend BOOL
);

CREATE TABLE IF NOT EXISTS `dealer_service.fact_repair_orders` (
  ro_key            INT64 NOT NULL,
  ro_number         STRING NOT NULL,
  dealer_key        INT64 NOT NULL,
  vehicle_key       INT64 NOT NULL,
  customer_key      INT64 NOT NULL,
  open_date_key     INT64 NOT NULL,
  service_type      STRING,
  pay_type          STRING,       -- warranty | customer
  days_to_close     INT64,
  labor_amount      NUMERIC,
  parts_amount      NUMERIC,
  total_amount      NUMERIC,
  repeat_repair_flag INT64,
  satisfaction_score INT64,       -- null when no survey response
  would_recommend    BOOL
)
PARTITION BY RANGE_BUCKET(open_date_key, GENERATE_ARRAY(20250101, 20260101, 100))
CLUSTER BY dealer_key, service_type;
