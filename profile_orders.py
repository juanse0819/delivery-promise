import duckdb

con = duckdb.connect()
ORDERS = "read_csv_auto('data/raw/olist_orders_dataset.csv')"

print("\n=== 1. ORDER STATUS BREAKDOWN ===")
print(con.sql(f"""
    SELECT
        order_status,
        COUNT(*)                                            AS n_orders,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM {ORDERS}
    GROUP BY order_status
    ORDER BY n_orders DESC
"""))

print("\n=== 2. TIMESTAMP COMPLETNESS (delivered orders only) ===")
print(con.sql(f"""
    SELECT
        COUNT(*) AS delivered_orders,
        COUNT(order_approved_at) AS has_approved,
        COUNT(order_delivered_carrier_date) AS has_carrier,
        COUNT(order_delivered_customer_date) AS has_customer,
        COUNT(order_estimated_delivery_date) AS has_estimate
    FROM {ORDERS}
    WHERE order_status = 'delivered'    
"""))

print("\n=== 3. LOGICAL ORDERING VIOLATIONS (delivered orders only) ===")
print(con.sql(f"""
    SELECT
        COUNT(*) FILTER (WHERE order_approved_at < order_purchase_timestamp)
            AS approved_before_purchase,
        COUNT(*) FILTER (WHERE order_delivered_carrier_date < order_approved_at)
            AS Shipped_before_approved,
        COUNT(*) FILTER (WHERE order_delivered_customer_date < order_delivered_carrier_date)
              AS delivered_before_shipped
    FROM {ORDERS}
    WHERE order_status = 'delivered'
"""))

print("\n=== 4. MONTHLY ORDER VOLUME ===")
print(con.sql(f"""
    SELECT
        strftime(order_purchase_timestamp, '%Y-%m') AS month,
        COUNT(*) AS n_orders
    FROM {ORDERS}
    GROUP BY month
    ORDER BY month
"""))
