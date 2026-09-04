import duckdb

con = duckdb.connect()

print("\n=== TOP 15 CATEGORIES BY ORDERS SOLD ===")
print(con.sql("""
    SELECT
        COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
        COUNT(*) AS items_sold,
        ROUND(AVG(i.price), 2) AS avg_price_brl,
        ROUND(AVG(p.product_weight_g) / 1000.0, 2) AS avg_weight_kg
    FROM read_csv_auto('data/raw/olist_order_items_dataset.csv') i
    LEFT JOIN read_csv_auto('data/raw/olist_products_dataset.csv') p
        ON i.product_id = p.product_id
    LEFT JOIN read_csv_auto('data/raw/product_category_name_translation.csv') t
        ON p.product_category_name = t.product_category_name
    GROUP BY category
    ORDER BY items_sold DESC
    LIMIT 15

"""))