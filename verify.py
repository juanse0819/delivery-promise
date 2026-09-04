import duckdb

con = duckdb.connect()

result = con.sql("""
SELECT
    COUNT(*)                           AS total_rows,
    COUNT(DISTINCT order_id)           AS unique_orders,
    MIN(order_purchase_timestamp)      AS earliest_purchase,
    MAX(order_purchase_timestamp)      AS latest_purchase,
FROM read_csv_auto('data/raw/olist_orders_dataset.csv')
""")

print(result)