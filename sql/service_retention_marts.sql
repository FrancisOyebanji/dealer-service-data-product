-- Service Retention analytics marts (Snowflake SQL).
-- Curated retention KPIs the Aftersales team consumes in Power BI, plus the
-- feature view that feeds the Python retention model. Sources from the star
-- schema built by the data product (fact_repair_orders, dim_customer, dim_vehicle).

-- 1. Customer retention feature view (feeds the ML model / Power BI)
CREATE OR REPLACE VIEW analytics.v_customer_retention_features AS
SELECT
    c.customer_key,
    v.model,
    DATEDIFF('year', v.in_service_date, CURRENT_DATE())          AS vehicle_age,
    IFF(DATEDIFF('year', v.in_service_date, CURRENT_DATE()) <= 3, 1, 0) AS in_warranty,
    COUNT(f.ro_key)                                              AS prior_visits,
    DATEDIFF('month', MAX(f.open_date), CURRENT_DATE())         AS months_since_last_service,
    AVG(f.satisfaction_score)                                    AS avg_satisfaction,
    AVG(f.days_to_close)                                         AS avg_wait_days,
    AVG(f.repeat_repair_flag)                                    AS repeat_repair_rate,
    SUM(IFF(f.pay_type = 'customer', f.total_amount, 0))
      / NULLIF(SUM(f.total_amount), 0)                           AS customer_pay_share,
    SUM(f.total_amount)                                          AS total_service_spend,
    MAX(IFF(f.service_type = 'recall', 1, 0))                    AS had_recall
FROM analytics.fact_repair_orders f
JOIN analytics.dim_customer c ON c.customer_key = f.customer_key
JOIN analytics.dim_vehicle  v ON v.vehicle_key  = f.vehicle_key
GROUP BY c.customer_key, v.model, v.in_service_date;

-- 2. Service Retention Rate by dealer region (the headline Aftersales KPI)
CREATE OR REPLACE VIEW analytics.v_retention_by_region AS
SELECT d.region,
       COUNT(*)                                             AS customers,
       ROUND(100.0 * AVG(r.retained_next_period), 1)        AS retention_rate_pct
FROM analytics.customer_retention_labeled r
JOIN analytics.dim_dealer d ON d.dealer_id = r.dealer_id
GROUP BY d.region
ORDER BY retention_rate_pct DESC;

-- 3. Retention by warranty status (the strongest driver)
SELECT IFF(in_warranty = 1, 'In warranty', 'Out of warranty') AS segment,
       COUNT(*)                                       AS customers,
       ROUND(100.0 * AVG(retained_next_period), 1)    AS retention_rate_pct
FROM analytics.customer_retention_labeled
GROUP BY in_warranty;

-- 4. At-risk customer list for outreach (churn score joined from the model output)
--    QUALIFY the top decile by churn risk within each region for targeted campaigns
SELECT customer_key, region, churn_risk, recommended_action, expected_value
FROM analytics.customer_churn_scores
QUALIFY ROW_NUMBER() OVER (PARTITION BY region ORDER BY churn_risk DESC) <= 500;
