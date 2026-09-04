import duckdb

con = duckdb.connect("delivery.duckdb")

ITEMS = "read_csv_auto('data/raw/olist_order_items_dataset.csv')"
SELLERS = "read_csv_auto('data/raw/olist_sellers_dataset.csv')"

con.sql(f"""
CREATE OR REPLACE TABLE order_seller_profile AS
SELECT
    b.order_id,
    COUNT(*) AS n_items,
    COUNT(DISTINCT i.seller_id) AS n_sellers,
    COUNT(DISTINCT s.seller_state) AS n_seller_states
FROM orders_base b
JOIN {ITEMS} i ON b.order_id = i.order_id
LEFT JOIN {SELLERS} s ON i.seller_id = s.seller_id
GROUP BY b.order_id
""")

print("\n=== COVERAGE CHECK ===")
print(con.sql("""
    SELECT
        (SELECT COUNT(*) FROM orders_base) AS orders_in_base,
        (SELECT COUNT(*) FROM order_seller_profile) AS orders_with_items,
        (SELECT COUNT(*) FROM orders_base)
          - (SELECT COUNT(*) FROM order_seller_profile) AS orders_missing_items
"""))

print("\n=== HOW MANY SELLERS PER ORDER? ===")
print(con.sql("""
    SELECT
        n_sellers,
        COUNT(*) AS n_orders,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM order_seller_profile
    GROUP BY n_sellers
    ORDER BY n_sellers
"""))

print("\n=== HOW MANY SELLER STATES PER ORDER? ===")
print(con.sql("""
    SELECT
        n_seller_states,
        COUNT(*) AS n_orders,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM order_seller_profile
    GROUP BY n_seller_states
    ORDER BY n_seller_states
"""))

print("\n=== DOES MULTI-SELLER CHANGE DELIVERY BEHAVIOR? ===")
print(con.sql("""
    SELECT
        CASE WHEN p.n_sellers = 1 THEN 'single seller'
             ELSE 'multi seller' END AS grp,
        COUNT(*) AS n_orders,
        ROUND(MEDIAN(s.transit_days), 1) AS median_transit,
        ROUND(QUANTILE_CONT(s.transit_days, 0.95), 1) AS p95_transit,
        ROUND(100.0 * AVG(s.is_late::INT), 1) AS pct_late
    FROM order_seller_profile p
    JOIN orders_segments s ON p.order_id = s.order_id
    WHERE NOT s.approval_suspect
    GROUP BY grp
"""))