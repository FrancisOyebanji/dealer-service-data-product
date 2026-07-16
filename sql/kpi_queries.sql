-- KPI library for the dealer service data product.
-- Written against the star schema; runs on SQLite and (with minor dialect
-- changes) BigQuery. Each query is a consumption contract for a dashboard tile.

-- 1. Fixed-first-visit rate by region (repeat repairs are the anti-metric)
SELECT dd.region,
       ROUND(100.0 * SUM(CASE WHEN f.repeat_repair_flag = 0 THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS fixed_first_visit_pct,
       COUNT(*) AS repair_orders
FROM fact_repair_orders f
JOIN dim_dealer dd ON dd.dealer_key = f.dealer_key
GROUP BY dd.region
ORDER BY fixed_first_visit_pct DESC;

-- 2. Average customer satisfaction and revenue per RO by dealer (top 10)
SELECT dd.dealer_name, dd.region,
       ROUND(AVG(f.satisfaction_score), 2) AS avg_csat,
       ROUND(AVG(f.total_amount), 2)       AS avg_revenue_per_ro,
       COUNT(*)                            AS ro_count
FROM fact_repair_orders f
JOIN dim_dealer dd ON dd.dealer_key = f.dealer_key
WHERE f.satisfaction_score IS NOT NULL
GROUP BY dd.dealer_key
HAVING COUNT(*) >= 50
ORDER BY avg_csat DESC, avg_revenue_per_ro DESC
LIMIT 10;

-- 3. Warranty vs customer-pay mix by month (margin pressure trend)
SELECT d.year, d.month, d.month_name,
       ROUND(SUM(CASE WHEN f.pay_type = 'warranty' THEN f.total_amount ELSE 0 END), 2) AS warranty_spend,
       ROUND(SUM(CASE WHEN f.pay_type = 'customer' THEN f.total_amount ELSE 0 END), 2) AS customer_pay_revenue
FROM fact_repair_orders f
JOIN dim_date d ON d.date_key = f.open_date_key
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- 4. Service throughput vs capacity (bays as denominator)
SELECT dd.dealer_name, dd.service_bays,
       COUNT(*)                                   AS annual_ros,
       ROUND(1.0 * COUNT(*) / dd.service_bays, 1) AS ros_per_bay
FROM fact_repair_orders f
JOIN dim_dealer dd ON dd.dealer_key = f.dealer_key
GROUP BY dd.dealer_key
ORDER BY ros_per_bay DESC
LIMIT 10;

-- 5. Satisfaction by days-to-close (the CX case for cycle-time investment)
SELECT f.days_to_close,
       ROUND(AVG(f.satisfaction_score), 2) AS avg_csat,
       COUNT(*) AS surveyed_ros
FROM fact_repair_orders f
WHERE f.satisfaction_score IS NOT NULL
GROUP BY f.days_to_close
ORDER BY f.days_to_close;

-- 6. Recall completion pressure by model (field-action exposure)
SELECT dv.model,
       SUM(CASE WHEN f.service_type = 'recall' THEN 1 ELSE 0 END) AS recall_ros,
       COUNT(*) AS total_ros,
       ROUND(100.0 * SUM(CASE WHEN f.service_type = 'recall' THEN 1 ELSE 0 END) / COUNT(*), 1)
         AS recall_share_pct
FROM fact_repair_orders f
JOIN dim_vehicle dv ON dv.vehicle_key = f.vehicle_key
GROUP BY dv.model
ORDER BY recall_share_pct DESC;

-- 7. ETL reconciliation (governance: every consumption number is traceable)
SELECT stage, entity, row_count FROM etl_audit ORDER BY rowid;
