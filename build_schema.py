import duckdb

con = duckdb.connect("delivery.duckdb")

CUSTOMERS = "read_csv_auto('data/raw/olist_customers_dataset.csv')"
SELLERS = "read_csv_auto('data/raw/olist_sellers_dataset.csv')"
ITEMS = "read_csv_auto('data/raw/olist_order_items_dataset.csv')"

# ---------- DIMENSIONS ----------

con.sql(f"""
CREATE OR REPLACE TABLE dim_customer_geo AS
SELECT
    customer_id,
    customer_state,
    customer_city,
    customer_zip_code_prefix
FROM {CUSTOMERS}
""")

con.sql(f"""
CREATE OR REPLACE TABLE dim_seller_geo AS
SELECT
    seller_id,
    seller_state,
    seller_city,
    seller_zip_code_prefix
FROM {SELLERS}
""")

# ---------- ORIGIN ASSIGNMENT ----------
# One row per order: the seller whose item shipped last.
# QUALIFY filters on a window function without a subquery.

con.sql(f"""
CREATE OR REPLACE TABLE order_origin AS
SELECT
    order_id,
    seller_id,
    n_sellers,
    n_seller_states
FROM (
    SELECT
        i.order_id,
        i.seller_id,
        COUNT(DISTINCT i.seller_id) OVER (PARTITION BY i.order_id) AS n_sellers,
        COUNT(DISTINCT s.seller_state) OVER (PARTITION BY i.order_id) AS n_seller_states
    FROM {ITEMS} i
    LEFT JOIN {SELLERS} s ON i.seller_id = s.seller_id
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY i.order_id
        ORDER BY i.shipping_limit_date DESC, i.seller_id
    ) = 1
)
""")

# ---------- FACT TABLE ----------

con.sql("""
CREATE OR REPLACE TABLE fct_orders AS
SELECT
    b.order_id,
    b.customer_id,
    o.seller_id,
    CAST(b.purchased_at AS DATE) AS purchase_date,

    c.customer_state,
    sg.seller_state,
    sg.seller_state || ' -> ' || c.customer_state AS lane,
    (sg.seller_state = c.customer_state) AS is_intrastate,

    b.total_days,
    s.approval_days,
    s.handoff_days,
    s.transit_days,
    b.promise_error_days,
    b.is_late,
    b.approval_suspect,

    o.n_sellers,
    o.n_seller_states,
    (o.n_seller_states > 1) AS origin_ambiguous
FROM orders_base b
JOIN orders_segments s ON b.order_id = s.order_id
JOIN order_origin o ON b.order_id = o.order_id
LEFT JOIN dim_customer_geo c ON b.customer_id = c.customer_id
LEFT JOIN dim_seller_geo sg ON o.seller_id = sg.seller_id
""")

# ---------- VALIDATION ----------

print("\n=== ROW COUNT INTEGRITY ===")
print(con.sql("""
    SELECT
        (SELECT COUNT(*) FROM orders_base) AS base_rows,
        (SELECT COUNT(*) FROM fct_orders) AS fact_rows,
        (SELECT COUNT(DISTINCT order_id) FROM fct_orders) AS distinct_orders,
        (SELECT COUNT(*) FROM fct_orders WHERE customer_state IS NULL) AS null_cust_state,
        (SELECT COUNT(*) FROM fct_orders WHERE seller_state IS NULL) AS null_sell_state
"""))

print("\n=== LANE COVERAGE ===")
print(con.sql("""
    SELECT
        COUNT(DISTINCT lane) AS n_lanes,
        SUM(is_intrastate::INT) AS intrastate_orders,
        ROUND(100.0 * AVG(is_intrastate::INT), 1) AS pct_intrastate,
        SUM(origin_ambiguous::INT) AS ambiguous_origin_orders
    FROM fct_orders
"""))

print("\n=== TOP 12 LANES BY VOLUME ===")
print(con.sql("""
    SELECT
        lane,
        COUNT(*) AS n_orders,
        ROUND(MEDIAN(transit_days), 1) AS median_transit,
        ROUND(QUANTILE_CONT(transit_days, 0.95), 1) AS p95_transit,
        ROUND(MEDIAN(promise_error_days), 1) AS median_promise_error,
        ROUND(100.0 * AVG(is_late::INT), 1) AS pct_late
    FROM fct_orders
    WHERE NOT approval_suspect
    GROUP BY lane
    ORDER BY n_orders DESC
    LIMIT 12
"""))

print("\n=== VARIANCE EXPLAINED: DESTINATION ONLY vs FULL LANE ===")
print(con.sql("""
    WITH dest AS (
        SELECT customer_state, MEDIAN(transit_days) AS med
        FROM fct_orders WHERE NOT approval_suspect
        GROUP BY customer_state
    ),
    lane AS (
        SELECT lane, MEDIAN(transit_days) AS med
        FROM fct_orders WHERE NOT approval_suspect
        GROUP BY lane
    )
    SELECT
        ROUND(VAR_POP(f.transit_days), 2) AS total_variance,
        ROUND(100.0 * (1 - VAR_POP(f.transit_days - d.med)
                         / VAR_POP(f.transit_days)), 1) AS pct_explained_dest_only,
        ROUND(100.0 * (1 - VAR_POP(f.transit_days - l.med)
                         / VAR_POP(f.transit_days)), 1) AS pct_explained_full_lane
    FROM fct_orders f
    JOIN dest d ON f.customer_state = d.customer_state
    JOIN lane l ON f.lane = l.lane
    WHERE NOT f.approval_suspect
"""))