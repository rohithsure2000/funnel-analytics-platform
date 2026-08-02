"""
pipeline.py
-----------
ETL for the Marketing & E-Commerce Analytics dataset (see data/README.md).
Reads the five raw CSVs, validates/cleans them, derives sessions
(src/sessionize.py), and loads everything into the warehouse.

Run:
    python -m src.pipeline
"""

import logging
import os

import pandas as pd

from src.db import DEFAULT_SQLITE_PATH, executescript, get_connection
from src.sessionize import build_sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sql", "schema.sql")

VALID_EVENT_TYPES = {"view", "click", "add_to_cart", "bounce", "purchase"}
# The source data has casing inconsistencies for traffic_source
# ("Organic" vs "ORGANIC") -- normalize to title case on load.
TRAFFIC_SOURCE_MAP = {s.upper(): s for s in ["Organic", "Paid Search", "Social", "Email", "Direct"]}


class DataQualityError(ValueError):
    pass


def _path(name: str) -> str:
    return os.path.join(RAW_DIR, name)


def load_customers() -> pd.DataFrame:
    df = pd.read_csv(_path("customers.csv"), parse_dates=["signup_date"])
    before = len(df)
    df = df.drop_duplicates(subset="customer_id").dropna()
    if len(df) != before:
        logger.info("customers: dropped %d invalid/duplicate rows", before - len(df))
    return df


def load_products() -> pd.DataFrame:
    df = pd.read_csv(_path("products.csv"), parse_dates=["launch_date"])
    before = len(df)
    df = df.drop_duplicates(subset="product_id").dropna()
    if len(df) != before:
        logger.info("products: dropped %d invalid/duplicate rows", before - len(df))
    return df


def load_campaigns() -> pd.DataFrame:
    df = pd.read_csv(_path("campaigns.csv"), parse_dates=["start_date", "end_date"])
    before = len(df)
    df = df.drop_duplicates(subset="campaign_id").dropna()
    if len(df) != before:
        logger.info("campaigns: dropped %d invalid/duplicate rows", before - len(df))
    return df


def load_transactions(valid_customers: set, valid_products: set) -> pd.DataFrame:
    df = pd.read_csv(_path("transactions.csv"), parse_dates=["timestamp"])
    before = len(df)

    df = df.drop_duplicates(subset="transaction_id")

    orphaned = ~df["customer_id"].isin(valid_customers)
    if orphaned.any():
        logger.warning("transactions: dropping %d rows with unknown customer_id", orphaned.sum())
        df = df[~orphaned]

    # product_id / gross_revenue are null together for ~10% of rows in the
    # source. Keep the rows (still a real transaction) but flag them
    # instead of imputing a number.
    df["has_missing_product_or_revenue"] = df["product_id"].isna() | df["gross_revenue"].isna()

    # 325 rows have refund_flag=1 but non-negative revenue -- inconsistent
    # with the usual convention (refunds should be negative). Trusting
    # refund_flag over the sign here since it's the explicit field; flag
    # the mismatch rather than silently picking one.
    df["revenue_sign_mismatch"] = (df["refund_flag"] == 1) & (df["gross_revenue"].fillna(0) >= 0)

    df["has_missing_product_or_revenue"] = df["has_missing_product_or_revenue"].astype(int)
    df["revenue_sign_mismatch"] = df["revenue_sign_mismatch"].astype(int)

    dropped = before - len(df)
    if dropped:
        logger.info("transactions: dropped %d rows (%d -> %d)", dropped, before, len(df))
    logger.info(
        "transactions: %d rows missing product/revenue, %d rows with refund/sign mismatch",
        df["has_missing_product_or_revenue"].sum(), df["revenue_sign_mismatch"].sum(),
    )
    return df


def load_events(valid_customers: set, valid_products: set) -> pd.DataFrame:
    df = pd.read_csv(_path("events.csv"), parse_dates=["timestamp"])
    before = len(df)

    df = df.drop_duplicates(subset="event_id")

    bad_types = ~df["event_type"].isin(VALID_EVENT_TYPES)
    if bad_types.any():
        raise DataQualityError(f"{bad_types.sum()} events have an unrecognized event_type")

    orphaned = ~df["customer_id"].isin(valid_customers)
    if orphaned.any():
        logger.warning("events: dropping %d rows with unknown customer_id", orphaned.sum())
        df = df[~orphaned]

    # Normalize traffic_source casing (source has both "Organic" and "ORGANIC")
    df["traffic_source"] = df["traffic_source"].str.upper().map(TRAFFIC_SOURCE_MAP).fillna(df["traffic_source"])

    # device_type is legitimately missing for ~2% of rows -- keep as an
    # explicit "unknown" category rather than dropping the event.
    df["device_type"] = df["device_type"].fillna("unknown")

    dropped = before - len(df)
    if dropped:
        logger.info("events: dropped %d rows (%d -> %d)", dropped, before, len(df))

    logger.info("events: deriving sessions from timestamps (source session_id is unreliable)")
    df = build_sessions(df)

    return df


def load_to_warehouse(customers, products, campaigns, transactions, events) -> None:
    with open(SCHEMA_PATH) as f:
        executescript(f.read())

    tables = {
        "dim_customers": customers,
        "dim_products": products,
        "dim_campaigns": campaigns,
        "fct_transactions": transactions,
        "fct_events": events,
    }

    # Delete children before parents (fct_* reference dim_*, and foreign
    # keys are enforced -- deleting a parent while a child still points at
    # it fails). Load in the opposite order so each insert's foreign key
    # already exists.
    delete_order = ["fct_events", "fct_transactions", "dim_customers", "dim_products", "dim_campaigns"]
    load_order = ["dim_customers", "dim_products", "dim_campaigns", "fct_transactions", "fct_events"]

    with get_connection() as conn:
        # Clear rows instead of drop+recreate -- to_sql's if_exists='replace'
        # would drop the table and lose the indexes/PK constraints from
        # schema.sql.
        for table_name in delete_order:
            conn.execute(f"DELETE FROM {table_name}")
        for table_name in load_order:
            tables[table_name].to_sql(table_name, conn, if_exists="append", index=False, chunksize=10_000)
        conn.commit()

    logger.info(
        "Loaded %d customers, %d products, %d campaigns, %d transactions, %d events into %s",
        len(customers), len(products), len(campaigns), len(transactions), len(events), DEFAULT_SQLITE_PATH,
    )


def run() -> None:
    logger.info("Starting ETL pipeline")

    customers = load_customers()
    products = load_products()
    campaigns = load_campaigns()

    transactions = load_transactions(set(customers["customer_id"]), set(products["product_id"]))
    events = load_events(set(customers["customer_id"]), set(products["product_id"]))

    load_to_warehouse(customers, products, campaigns, transactions, events)
    logger.info("ETL pipeline complete")


if __name__ == "__main__":
    run()
