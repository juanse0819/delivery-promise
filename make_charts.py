import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

con = duckdb.connect("delivery.duckdb")
OUT = "outputs/charts"

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.axisbelow": True,
})

BLUE, ORANGE, GREY, PURPLE = "#4C72B0", "#DD8452", "#B0B0B0", "#8172B3"


def finish(fig, ax_or_axes, path, subtitle=None):
    axes = ax_or_axes if isinstance(ax_or_axes, (list, tuple)) else [ax_or_axes]
    for ax in axes:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    if subtitle:
        fig.text(0.5, -0.02, subtitle, ha="center", fontsize=9, color="#666666")
    fig.tight_layout()
    fig.savefig(f"{OUT}/{path}", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path}")


# ---------- REGRESSION CHECK ----------
print("\n=== LANES WHERE RECALIBRATION MADE THINGS WORSE ===")
print(con.sql("""
    SELECT lane, COUNT(*) AS n,
        ROUND(100.0 * AVG((total_days <= current_promise_days)::INT), 1) AS ot_current,
        ROUND(100.0 * AVG((total_days <= new_95)::INT), 1) AS ot_recal
    FROM test_eval WHERE promise_source = '1_lane'
    GROUP BY lane 
    HAVING COUNT(*) >= 100
        AND AVG((total_days <= new_95)::INT) < AVG((total_days <= current_promise_days)::INT)
    ORDER BY ot_recal - ot_current
"""))


# ---------- 1. PROMISE ERROR DISTRIBUTION ----------
d = con.sql("""
    SELECT promise_error_days FROM fct_orders
    WHERE promise_error_days BETWEEN -45 AND 25
""").df()

fig, ax = plt.subplots(figsize=(10, 6))
ax.hist(d["promise_error_days"], bins=71, color=BLUE, edgecolor="white", linewidth=0.3)
ax.axvline(0, color="#333333", linewidth=1.5)
ax.text(0.5, 0.97, "promised date", transform=ax.get_xaxis_transform(),
        rotation=90, va="top", fontsize=9, color="#333333")
ax.axvline(-11.8, color=ORANGE, linestyle="--", linewidth=2, label="mean: 11.8 days early")
ax.set_title("Two-thirds of orders arrive 10 or more days before the promised date")
ax.set_xlabel("Days early (negative) or late (positive)")
ax.set_ylabel("Orders")
ax.legend()
finish(fig, ax, "01_promise_error_distribution.png",
       "96,174 delivered orders, Jan 2017 - Aug 2018. Excludes 0.4% beyond ±45 days.")


# ---------- 2. LEAD TIME DECOMPOSITION ----------
d = con.sql("""
    SELECT is_late,
        MEDIAN(approval_days) AS approval,
        MEDIAN(handoff_days) AS handoff,
        MEDIAN(transit_days) AS transit
    FROM fct_orders WHERE NOT approval_suspect
    GROUP BY is_late ORDER BY is_late
""").df()

labels = ["On time", "Late"]
fig, ax = plt.subplots(figsize=(10, 3.8))
left = [0.0, 0.0]
for col, color, name in [("approval", GREY, "Payment approval (<0.1d)"),
                         ("handoff", PURPLE, "Seller handoff"),
                         ("transit", ORANGE, "Carrier transit")]:
    vals = d[col].tolist()
    ax.barh(labels, vals, left=left, color=color, label=name, height=0.55)
    for i, v in enumerate(vals):
        if v > 0.6:
            ax.text(left[i] + v / 2, i, f"{v:.1f}d", ha="center", va="center",
                    color="white", fontweight="bold", fontsize=10)
    left = [left[i] + vals[i] for i in range(2)]

ax.set_title("Transit time — not payment or seller handoff — separates late from on-time orders")
ax.set_xlabel("Median days")
ax.legend(loc="lower right", framealpha=0.95)
finish(fig, ax, "02_lead_time_decomposition.png",
       "Approval time is identical (0.04 days) for both groups; transit differs 3.4x.")


