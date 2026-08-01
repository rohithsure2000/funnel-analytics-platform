import pandas as pd
import pytest

from src.ab_testing import chi_square_test, group_totals, pairwise_tests, two_proportion_z


@pytest.fixture
def toy_counts():
    """Hand-crafted per-(customer, group) counts with a known, large
    Control vs Variant_B difference and no real Control vs Variant_A
    difference, so the pairwise significance pattern is predictable."""
    rows = [
        # Control: 1000 events, 50 purchases (5%)
        (1, "Control", 500, 25), (2, "Control", 500, 25),
        # Variant_A: 1000 events, 51 purchases (~5.1%) -- should NOT be significant
        (3, "Variant_A", 500, 26), (4, "Variant_A", 500, 25),
        # Variant_B: 1000 events, 150 purchases (15%) -- should be significant
        (5, "Variant_B", 500, 75), (6, "Variant_B", 500, 75),
    ]
    return pd.DataFrame(rows, columns=["customer_id", "experiment_group", "total_events", "purchase_events"])


def test_group_totals(toy_counts):
    totals = group_totals(toy_counts)
    assert totals.loc["Control", "total_events"] == 1000
    assert totals.loc["Control", "purchase_events"] == 50
    assert totals.loc["Control", "purchase_rate"] == pytest.approx(0.05)
    assert totals.loc["Variant_B", "purchase_rate"] == pytest.approx(0.15)


def test_two_proportion_z_known_difference():
    # 5% vs 15% on n=1000 each should be hugely significant
    p_a, p_b, z, p_value = two_proportion_z(1000, 50, 1000, 150)
    assert p_value < 0.001
    assert z > 0  # b > a


def test_pairwise_tests_significance_pattern(toy_counts):
    results = pairwise_tests(toy_counts)
    by_pair = {(r.group_a, r.group_b): r for r in results}

    control_vs_a = by_pair[("Control", "Variant_A")]
    control_vs_b = by_pair[("Control", "Variant_B")]

    # ~5% vs ~5.1% on n=1000 should NOT be significant
    assert not control_vs_a.significant
    # 5% vs 15% on n=1000 should be significant even after Bonferroni correction
    assert control_vs_b.significant
    assert control_vs_b.absolute_lift_pp == pytest.approx(10.0, abs=0.1)


def test_chi_square_detects_group_difference(toy_counts):
    result = chi_square_test(toy_counts)
    assert result["p_value"] < 0.001
    assert result["dof"] == 2
