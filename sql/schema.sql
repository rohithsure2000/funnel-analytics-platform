-- schema.sql
-- Warehouse schema for the real Marketing & E-Commerce Analytics dataset
-- (see data/README.md for the source). ANSI-SQL, compatible with both
-- Snowflake (production) and SQLite (local demo backend, see src/db.py).

CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id             INTEGER PRIMARY KEY,
    signup_date             DATE NOT NULL,
    country                 VARCHAR(5)  NOT NULL,
    age                     INTEGER NOT NULL,
    gender                  VARCHAR(20) NOT NULL,
    loyalty_tier             VARCHAR(20) NOT NULL,
    acquisition_channel      VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_id      INTEGER PRIMARY KEY,
    category        VARCHAR(50) NOT NULL,
    brand           VARCHAR(50) NOT NULL,
    base_price      DECIMAL(10,2) NOT NULL,
    launch_date     DATE NOT NULL,
    is_premium      INTEGER NOT NULL  -- 0/1
);

CREATE TABLE IF NOT EXISTS dim_campaigns (
    campaign_id      INTEGER PRIMARY KEY,
    channel          VARCHAR(50) NOT NULL,
    objective        VARCHAR(50) NOT NULL,
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    target_segment   VARCHAR(50) NOT NULL,
    expected_uplift  DECIMAL(6,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS fct_transactions (
    transaction_id     INTEGER PRIMARY KEY,
    timestamp           TIMESTAMP NOT NULL,
    customer_id         INTEGER NOT NULL REFERENCES dim_customers(customer_id),
    product_id           INTEGER REFERENCES dim_products(product_id),  -- nullable in source
    quantity             INTEGER NOT NULL,
    discount_applied     DECIMAL(5,4) NOT NULL,
    gross_revenue        DECIMAL(10,2),                                  -- nullable in source
    campaign_id           INTEGER NOT NULL,  -- 0 = not campaign-attributed
    refund_flag           INTEGER NOT NULL,  -- 0/1
    has_missing_product_or_revenue INTEGER NOT NULL,  -- data-quality flag, set by src/pipeline.py
    revenue_sign_mismatch           INTEGER NOT NULL  -- refund_flag=1 but revenue not negative
);

-- One row per (customer, product, view/click/add_to_cart/bounce/purchase)
-- interaction. session_id is kept for traceability back to the source file
-- but is NOT trustworthy as a single-visit key (see data/README.md) -- use
-- derived_session_id instead, which src/sessionize.py computes from
-- timestamps (30-minute inactivity gap = new session).
CREATE TABLE IF NOT EXISTS fct_events (
    event_id               INTEGER PRIMARY KEY,
    timestamp                TIMESTAMP NOT NULL,
    customer_id              INTEGER NOT NULL REFERENCES dim_customers(customer_id),
    session_id                INTEGER NOT NULL,   -- source field, unreliable -- see note above
    derived_session_id        VARCHAR(40) NOT NULL,  -- computed by src/sessionize.py
    event_type                 VARCHAR(20) NOT NULL,  -- view|click|add_to_cart|bounce|purchase
    product_id                  INTEGER REFERENCES dim_products(product_id),  -- nullable
    device_type                  VARCHAR(20),          -- nullable in source
    traffic_source                VARCHAR(20) NOT NULL, -- casing-normalized on load
    campaign_id                    INTEGER NOT NULL,     -- 0 = not campaign-attributed
    page_category                    VARCHAR(20) NOT NULL,
    session_duration_sec              DECIMAL(8,2) NOT NULL,
    experiment_group                   VARCHAR(20) NOT NULL  -- Control|Variant_A|Variant_B, assigned per-event
);

CREATE INDEX IF NOT EXISTS idx_events_customer      ON fct_events(customer_id);
CREATE INDEX IF NOT EXISTS idx_events_derived_sess   ON fct_events(derived_session_id);
CREATE INDEX IF NOT EXISTS idx_events_type           ON fct_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_group          ON fct_events(experiment_group);
CREATE INDEX IF NOT EXISTS idx_txn_customer          ON fct_transactions(customer_id);
