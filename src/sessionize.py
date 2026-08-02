"""
sessionize.py
-------------
The source `session_id` field in events.csv isn't a trustworthy
single-visit key -- the same value shows up across different customers
and across dates years apart (see data/README.md).

This derives real sessions from timestamps instead: within one
customer's history, a new session starts whenever the gap since their
last event exceeds `gap_minutes` (30 min default -- Google Analytics
uses the same threshold).
"""

import pandas as pd

DEFAULT_GAP_MINUTES = 30


def build_sessions(events: pd.DataFrame, gap_minutes: int = DEFAULT_GAP_MINUTES) -> pd.DataFrame:
    """Return a copy of `events` with a new `derived_session_id` column.

    Requires columns: customer_id, timestamp (datetime64).
    derived_session_id is formatted as "{customer_id}-{session_seq}" so it
    is unique across customers as well as within one customer's history.
    """
    df = events.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["customer_id", "timestamp"])

    gap = df.groupby("customer_id")["timestamp"].diff()
    new_session = (gap.isna()) | (gap > pd.Timedelta(minutes=gap_minutes))
    session_seq = new_session.groupby(df["customer_id"]).cumsum()

    df["derived_session_id"] = df["customer_id"].astype(str) + "-" + session_seq.astype(str)
    return df


def session_summary(sessioned_events: pd.DataFrame) -> pd.DataFrame:
    """One row per derived session: customer, start/end time, event count,
    and duration. Useful for sanity-checking the sessionization -- the
    duration distribution should look like real browsing sessions, not
    years-long spans."""
    g = sessioned_events.groupby("derived_session_id")
    summary = g.agg(
        customer_id=("customer_id", "first"),
        start_ts=("timestamp", "min"),
        end_ts=("timestamp", "max"),
        n_events=("event_id", "count"),
    )
    summary["duration_minutes"] = (
        (summary["end_ts"] - summary["start_ts"]).dt.total_seconds() / 60
    ).round(2)
    return summary.reset_index()


if __name__ == "__main__":
    import os
    from src.db import get_connection

    with get_connection() as conn:
        events = pd.read_sql("SELECT * FROM fct_events", conn, parse_dates=["timestamp"])

    sessioned = build_sessions(events)
    summary = session_summary(sessioned)
    print(f"Derived {summary.shape[0]:,} sessions from {len(events):,} events "
          f"(source session_id had {events['session_id'].nunique():,} distinct values)")
    print(summary["duration_minutes"].describe())
    print(summary["n_events"].describe())
