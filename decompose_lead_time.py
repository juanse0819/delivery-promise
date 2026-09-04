import duckdb

con = duckdb.connect("delivery.duckdb")

con.sql("""
CREATE OR REPLACE TABLE orders_segments AS
SELECT
    order_id,
    purchased_at,
    total_days,
    promise_error_days,
    is_late,
    approval_suspect,
    date_diff('hour', purchased_at, approved_at) / 24.0 AS approval_days,
    date_diff('hour', approved_at, shipped_at) / 24.0 AS handoff_days,
    date_diff('hour', shipped_at, delivered_at) / 24.0 AS transit_days
FROM orders_base
""")

print("\n=== SEGMENT DISTRIBUTIONS (approval-suspect orders excluded) ===")
print(con.sql("""
    SELECT
        'approval' AS segment,
        ROUND(AVG(approval_days), 2) AS mean_days,
        ROUND(MEDIAN(approval_days), 2) AS median_days,
        ROUND(QUANTILE_CONT(approval_days, 0.95), 2) AS p95_days,
        ROUND(STDDEV(approval_days), 2) AS stddev_days,
        ROUND(QUANTILE_CONT(approval_days, 0.95) - MEDIAN(approval_days), 2) AS tail_spread
    FROM orders_segments WHERE NOT approval_suspect
    UNION ALL
    SELECT
        'handoff',
        ROUND(AVG(handoff_days), 2),
        ROUND(MEDIAN(handoff_days), 2),
        ROUND(QUANTILE_CONT(handoff_days, 0.95), 2),
        ROUND(STDDEV(handoff_days), 2),
        ROUND(QUANTILE_CONT(handoff_days, 0.95) - MEDIAN(handoff_days), 2)
    FROM orders_segments WHERE NOT approval_suspect
    UNION ALL
    SELECT
        'transit',
        ROUND(AVG(transit_days), 2),
        ROUND(MEDIAN(transit_days), 2),
        ROUND(QUANTILE_CONT(transit_days, 0.95), 2),
        ROUND(STDDEV(transit_days), 2),
        ROUND(QUANTILE_CONT(transit_days, 0.95) - MEDIAN(transit_days), 2)
    FROM orders_segments WHERE NOT approval_suspect
"""))

print("\n=== SHARE OF TOTAL TIME ===")
print(con.sql("""
    SELECT
        ROUND(AVG(approval_days), 2) AS approval,
        ROUND(AVG(handoff_days), 2) AS handoff,
        ROUND(AVG(transit_days), 2) AS transit,
        ROUND(100.0 * AVG(approval_days) / AVG(total_days), 1) AS pct_approval,
        ROUND(100.0 * AVG(handoff_days) / AVG(total_days), 1) AS pct_handoff,
        ROUND(100.0 * AVG(transit_days) / AVG(total_days), 1) AS pct_transit
    FROM orders_segments WHERE NOT approval_suspect
"""))

print("\n=== WHICH SEGMENT TRACKS LATENESS? ===")
print(con.sql("""
    SELECT
        is_late,
        COUNT(*) AS n_orders,
        ROUND(MEDIAN(approval_days), 2) AS approval,
        ROUND(MEDIAN(handoff_days), 2) AS handoff,
        ROUND(MEDIAN(transit_days), 2) AS transit
    FROM orders_segments WHERE NOT approval_suspect
    GROUP BY is_late
"""))

print("\n=== SANITY CHECK: SEGMENTS SHOULD SUM TO TOTAL ===")
print(con.sql("""
    SELECT
        COUNT(*) AS n_orders,
        ROUND(AVG(approval_days + handoff_days + transit_days), 3) AS sum_of_segments,
        ROUND(AVG(total_days), 3) AS total_days_col,
        ROUND(AVG(approval_days + handoff_days + transit_days) - AVG(total_days), 3) AS gap
    FROM orders_segments WHERE NOT approval_suspect
"""))