# ---------- 3. TAIL SPREAD VS LATENESS ----------
d = con.sql("""
    SELECT lane,
        COUNT(*) AS n,
        QUANTILE_CONT(transit_days, 0.95) - MEDIAN(transit_days) AS tail_spread,
        100.0 * AVG(is_late::INT) AS pct_late,
        MEDIAN(transit_days) AS median_transit
    FROM fct_orders WHERE NOT approval_suspect
    GROUP BY lane HAVING COUNT(*) >= 150
""").df()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5), sharey=True)
ax1.scatter(d["median_transit"], d["pct_late"], s=d["n"] / 60, color=GREY,
            edgecolor="#888888", alpha=0.85)
ax1.set_title("Distance: no clear pattern", fontsize=12)
ax1.set_xlabel("Median transit (days)")
ax1.set_ylabel("% of orders late")

ax2.scatter(d["tail_spread"], d["pct_late"], s=d["n"] / 60, color=BLUE,
            edgecolor="#2F4F7F", alpha=0.85)
ax2.set_title("Unpredictability: clear relationship", fontsize=12)
ax2.set_xlabel("Tail spread: p95 − median transit (days)")

fig.suptitle("Lateness tracks how unpredictable a lane is, not how far it goes",
             fontsize=14, fontweight="bold")
finish(fig, [ax1, ax2], "03_tail_spread_vs_lateness.png",
       "Each point is one origin-destination lane with 150+ orders. Point size = order volume.")


# ---------- 4. SERVICE LEVEL EQUALIZATION ----------
d = con.sql("""
    SELECT lane,
        100.0 * AVG((total_days <= current_promise_days)::INT) AS ot_current,
        100.0 * AVG((total_days <= new_95)::INT) AS ot_recal
    FROM test_eval WHERE promise_source = '1_lane'
    GROUP BY lane HAVING COUNT(*) >= 100
    ORDER BY ot_current
    LIMIT 20
""").df()

y = range(len(d))
fig, ax = plt.subplots(figsize=(10, 7))
ax.hlines(y, d["ot_current"], d["ot_recal"], color="#DDDDDD", linewidth=2.5, zorder=1)
ax.scatter(d["ot_current"], y, color=GREY, s=70, zorder=3, label="Current policy")
ax.scatter(d["ot_recal"], y, color=BLUE, s=70, zorder=3, label="Recalibrated (p95)")
ax.set_yticks(list(y))
ax.set_yticklabels(d["lane"], fontsize=10)
ax.set_xlabel("% of orders on time")
ax.set_title("The 20 worst-served lanes gain the most from recalibration")
ax.legend(loc="lower right", framealpha=0.95)
ax.grid(axis="y", visible=False)
finish(fig, ax, "04_service_level_equalization.png",
       "Held-out test set, Mar-Aug 2018. Across all 48 qualifying lanes, "
       "std dev of on-time rate falls from 6.05 to 2.22.")


# ---------- 5. REVIEW SCORE BY DELIVERY TIMING ----------
d = con.sql("""
    SELECT
        CASE
            WHEN promise_error_days <= -10 THEN 'a) 10+ early'
            WHEN promise_error_days <   0  THEN 'b) 1-9 early'
            WHEN promise_error_days =   0  THEN 'c) on time'
            WHEN promise_error_days <=  3  THEN 'd) 1-3 late'
            WHEN promise_error_days <=  7  THEN 'e) 4-7 late'
            WHEN promise_error_days <= 14  THEN 'f) 8-14 late'
            ELSE                                'g) 15+ late'
        END AS bucket,
        AVG(review_score) AS mean_score
    FROM order_outcomes WHERE review_score IS NOT NULL
    GROUP BY bucket ORDER BY bucket
""").df()

names = [b[3:] for b in d["bucket"]]
colors = [GREY, GREY, GREY, ORANGE, ORANGE, ORANGE, ORANGE]
fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(names, d["mean_score"], color=colors, edgecolor="white")
for b, v in zip(bars, d["mean_score"]):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.07, f"{v:.2f}",
            ha="center", fontsize=10, fontweight="bold")
ax.set_ylim(0, 5)
ax.set_title("Arriving early earns nothing; arriving late costs everything")
ax.set_xlabel("Delivery timing vs promise (days)")
ax.set_ylabel("Mean review score (1-5)")
finish(fig, ax, "05_review_score_by_timing.png",
       "95,531 reviewed orders. Nine extra days early is worth +0.09; a 1-3 day miss costs -0.94.")

print("\nAll charts written to outputs/charts/")