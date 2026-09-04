import duckdb

con = duckdb.connect("delivery.duckdb")

CUSTOMERS = "read_csv_auto('data/raw/olist_customers_dataset.csv')"

con.sql(f"""
CREATE OR REPLACE TABLE orders_geo AS
SELECT
    s.order_id,
    s.total_days,
    s.transit_days,
    s.handoff_days,
    s.promise_error_days,
    s.is_late,
    c.customer_state
FROM orders_segments s
JOIN orders_base b
    ON s.order_id = b.order_id
LEFT JOIN {CUSTOMERS} c
    ON b.customer_id = c.customer_id
WHERE NOT s.approval_suspect
""")

print("\n=== JOIN CHECK ===")
print(con.sql("""
    SELECT
        COUNT(*) AS n_rows,
        COUNT(customer_state) AS has_state,
        COUNT(*) - COUNT(customer_state) AS missing_state
    FROM orders_geo
"""))

print("\n=== TRANSIT TIME BY CUSTOMER STATE (top 15 by volume) ===")
print(con.sql("""
    SELECT
        customer_state,
        COUNT(*) AS n_orders,
        ROUND(MEDIAN(transit_days), 1) AS median_transit,
        ROUND(QUANTILE_CONT(transit_days, 0.95), 1) AS p95_transit,
        ROUND(MEDIAN(promise_error_days), 1) AS median_promise_error,
        ROUND(100.0 * AVG(is_late::INT), 1) AS pct_late
    FROM orders_geo
    GROUP BY customer_state
    ORDER BY n_orders DESC
    LIMIT 15
"""))

print("\n=== FASTEST VS SLOWEST STATES (min 200 orders) ===")
print(con.sql("""
    WITH by_state AS (
        SELECT
            customer_state,
            COUNT(*) AS n_orders,
            MEDIAN(transit_days) AS median_transit
        FROM orders_geo
        GROUP BY customer_state
        HAVING COUNT(*) >= 200
    )
    SELECT * FROM (
        (SELECT 'fastest' AS grp, * FROM by_state ORDER BY median_transit ASC LIMIT 5)
        UNION ALL
        (SELECT 'slowest' AS grp, * FROM by_state ORDER BY median_transit DESC LIMIT 5)
    )
    ORDER BY grp, median_transit
"""))

print("\n=== HOW MUCH VARIANCE DOES STATE EXPLAIN? ===")
print(con.sql("""
    WITH state_med AS (
        SELECT customer_state, MEDIAN(transit_days) AS state_median
        FROM orders_geo GROUP BY customer_state
    )
    SELECT
        ROUND(VAR_POP(g.transit_days), 2) AS total_variance,
        ROUND(VAR_POP(g.transit_days - m.state_median), 2) AS within_state_variance,
        ROUND(100.0 * (1 - VAR_POP(g.transit_days - m.state_median)
                         / VAR_POP(g.transit_days)), 1) AS pct_explained_by_state
    FROM orders_geo g
    JOIN state_med m ON g.customer_state = m.customer_state
"""))

