-- funnel_queries.sql
-- Example analytical queries against the real warehouse schema.
-- Note: these express the customer-lifecycle funnel (did a customer EVER
-- reach a stage), not a per-visit funnel -- see data/README.md for why
-- (the source data has no recoverable session structure).

-- 1. Customer lifecycle funnel: how many customers ever reached each stage
WITH customer_steps AS (
    SELECT
        customer_id,
        MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END)        AS reached_view,
        MAX(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END)       AS reached_click,
        MAX(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END) AS reached_cart,
        MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END)    AS reached_purchase
    FROM fct_events
    GROUP BY customer_id
)
SELECT
    SUM(reached_view)     AS view_count,
    SUM(reached_click)    AS click_count,
    SUM(reached_cart)     AS add_to_cart_count,
    SUM(reached_purchase) AS purchase_count,
    COUNT(*)              AS total_customers
FROM customer_steps;

-- 2. Ever-purchased rate by acquisition channel
WITH customer_purchased AS (
    SELECT customer_id, MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchased
    FROM fct_events
    GROUP BY customer_id
)
SELECT
    c.acquisition_channel,
    COUNT(*)                          AS customers,
    SUM(p.purchased)                  AS ever_purchased,
    ROUND(100.0 * SUM(p.purchased) / COUNT(*), 2) AS pct_ever_purchased
FROM dim_customers c
JOIN customer_purchased p ON p.customer_id = c.customer_id
GROUP BY c.acquisition_channel
ORDER BY pct_ever_purchased DESC;

-- 3. A/B test: purchase rate by experiment_group at the EVENT level
--    (experiment_group is assigned per-event, not persisted per customer --
--    see src/ab_testing.py for the full statistical treatment, including
--    the customer-clustered bootstrap robustness check this simple query
--    doesn't capture on its own)
SELECT
    experiment_group,
    COUNT(*) AS total_events,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchase_events,
    ROUND(100.0 * SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) / COUNT(*), 3) AS purchase_rate_pct
FROM fct_events
GROUP BY experiment_group
ORDER BY experiment_group;

-- 4. Average lifetime revenue per converted (ever-purchased) customer
SELECT
    ROUND(AVG(customer_total), 2) AS avg_revenue_per_converted_customer
FROM (
    SELECT customer_id, SUM(gross_revenue) AS customer_total
    FROM fct_transactions
    WHERE refund_flag = 0 AND gross_revenue IS NOT NULL
    GROUP BY customer_id
);

-- 5. Campaign performance: measured purchase-event share during each
--    campaign's active window vs. its own expected_uplift target
SELECT
    camp.campaign_id,
    camp.channel,
    camp.objective,
    camp.expected_uplift,
    COUNT(*) AS attributed_events,
    SUM(CASE WHEN e.event_type = 'purchase' THEN 1 ELSE 0 END) AS attributed_purchases,
    ROUND(100.0 * SUM(CASE WHEN e.event_type = 'purchase' THEN 1 ELSE 0 END) / COUNT(*), 3) AS purchase_rate_pct
FROM fct_events e
JOIN dim_campaigns camp ON camp.campaign_id = e.campaign_id
WHERE e.campaign_id != 0
GROUP BY camp.campaign_id, camp.channel, camp.objective, camp.expected_uplift
ORDER BY purchase_rate_pct DESC
LIMIT 10;
