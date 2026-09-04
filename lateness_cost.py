import duckdb

con = duckdb.connect("delivery.duckdb")

ORDERS = "read_csv_auto('data/raw/olist_orders_dataset.csv')"
CUSTOMERS = "read_csv_auto('data/raw/olist_customers_dataset.csv')"
REVIEWS = "read_csv_auto('data/raw/olist_order_reviews_dataset.csv')"
PAYMENTS = "read_csv_auto('data/raw/olist_order_payments_dataset.csv')"

con.sql(f"""
CREATE OR REPLACE TABLE order_outcomes AS
SELECT
    f.order_id,
    c.customer_unique_id,
    f.purchase_date,
    f.total_days,
    f.promise_error_days,
    f.is_late,
    r.review_score,
    p.order_value
FROM fct_orders f
LEFT JOIN {CUSTOMERS} c ON f.customer_id = c.customer_id
LEFT JOIN (
    SELECT order_id, review_score FROM {REVIEWS}
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY order_id ORDER BY review_creation_date DESC) = 1
) r ON f.order_id = r.order_id
LEFT JOIN (
    SELECT order_id, SUM(payment_value) AS order_value
    FROM {PAYMENTS} GROUP BY order_id
) p ON f.order_id = p.order_id
""")

print("\n=== COVERAGE ===")
print(con.sql("""
    SELECT COUNT(*) AS n_orders,
        COUNT(review_score) AS has_review,
        COUNT(order_value) AS has_value,
        COUNT(customer_unique_id) AS has_customer
    FROM order_outcomes
"""))

print("\n=== REVIEW SCORE: LATE vs ON TIME ===")
print(con.sql("""
    SELECT is_late,
        COUNT(*) AS n_orders,
        ROUND(AVG(review_score), 2) AS mean_score,
        ROUND(100.0 * AVG((review_score = 1)::INT), 1) AS pct_1_star,
        ROUND(100.0 * AVG((review_score <= 2)::INT), 1) AS pct_1_or_2,
        ROUND(100.0 * AVG((review_score = 5)::INT), 1) AS pct_5_star
    FROM order_outcomes WHERE review_score IS NOT NULL
    GROUP BY is_late
"""))

print("\n=== DOSE RESPONSE: HOW LATE vs SCORE ===")
print(con.sql("""
    SELECT
        CASE
            WHEN promise_error_days <= -10 THEN 'a) 10+ days early'
            WHEN promise_error_days <   0  THEN 'b) 1-9 days early'
            WHEN promise_error_days =   0  THEN 'c) on time'
            WHEN promise_error_days <=  3  THEN 'd) 1-3 days late'
            WHEN promise_error_days <=  7  THEN 'e) 4-7 days late'
            WHEN promise_error_days <= 14  THEN 'f) 8-14 days late'
            ELSE                                'g) 15+ days late'
        END AS bucket,
        COUNT(*) AS n_orders,
        ROUND(AVG(review_score), 2) AS mean_score,
        ROUND(100.0 * AVG((review_score = 1)::INT), 1) AS pct_1_star
    FROM order_outcomes WHERE review_score IS NOT NULL
    GROUP BY bucket ORDER BY bucket
"""))

print("\n=== REPEAT PURCHASE WITHIN 90 DAYS OF FIRST ORDER ===")
print(con.sql(f"""
    WITH all_cust AS (
        SELECT c.customer_unique_id,
               CAST(o.order_purchase_timestamp AS DATE) AS pdate
        FROM {ORDERS} o
        JOIN {CUSTOMERS} c ON o.customer_id = c.customer_id
    ),
    first_o AS (
        SELECT customer_unique_id, purchase_date, is_late
        FROM order_outcomes
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY purchase_date, order_id) = 1
    ),
    windowed AS (
        SELECT f.customer_unique_id, f.is_late, COUNT(a.pdate) AS n_repeat
        FROM first_o f
        LEFT JOIN all_cust a
          ON a.customer_unique_id = f.customer_unique_id
         AND a.pdate > f.purchase_date
         AND a.pdate <= f.purchase_date + INTERVAL 90 DAY
        WHERE f.purchase_date <= DATE '2018-06-01'
        GROUP BY f.customer_unique_id, f.is_late
    )
    SELECT is_late, COUNT(*) AS n_customers,
        ROUND(100.0 * AVG((n_repeat > 0)::INT), 2) AS pct_repeat_90d
    FROM windowed GROUP BY is_late
"""))

print("\n=== REVENUE EXPOSED TO LATENESS ===")
print(con.sql("""
    SELECT is_late,
        COUNT(*) AS n_orders,
        ROUND(SUM(order_value), 0) AS total_brl,
        ROUND(AVG(order_value), 2) AS mean_order_brl,
        ROUND(100.0 * SUM(order_value) / SUM(SUM(order_value)) OVER (), 1) AS pct_of_revenue
    FROM order_outcomes WHERE order_value IS NOT NULL
    GROUP BY is_late
"""))