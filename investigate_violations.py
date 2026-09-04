import duckdb

con = duckdb.connect()
ORDERS = "read_csv_auto('data/raw/olist_orders_dataset.csv')"

VIOLATIONS = f"""
    SELECT
        date_diff('hour', order_delivered_carrier_date, order_approved_at) AS hours_early 
    FROM {ORDERS}
    WHERE Order_status = 'delivered'
    AND order_delivered_carrier_date < order_approved_At
"""

print("\n=== A. HOW EARLY DID THE CARRIER GET IT? ===")
print(con.sql(f"""
    WITH V AS ({VIOLATIONS})
    SELECT
        COUNT(*) AS n_orders,
        MIN(hours_early) AS min_hours,
        MEDIAN(hours_early) AS median_hours,
        QUANTILE_CONT(hours_early, 0.95) AS p95_hours,
        MAX(hours_early) AS max_hours
    FROM V
"""))

print("\n=== B. DISTRIBUTION OF THE GAP ===")
print(con.sql(f"""
    WITH V AS ({VIOLATIONS})   
    SELECT
        CASE
            WHEN hours_early <= 6 THEN 'a) 0-6 hours'
            WHEN hours_early <= 24 THEN 'b) 6-24 hours'
            WHEN hours_early <= 72 THEN 'c) 1-3 days'
            WHEN hours_early <= 168 THEN 'd) 3-7 days'
            ELSE 'e) over 7 days'
        END AS gap_bucket,
        COUNT(*) AS n_orders
    FROM V
    GROUP BY gap_bucket
    ORDER BY gap_bucket
"""))

print("\n=== C. ARE THESE ORDERS OTHERWISE NORMAL? ===")
print(con.sql(f"""
    SELECT
        CASE
              WHEN order_delivered_carrier_Date < order_approved_at
              THEN 'violation' ELSE 'clean'
        END AS grp,
        COUNT(*) AS n_orders,
        ROUND(MEDIAN(date_diff('day', order_purchase_timestamp,
              order_delivered_customer_date)), 1) AS median_total_days,
        ROUND(QUANTILE_CONT(date_diff('day', order_purchase_timestamp,
              order_delivered_customer_date), 0.95), 1) AS p95_total_days
    FROM {ORDERS}
    WHERE order_status = 'delivered'
        AND order_approved_at IS NOT NULL
        AND order_delivered_carrier_date IS NOT NULL
        AND order_delivered_customer_date IS NOT NULL
    GROUP BY grp
"""))