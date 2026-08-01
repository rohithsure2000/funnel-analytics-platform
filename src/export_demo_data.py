"""
export_demo_data.py
--------------------
Exports small, precomputed result tables to dashboard/demo_data/ so the
dashboard can run in "demo mode" without the real dataset present --
e.g. for a Streamlit Community Cloud deployment, where bundling the real
~200MB licensed dataset isn't practical or appropriate.

This does NOT replace the real pipeline -- it's a snapshot of results
*produced by* the real pipeline, for display purposes only. Run it once,
locally, after `python -m src.pipeline` has populated the real warehouse:

    python -m src.export_demo_data

The output files are small (a few KB total) and are committed to the
repo, unlike the raw CSVs / warehouse.db.
"""

import json
import logging
import os

from src.ab_testing import (
    _load_customer_group_counts, chi_square_test, cluster_bootstrap_ci, group_totals, pairwise_tests,
)
from src.funnel_analysis import (
    bounce_rate, customer_step_reach, funnel_by_channel, overall_funnel, revenue_per_converted_customer,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "demo_data")


def run() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    reach = customer_step_reach()
    overall = overall_funnel(reach)
    overall.to_csv(os.path.join(OUT_DIR, "funnel_overall.csv"), index=False)

    by_channel = funnel_by_channel(reach)
    by_channel.to_csv(os.path.join(OUT_DIR, "funnel_by_channel.csv"), index=False)

    counts = _load_customer_group_counts()
    totals = group_totals(counts).reset_index()
    totals.to_csv(os.path.join(OUT_DIR, "ab_test_totals.csv"), index=False)

    pairwise = [
        {
            "group_a": r.group_a, "group_b": r.group_b,
            "rate_a": float(r.rate_a), "rate_b": float(r.rate_b),
            "absolute_lift_pp": float(r.absolute_lift_pp),
            "z_stat": float(r.z_stat), "p_value": float(r.p_value),
            "significant": bool(r.significant),
        }
        for r in pairwise_tests(counts)
    ]
    with open(os.path.join(OUT_DIR, "ab_test_pairwise.json"), "w") as f:
        json.dump(pairwise, f, indent=2)

    bootstrap = cluster_bootstrap_ci(counts)
    bootstrap.to_csv(os.path.join(OUT_DIR, "ab_test_bootstrap.csv"), index=False)

    chi2 = chi_square_test(counts)
    summary = {
        "chi2": float(chi2["chi2"]),
        "chi2_p_value": float(chi2["p_value"]),
        "chi2_dof": int(chi2["dof"]),
        "bounce_rate_pct": float(bounce_rate()),
        "avg_revenue_per_converted_customer": float(revenue_per_converted_customer()),
        "total_customers": int(overall.loc[0, "customers_reached"]),
    }
    with open(os.path.join(OUT_DIR, "summary_stats.json"), "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("Exported demo data to %s", OUT_DIR)


if __name__ == "__main__":
    run()
