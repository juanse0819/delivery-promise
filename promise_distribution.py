import duckdb

con = duckdb.connect("delivery.duckdb")

print("\n=== PROMISE ERROR PERCENTILES ===")
print(con.sql("""
    SELECT
        MIN(promise_error_days) AS min_error,
        QUANTILE_CONT(promise_error_days, 0.05) AS p05,
        QUANTILE_CONT(promise_error_days, 0.25) AS p25,
        MEDIAN(promise_error_days) AS median_error,
        QUANTILE_CONT(promise_error_days, 0.75) AS p75,
        QUANTILE_CONT(promise_error_days, 0.95) AS p95,
        MAX(promise_error_days) AS max_error
    FROM orders_base
"""))

print("\n=== HOW EARLY, HOW LATE ===")
print(con.sql("""
    SELECT
        CASE
            WHEN promise_error_days <= -20 THEN 'a) 20+ days early'
            WHEN promise_error_days <= -10 THEN 'b) 10-20 days early'
            WHEN promise_error_days <=  -5 THEN 'c) 5-10 days early'
            WHEN promise_error_days <    0 THEN 'd) 1-5 days early'
            WHEN promise_error_days =    0 THEN 'e) exactly on time'
            WHEN promise_error_days <=   5 THEN 'f) 1-5 days late'
            ELSE                              'g) 5+ days late'
        END AS bucket,
        COUNT(*) AS n_orders,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
    FROM orders_base
        GROUP BY bucket
        ORDER BY bucket
"""))
