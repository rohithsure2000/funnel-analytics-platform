import pandas as pd
import pytest

from src.funnel_analysis import (
    bounce_rate, biggest_drop_off_step, customer_step_reach, funnel_by_channel, overall_funnel,
)


@pytest.fixture
def toy_events():
    """5 customers with hand-crafted event histories so the expected
    lifecycle-funnel counts are known:
    view: 5, click: 4, add_to_cart: 2, purchase: 1
    """
    rows = [
        # customer 1: full funnel
        (1, "view"), (1, "click"), (1, "add_to_cart"), (1, "purchase"),
        # customer 2: reaches add_to_cart, never purchases
        (2, "view"), (2, "click"), (2, "add_to_cart"),
        # customer 3: reaches click only
        (3, "view"), (3, "click"),
        # customer 4: reaches click only
        (4, "view"), (4, "click"),
        # customer 5: view then bounces (bounce is NOT a funnel step)
        (5, "view"), (5, "bounce"),
    ]
    return pd.DataFrame(rows, columns=["customer_id", "event_type"])


@pytest.fixture
def toy_customers():
    return pd.DataFrame({
        "customer_id": [1, 2, 3, 4, 5],
        "acquisition_channel": ["Organic", "Organic", "Email", "Email", "Email"],
    })


def test_customer_step_reach_shape(toy_events):
    reach = customer_step_reach(toy_events)
    assert set(reach.columns) == {"view", "click", "add_to_cart", "purchase"}
    assert len(reach) == 5


def test_overall_funnel_counts(toy_events):
    overall = overall_funnel(customer_step_reach(toy_events))
    counts = dict(zip(overall["step_name"], overall["customers_reached"]))
    assert counts["view"] == 5
    assert counts["click"] == 4
    assert counts["add_to_cart"] == 2
    assert counts["purchase"] == 1


def test_bounce_is_not_a_funnel_step(toy_events):
    reach = customer_step_reach(toy_events)
    # customer 5 bounced and should NOT show as having reached any step
    # beyond 'view'
    assert reach.loc[5, "view"] is True or reach.loc[5, "view"] == True  # noqa: E712
    assert reach.loc[5, "click"] == False  # noqa: E712


def test_biggest_drop_off_step(toy_events):
    overall = overall_funnel(customer_step_reach(toy_events))
    worst = biggest_drop_off_step(overall)
    # add_to_cart -> purchase drops 2 -> 1 (50%); click -> add_to_cart drops
    # 4 -> 2 (50% too) -- whichever pandas picks first among ties is fine,
    # just confirm it's one of the two steepest, not view/click (only 20%)
    assert worst["step_name"] in {"add_to_cart", "purchase"}
    assert worst["drop_off_pct"] == pytest.approx(50.0)


def test_bounce_rate(toy_events):
    # 1 bounce out of 13 total events
    assert bounce_rate(toy_events) == pytest.approx(100 / 13, abs=0.01)


def test_funnel_by_channel(toy_events, toy_customers):
    reach = customer_step_reach(toy_events)
    by_channel = funnel_by_channel(reach, toy_customers)
    email_purchase = by_channel[
        (by_channel["acquisition_channel"] == "Email") & (by_channel["step_name"] == "purchase")
    ]
    # none of customers 3, 4, 5 (all Email) ever purchased
    assert email_purchase["customers_reached"].iloc[0] == 0

    organic_purchase = by_channel[
        (by_channel["acquisition_channel"] == "Organic") & (by_channel["step_name"] == "purchase")
    ]
    # customer 1 (Organic) purchased; customer 2 (Organic) did not
    assert organic_purchase["customers_reached"].iloc[0] == 1
