"""
ab_testing.py
-------------
Evaluates the Control / Variant_A / Variant_B experiment_group field.

`experiment_group` is assigned per *event*, not persisted per customer --
99.96% of customers see more than one group across their history (see
data/README.md). A plain two-proportion z-test at the event level
technically violates independence (events from the same customer aren't
independent draws), so this module does two things:

  1. Headline test at the event level -- chi-square across all 3 groups,
     then pairwise z-tests with a Bonferroni correction.
  2. Cross-check via a customer-clustered bootstrap: resample customers
     (not events), so within-customer correlation is preserved instead of
     assumed away. Agreement between the two is evidence the effect isn't
     a pseudo-replication artifact.

Run:
    python -m src.ab_testing
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from src.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GROUPS = ["Control", "Variant_A", "Variant_B"]
N_BOOTSTRAP = 2000
RNG_SEED = 42


@dataclass
class PairwiseResult:
    group_a: str
    group_b: str
    rate_a: float
    rate_b: float
    absolute_lift_pp: float
    z_stat: float
    p_value: float
    bonferroni_alpha: float
    significant: bool


def _load_customer_group_counts() -> pd.DataFrame:
    """One row per (customer_id, experiment_group) with total events and
    purchase events -- the sufficient statistic for both the pooled test
    and the cluster bootstrap."""
    with get_connection() as conn:
        df = pd.read_sql(
            """
            SELECT customer_id, experiment_group,
                   COUNT(*) AS total_events,
                   SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchase_events
            FROM fct_events
            GROUP BY customer_id, experiment_group
            """,
            conn,
        )
    return df


def group_totals(counts: pd.DataFrame = None) -> pd.DataFrame:
    counts = counts if counts is not None else _load_customer_group_counts()
    totals = counts.groupby("experiment_group")[["total_events", "purchase_events"]].sum()
    totals["purchase_rate"] = totals["purchase_events"] / totals["total_events"]
    return totals.reindex(GROUPS)


def chi_square_test(counts: pd.DataFrame = None) -> dict:
    totals = group_totals(counts)
    table = np.array([
        totals["purchase_events"].values,
        (totals["total_events"] - totals["purchase_events"]).values,
    ])
    chi2, p, dof, _ = stats.chi2_contingency(table)
    return {"chi2": chi2, "p_value": p, "dof": dof}


def two_proportion_z(n_a, x_a, n_b, x_b) -> tuple:
    p_a, p_b = x_a / n_a, x_b / n_b
    p_pool = (x_a + x_b) / (n_a + n_b)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    z = (p_b - p_a) / se if se > 0 else 0.0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return p_a, p_b, z, p_value


def pairwise_tests(counts: pd.DataFrame = None) -> list:
    totals = group_totals(counts)
    pairs = [("Control", "Variant_A"), ("Control", "Variant_B"), ("Variant_A", "Variant_B")]
    bonferroni_alpha = 0.05 / len(pairs)

    results = []
    for a, b in pairs:
        n_a, x_a = totals.loc[a, "total_events"], totals.loc[a, "purchase_events"]
        n_b, x_b = totals.loc[b, "total_events"], totals.loc[b, "purchase_events"]
        rate_a, rate_b, z, p = two_proportion_z(n_a, x_a, n_b, x_b)
        results.append(PairwiseResult(
            group_a=a, group_b=b, rate_a=rate_a, rate_b=rate_b,
            absolute_lift_pp=(rate_b - rate_a) * 100,
            z_stat=z, p_value=p, bonferroni_alpha=bonferroni_alpha,
            significant=p < bonferroni_alpha,
        ))
    return results


def cluster_bootstrap_ci(counts: pd.DataFrame = None, n_boot: int = N_BOOTSTRAP, seed: int = RNG_SEED) -> pd.DataFrame:
    """Resample CUSTOMERS (not events) with replacement to get a lift CI
    that accounts for within-customer correlation, rather than treating
    every event as an independent observation."""
    counts = counts if counts is not None else _load_customer_group_counts()

    customer_ids = counts["customer_id"].unique()
    n_customers = len(customer_ids)
    cust_index = {cid: i for i, cid in enumerate(customer_ids)}
    group_index = {g: i for i, g in enumerate(GROUPS)}

    # matrix[customer, group, 0] = total_events, matrix[customer, group, 1] = purchase_events
    matrix = np.zeros((n_customers, len(GROUPS), 2))
    rows = counts["customer_id"].map(cust_index).values
    cols = counts["experiment_group"].map(group_index).values
    matrix[rows, cols, 0] = counts["total_events"].values
    matrix[rows, cols, 1] = counts["purchase_events"].values

    rng = np.random.default_rng(seed)
    lifts_a, lifts_b = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n_customers, size=n_customers)
        summed = matrix[idx].sum(axis=0)  # shape (3, 2)
        rates = summed[:, 1] / summed[:, 0]
        lifts_a.append((rates[1] - rates[0]) * 100)  # Variant_A - Control
        lifts_b.append((rates[2] - rates[0]) * 100)  # Variant_B - Control

    ci = pd.DataFrame({
        "comparison": ["Variant_A vs Control", "Variant_B vs Control"],
        "median_lift_pp": [np.median(lifts_a), np.median(lifts_b)],
        "ci_2.5pct": [np.percentile(lifts_a, 2.5), np.percentile(lifts_b, 2.5)],
        "ci_97.5pct": [np.percentile(lifts_a, 97.5), np.percentile(lifts_b, 97.5)],
    })
    return ci


def run() -> None:
    counts = _load_customer_group_counts()

    totals = group_totals(counts)
    print("=== Purchase rate by experiment_group (event-level) ===")
    print(totals.to_string())

    chi2_result = chi_square_test(counts)
    print(f"\n3-group chi-square test: chi2={chi2_result['chi2']:.2f}, "
          f"p={chi2_result['p_value']:.6g}, dof={chi2_result['dof']}")

    print("\n=== Pairwise z-tests (Bonferroni alpha = 0.0167) ===")
    for r in pairwise_tests(counts):
        sig = "YES" if r.significant else "no"
        print(f"{r.group_a} ({r.rate_a:.2%}) vs {r.group_b} ({r.rate_b:.2%}): "
              f"lift={r.absolute_lift_pp:+.2f}pp, z={r.z_stat:.2f}, p={r.p_value:.4g}, significant={sig}")

    print(f"\n=== Customer-clustered bootstrap ({N_BOOTSTRAP} resamples), robustness check ===")
    ci = cluster_bootstrap_ci(counts)
    print(ci.to_string(index=False))


if __name__ == "__main__":
    run()
