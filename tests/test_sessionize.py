import pandas as pd
import pytest

from src.sessionize import build_sessions, session_summary


@pytest.fixture
def toy_events():
    """Customer 1: 3 events within a 30-minute window (should be ONE
    session), then a 4th event 2 hours later (should start a NEW session).
    Customer 2: a single event."""
    rows = [
        (1, 1, "2024-01-01 10:00:00"),
        (2, 1, "2024-01-01 10:10:00"),
        (3, 1, "2024-01-01 10:20:00"),
        (4, 1, "2024-01-01 12:20:00"),  # 2 hours after the previous event
        (5, 2, "2024-01-01 09:00:00"),
    ]
    df = pd.DataFrame(rows, columns=["event_id", "customer_id", "timestamp"])
    return df


def test_events_within_gap_share_a_session(toy_events):
    sessioned = build_sessions(toy_events, gap_minutes=30)
    cust1 = sessioned[sessioned["customer_id"] == 1].sort_values("timestamp")
    # first 3 events (10:00, 10:10, 10:20) are all <=30 min apart
    assert cust1.iloc[0]["derived_session_id"] == cust1.iloc[1]["derived_session_id"]
    assert cust1.iloc[1]["derived_session_id"] == cust1.iloc[2]["derived_session_id"]


def test_gap_over_threshold_starts_new_session(toy_events):
    sessioned = build_sessions(toy_events, gap_minutes=30)
    cust1 = sessioned[sessioned["customer_id"] == 1].sort_values("timestamp")
    # 4th event is 2 hours after the 3rd -- should be a different session
    assert cust1.iloc[2]["derived_session_id"] != cust1.iloc[3]["derived_session_id"]


def test_sessions_are_unique_across_customers(toy_events):
    sessioned = build_sessions(toy_events, gap_minutes=30)
    cust1_session = sessioned[sessioned["customer_id"] == 1]["derived_session_id"].iloc[0]
    cust2_session = sessioned[sessioned["customer_id"] == 2]["derived_session_id"].iloc[0]
    assert cust1_session != cust2_session


def test_session_summary_shape(toy_events):
    sessioned = build_sessions(toy_events, gap_minutes=30)
    summary = session_summary(sessioned)
    # customer 1 has 2 sessions (3 events + 1 event), customer 2 has 1
    assert summary.shape[0] == 3
    assert summary["n_events"].sum() == 5
