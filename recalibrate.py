import duckdb

con = duckdb.connect("delivery.duckdb")

TRAIN_END = '2018-03-01'
MIN_LANE = 100

print("\n=== TRAIN / TEST SPLIT ===")
print(con.sql(f"""
    SELECT
        CASE WHEN purchase_date < '{TRAIN_END}' THEN '1_train' ELSE '2_test' END AS split,
        COUNT(*) AS n_orders,
        MIN(purchase_date) AS first_date,
        MAX(purchase_date) AS last_date
    FROM fct_orders
    GROUP BY split ORDER BY split
"""))

print("\n=== LANE COVERAGE BY VOLUME THRESHOLD ===")
print(con.sql(f"""
    WITH tr AS (
        SELECT lane, COUNT(*) AS n_train FROM fct_orders
        WHERE purchase_date < '{TRAIN_END}' GROUP BY lane
    ),
    te AS (
        SELECT lane, COUNT(*) AS n_test FROM fct_orders
        WHERE purchase_date >= '{TRAIN_END}' GROUP BY lane
    ),
    j AS (
        SELECT tr.lane, tr.n_train, COALESCE(te.n_test, 0) AS n_test
        FROM tr LEFT JOIN te ON tr.lane = te.lane
    ),
    tot AS (
        SELECT COUNT(*) AS n FROM fct_orders WHERE purchase_date >= '{TRAIN_END}'
    )
    SELECT
        th.t AS min_orders,
        COUNT(*) FILTER (WHERE j.n_train >= th.t) AS n_lanes,
        SUM(j.n_test) FILTER (WHERE j.n_train >= th.t) AS test_orders_covered,
        ROUND(100.0 * SUM(j.n_test) FILTER (WHERE j.n_train >= th.t) / MAX(tot.n), 1) AS pct_covered
    FROM j, tot, (VALUES (30),(50),(100),(200),(400)) AS th(t)
    GROUP BY th.t ORDER BY th.t
"""))

# ---------- PROMISE LOOKUP TABLES (train only) ----------

for name, key, extra in [
    ("lane_promise", "lane", f"HAVING COUNT(*) >= {MIN_LANE}"),
    ("state_promise", "customer_state", ""),
]:
    con.sql(f"""
    CREATE OR REPLACE TABLE {name} AS
    SELECT
        {key},
        COUNT(*) AS n_train,
        CAST(CEIL(QUANTILE_CONT(total_days, 0.90)) AS INT) AS promise_90,
        CAST(CEIL(QUANTILE_CONT(total_days, 0.92)) AS INT) AS promise_92,
        CAST(CEIL(QUANTILE_CONT(total_days, 0.95)) AS INT) AS promise_95
    FROM fct_orders
    WHERE purchase_date < '{TRAIN_END}'
    GROUP BY {key}
    {extra}
    """)

con.sql(f"""
CREATE OR REPLACE TABLE national_promise AS
SELECT
    CAST(CEIL(QUANTILE_CONT(total_days, 0.90)) AS INT) AS promise_90,
    CAST(CEIL(QUANTILE_CONT(total_days, 0.92)) AS INT) AS promise_92,
    CAST(CEIL(QUANTILE_CONT(total_days, 0.95)) AS INT) AS promise_95
FROM fct_orders WHERE purchase_date < '{TRAIN_END}'
""")

# ---------- APPLY TO HELD-OUT TEST SET ----------

con.sql(f"""
CREATE OR REPLACE TABLE test_eval AS
SELECT
    f.order_id, f.lane, f.customer_state, f.total_days, f.is_late,
    f.total_days - f.promise_error_days AS current_promise_days,
    COALESCE(lp.promise_90, sp.promise_90, np.promise_90) AS new_90,
    COALESCE(lp.promise_92, sp.promise_92, np.promise_92) AS new_92,
    COALESCE(lp.promise_95, sp.promise_95, np.promise_95) AS new_95,
    CASE WHEN lp.lane IS NOT NULL THEN '1_lane'
         WHEN sp.customer_state IS NOT NULL THEN '2_state'
         ELSE '3_national' END AS promise_source
FROM fct_orders f
LEFT JOIN lane_promise lp ON f.lane = lp.lane
LEFT JOIN state_promise sp ON f.customer_state = sp.customer_state
CROSS JOIN national_promise np
WHERE f.purchase_date >= '{TRAIN_END}'
""")

