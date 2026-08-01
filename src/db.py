"""
db.py
-----
Connection helper for the funnel analytics platform.

Two backends are supported:

  * sqlite (default, used for local development / this demo): a local
    file-based warehouse at data/processed/warehouse.db. No credentials
    required, works out of the box.

  * snowflake (production): set DB_BACKEND=snowflake and the SNOWFLAKE_*
    environment variables (see .env.example). Requires the optional
    `snowflake-connector-python` dependency.

Application code should import `get_connection()` and not care which
backend is active.
"""

import os
import sqlite3
from contextlib import contextmanager

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from a .env file if present, no-op otherwise

DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "processed", "warehouse.db"
)


class ConfigError(RuntimeError):
    pass


def _sqlite_connect(path: str = DEFAULT_SQLITE_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _snowflake_connect():
    try:
        import snowflake.connector  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError(
            "DB_BACKEND=snowflake requires `pip install snowflake-connector-python`."
        ) from exc

    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD", "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:  # pragma: no cover
        raise ConfigError(f"Missing required Snowflake env vars: {', '.join(missing)}")

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


@contextmanager
def get_connection():
    """Yield a DB connection for whichever backend is configured, and
    guarantee it is closed afterward."""
    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    if backend == "sqlite":
        conn = _sqlite_connect()
    elif backend == "snowflake":  # pragma: no cover - exercised only in prod
        conn = _snowflake_connect()
    else:
        raise ConfigError(f"Unknown DB_BACKEND '{backend}'. Use 'sqlite' or 'snowflake'.")
    try:
        yield conn
    finally:
        conn.close()


def executescript(sql_text: str) -> None:
    """Run a multi-statement SQL script (used for schema.sql)."""
    with get_connection() as conn:
        conn.executescript(sql_text)
        conn.commit()
