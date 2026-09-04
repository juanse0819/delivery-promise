import duckdb

con = duckdb.connect("delivery.duckdb")
ORDERS = "read_csv_auto('data/raw/olist_orders_dataset.csv')"

con.sql(f"""
CREATE OR REPLACE TABLE orders_base AS
SELECT
    order_id,
    customer_id,
    order_purchase_timestamp AS purchased_at,
    order_approved_at AS approved_at,
    order_delivered_carrier_date AS shipped_at,
    order_delivered_customer_date AS delivered_at,
    order_estimated_delivery_date AS promised_at,
    date_diff('day', order_purchase_timestamp, order_delivered_customer_date) AS total_days,
    date_diff('day', order_estimated_delivery_date, order_delivered_customer_date) AS promise_error_days,
    order_delivered_customer_date > order_estimated_delivery_date AS is_late,
    order_delivered_carrier_date < order_approved_at AS approval_suspect
FROM {ORDERS}
WHERE order_status = 'delivered'
  AND order_approved_at IS NOT NULL
  AND order_delivered_carrier_date IS NOT NULL
  AND order_delivered_customer_date IS NOT NULL
  AND order_purchase_timestamp >= '2017-01-01'
  AND order_purchase_timestamp < '2018-09-01'
  AND date_diff('hour', order_delivered_carrier_date, order_approved_at) <= 168
""")

print("\n=== FUNNEL: WHAT SURVIVED ===")
print(con.sql(f"""
    SELECT 'all orders' AS stage, COUNT(*) AS n FROM {ORDERS}
    UNION ALL SELECT 'delivered', COUNT(*) FROM {ORDERS} WHERE order_status = 'delivered'
    UNION ALL SELECT 'final base', COUNT(*) FROM orders_base
"""))

print("\n=== HEADLINE NUMBERS ===")
print(con.sql("""
    SELECT
        COUNT(*) AS n_orders,
        ROUND(AVG(total_days), 1) AS mean_days,
        MEDIAN(total_days) AS median_days,
        QUANTILE_CONT(total_days, 0.95) AS p95_days,
        ROUND(100.0 * AVG(is_late::INT), 1) AS pct_late,
        ROUND(AVG(promise_error_days), 1) AS mean_promise_error,
        SUM(approval_suspect::INT) AS n_approval_suspect
    FROM orders_base
"""))
