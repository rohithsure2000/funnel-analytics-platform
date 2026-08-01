"""
funnel_analysis.py
-------------------
Customer-lifecycle funnel analysis.

Note on methodology: an earlier version of this analysis assumed a
per-visit ("session") funnel. We checked that empirically (see
src/sessionize.py and data/README.md) and found the source data has no
recoverable session structure -- a given customer's events are spread
with a median 36-day gap, not clustered into visits. So this funnel asks
a different, still standard, question: across a customer's *entire*
history, did they ever reach each successive stage? (view -> click ->
add_to_cart -> purchase). `bounce` is tracked separately as a rate, not
a funnel step, since it's a terminal non-progression outcome rather than
a stage customers pass through.

Run:
    python -m src.funnel_analysis
"""

import logging
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

STEP_ORDER = ["view", "click", "add_to_cart", "purchase"]
FIGURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "figures")


def _read_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    with get_connection() as conn:
        events = pd.read_sql(
            "SELECT customer_id, event_type FROM fct_events", conn
        )
        customers = pd.read_sql(
            "SELECT customer_id, acquisition_channel FROM dim_customers", conn
        )
    return events, customers


def customer_step_reach(events: pd.DataFrame = None) -> pd.DataFrame:
    """One row per customer, one boolean column per funnel step: did this
    customer ever have an event of that type?"""
    events = events if events is not None else _read_data()[0]
    reach = (
        events[events["event_type"].isin(STEP_ORDER)]
        .assign(reached=True)
        .pivot_table(index="customer_id", columns="event_type", values="reached", aggfunc="any", fill_value=False)
        .reindex(columns=STEP_ORDER, fill_value=False)
    )
    return reach


def overall_funnel(reach: pd.DataFrame = None) -> pd.DataFrame:
    reach = reach if reach is not None else customer_step_reach()
    counts = reach[STEP_ORDER].sum()
    total = len(reach)

    result = pd.DataFrame({"step_name": STEP_ORDER, "customers_reached": counts.values})
    result["pct_of_customers"] = (result["customers_reached"] / total * 100).round(2)
    result["step_over_step_pct"] = (
        result["customers_reached"] / result["customers_reached"].shift(1) * 100
    ).round(2)
    result.loc[0, "step_over_step_pct"] = 100.0
    result["drop_off_pct"] = (100 - result["step_over_step_pct"]).round(2)
    return result


def bounce_rate(events: pd.DataFrame = None) -> float:
    events = events if events is not None else _read_data()[0]
    return round((events["event_type"] == "bounce").mean() * 100, 2)


def funnel_by_channel(reach: pd.DataFrame = None, customers: pd.DataFrame = None) -> pd.DataFrame:
    if reach is None or customers is None:
        events, customers = _read_data()
        reach = customer_step_reach(events)

    merged = reach.merge(customers.set_index("customer_id"), left_index=True, right_index=True)
    rows = []
    for channel, grp in merged.groupby("acquisition_channel"):
        total = len(grp)
        for step in STEP_ORDER:
            rows.append({
                "acquisition_channel": channel,
                "step_name": step,
                "customers_reached": int(grp[step].sum()),
                "pct_of_signups": round(grp[step].sum() / total * 100, 2),
            })
    result = pd.DataFrame(rows)
    result["step_name"] = pd.Categorical(result["step_name"], categories=STEP_ORDER, ordered=True)
    return result.sort_values(["acquisition_channel", "step_name"])


def revenue_per_converted_customer() -> float:
    with get_connection() as conn:
        row = pd.read_sql(
            """
            SELECT AVG(customer_total) AS avg_revenue FROM (
                SELECT customer_id, SUM(gross_revenue) AS customer_total
                FROM fct_transactions
                WHERE refund_flag = 0 AND gross_revenue IS NOT NULL
                GROUP BY customer_id
            )
            """,
            conn,
        )
    return round(float(row["avg_revenue"].iloc[0]), 2)


def biggest_drop_off_step(overall: pd.DataFrame = None) -> dict:
    overall = overall if overall is not None else overall_funnel()
    worst = overall.iloc[1:].sort_values("drop_off_pct", ascending=False).iloc[0]
    return {"step_name": worst["step_name"], "drop_off_pct": float(worst["drop_off_pct"])}


def plot_overall_funnel(overall: pd.DataFrame = None, out_path: str = None) -> str:
    overall = overall if overall is not None else overall_funnel()
    out_path = out_path or os.path.join(FIGURES_DIR, "overall_funnel.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(overall["step_name"], overall["customers_reached"], color="#3b6fa0")
    ax.set_title("Customer Lifecycle Funnel: Ever Reached Each Stage")
    ax.set_ylabel("Distinct customers")
    ax.set_xlabel("Funnel stage")
    for bar, pct in zip(bars, overall["pct_of_customers"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{pct}%",
                 ha="center", va="bottom", fontsize=9)
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Saved funnel chart to %s", out_path)
    return out_path


def plot_channel_conversion(by_channel: pd.DataFrame = None, out_path: str = None) -> str:
    by_channel = by_channel if by_channel is not None else funnel_by_channel()
    out_path = out_path or os.path.join(FIGURES_DIR, "channel_conversion.png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    purchased = by_channel[by_channel["step_name"] == "purchase"].sort_values("pct_of_signups", ascending=False)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(purchased["acquisition_channel"], purchased["pct_of_signups"], color="#5aa06d")
    ax.set_title("Ever-Purchased Rate by Acquisition Channel")
    ax.set_xlabel("% of customers who ever purchased")
    plt.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("Saved channel chart to %s", out_path)
    return out_path


def run() -> None:
    events, customers = _read_data()
    reach = customer_step_reach(events)

    overall = overall_funnel(reach)
    print("\n=== Customer Lifecycle Funnel ===")
    print(overall.to_string(index=False))
    print(f"\nBounce rate (share of all events that are 'bounce'): {bounce_rate(events)}%")

    worst = biggest_drop_off_step(overall)
    print(f"Biggest drop-off: {worst['step_name']} ({worst['drop_off_pct']}% lost)")

    print(f"Avg. lifetime revenue per converted customer: ${revenue_per_converted_customer()}")

    by_channel = funnel_by_channel(reach, customers)
    plot_overall_funnel(overall)
    plot_channel_conversion(by_channel)


if __name__ == "__main__":
    run()