print("\n=== FALLBACK USAGE ON TEST SET ===")
print(con.sql("""
    SELECT promise_source, COUNT(*) AS n_orders,
           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
    FROM test_eval GROUP BY promise_source ORDER BY promise_source
"""))

print("\n=== HEADLINE: DAYS SAVED vs SERVICE LEVEL (out of sample) ===")
print(con.sql("""
    SELECT 'current' AS policy,
        ROUND(AVG(current_promise_days), 1) AS mean_promise_days,
        0.0 AS mean_days_saved,
        ROUND(100.0 * AVG((total_days <= current_promise_days)::INT), 1) AS pct_on_time
    FROM test_eval
    UNION ALL SELECT 'recal_p90',
        ROUND(AVG(new_90), 1), ROUND(AVG(current_promise_days - new_90), 1),
        ROUND(100.0 * AVG((total_days <= new_90)::INT), 1) FROM test_eval
    UNION ALL SELECT 'recal_p92',
        ROUND(AVG(new_92), 1), ROUND(AVG(current_promise_days - new_92), 1),
        ROUND(100.0 * AVG((total_days <= new_92)::INT), 1) FROM test_eval
    UNION ALL SELECT 'recal_p95',
        ROUND(AVG(new_95), 1), ROUND(AVG(current_promise_days - new_95), 1),
        ROUND(100.0 * AVG((total_days <= new_95)::INT), 1) FROM test_eval
"""))

print("\n=== LANE-LEVEL EFFECT AT p95 (top 12 by test volume) ===")
print(con.sql("""
    SELECT lane,
        COUNT(*) AS n_test,
        ROUND(AVG(current_promise_days), 1) AS current_days,
        ROUND(AVG(new_95), 1) AS recal_days,
        ROUND(AVG(current_promise_days - new_95), 1) AS days_saved,
        ROUND(100.0 * AVG((total_days <= current_promise_days)::INT), 1) AS on_time_current,
        ROUND(100.0 * AVG((total_days <= new_95)::INT), 1) AS on_time_recal
    FROM test_eval
    WHERE promise_source = '1_lane'
    GROUP BY lane ORDER BY n_test DESC LIMIT 12
"""))

print("\n=== SERVICE LEVEL DISPERSION ACROSS LANES ===")
print(con.sql("""
    WITH by_lane AS (
        SELECT lane, COUNT(*) AS n,
            100.0 * AVG((total_days <= current_promise_days)::INT) AS ot_current,
            100.0 * AVG((total_days <= new_90)::INT) AS ot_90,
            100.0 * AVG((total_days <= new_95)::INT) AS ot_95
        FROM test_eval
        WHERE promise_source = '1_lane'
        GROUP BY lane HAVING COUNT(*) >= 50
    )
    SELECT 'current' AS policy, ROUND(MIN(ot_current),1) AS worst_lane,
    ROUND(MAX(ot_current),1) AS best_lane,
        ROUND(MAX(ot_current)-MIN(ot_current),1) AS spread,
        ROUND(STDDEV(ot_current),2) AS stddev FROM by_lane
    UNION ALL SELECT 'recal_p90', ROUND(MIN(ot_90),1), ROUND(MAX(ot_90),1),
        ROUND(MAX(ot_90)-MIN(ot_90),1), ROUND(STDDEV(ot_90),2) FROM by_lane
    UNION ALL SELECT 'recal_p95', ROUND(MIN(ot_95),1), ROUND(MAX(ot_95),1),
        ROUND(MAX(ot_95)-MIN(ot_95),1), ROUND(STDDEV(ot_95),2) FROM by_lane
"""))