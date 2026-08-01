"""
dashboard/app.py
-----------------
Interactive Streamlit dashboard for the customer lifecycle funnel and the
Control / Variant_A / Variant_B experiment. Plays the role Tableau / Power
BI would play against the same warehouse tables in production (see README
"Connecting a real BI tool" section).

Run:
    streamlit run dashboard/app.py
"""

import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ab_testing import _load_customer_group_counts, chi_square_test, group_totals, pairwise_tests
from src.funnel_analysis import (
    bounce_rate, customer_step_reach, funnel_by_channel, overall_funnel,
    revenue_per_converted_customer,
)

st.set_page_config(page_title="Marketing Funnel & Experiment Analytics", layout="wide")

st.title("Marketing & E-Commerce Funnel Analytics")
st.caption(
    "Built on the real Kaggle 'Marketing & E-Commerce Analytics Dataset' "
    "(Geetha Sagar Bonthu, CC0) -- see data/README.md for source & citation."
)

reach = customer_step_reach()
overall = overall_funnel(reach)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total customers", f"{overall.loc[0, 'customers_reached']:,}")
col2.metric("Ever purchased", f"{overall.loc[len(overall)-1, 'customers_reached']:,}",
            f"{overall.loc[len(overall)-1, 'pct_of_customers']}% of customers")
worst_row = overall.iloc[1:].sort_values("drop_off_pct", ascending=False).iloc[0]
col3.metric("Biggest drop-off stage", worst_row["step_name"], f"-{worst_row['drop_off_pct']}%")
col4.metric("Avg. revenue / converted customer", f"${revenue_per_converted_customer():,.2f}")

st.subheader("Customer lifecycle funnel")
st.caption(
    "Not a per-visit funnel -- the source data has no recoverable session "
    "structure (median 36-day gap between a customer's events), so this "
    "tracks whether a customer EVER reached each stage. See data/README.md."
)
fig_funnel = go.Figure(go.Funnel(
    y=overall["step_name"],
    x=overall["customers_reached"],
    textinfo="value+percent initial",
))
st.plotly_chart(fig_funnel, use_container_width=True)
st.caption(f"Bounce rate (share of all events that are 'bounce'): {bounce_rate()}%")

st.subheader("Ever-purchased rate by acquisition channel")
by_channel = funnel_by_channel(reach)
purchased_by_channel = by_channel[by_channel["step_name"] == "purchase"].sort_values(
    "pct_of_signups", ascending=False
)
fig_channel = px.bar(
    purchased_by_channel, x="pct_of_signups", y="acquisition_channel",
    orientation="h", labels={"pct_of_signups": "% of customers who ever purchased", "acquisition_channel": "Channel"},
)
st.plotly_chart(fig_channel, use_container_width=True)

st.subheader("Experiment: Control vs. Variant_A vs. Variant_B")
st.caption(
    "experiment_group is assigned per-event, not persisted per customer -- "
    "tested at the event level with a customer-clustered bootstrap as a "
    "robustness check. See src/ab_testing.py for the full treatment."
)

counts = _load_customer_group_counts()
totals = group_totals(counts)
chi2 = chi_square_test(counts)

c1, c2, c3 = st.columns(3)
for col, group in zip([c1, c2, c3], ["Control", "Variant_A", "Variant_B"]):
    col.metric(group, f"{totals.loc[group, 'purchase_rate']:.2%}",
               f"n={int(totals.loc[group, 'total_events']):,} events")

st.caption(f"3-group chi-square: χ²={chi2['chi2']:.1f}, p={chi2['p_value']:.2g}")

pairwise_df = pd.DataFrame([
    {
        "Comparison": f"{r.group_a} vs {r.group_b}",
        "Lift (pp)": round(r.absolute_lift_pp, 2),
        "p-value": f"{r.p_value:.2g}",
        "Significant (Bonferroni)": "Yes" if r.significant else "No",
    }
    for r in pairwise_tests(counts)
])
st.dataframe(pairwise_df, use_container_width=True, hide_index=True)

st.subheader("Funnel detail table")
st.dataframe(overall, use_container_width=True, hide_index=True)
