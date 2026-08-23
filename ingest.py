"""Ingest: discovery, price-series fetch, and persistence to SQLite.

This module is built in stages. Currently implemented:

  * value normalization (`_num`, `to_unix`)   -- the parsing primitives
  * schema and persistence                    -- `init_db`, `upsert_market`, ...

Discovery and price-series fetching land in later steps.

On the two tables: `markets` holds one row per market, `candles` holds one row
per market per hour. Splitting them avoids repeating a market's title, category
and result across all ~40 of its candles, and the `candles` table is what makes
the project's "price series" claim literally true rather than a snapshot.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS markets (
    ticker         TEXT PRIMARY KEY,
    series_ticker  TEXT,
    category       TEXT,            -- REQUIRED: enables per-category calibration
    title          TEXT,
    close_ts       INTEGER,
    settle_ts      INTEGER NOT NULL,
    result         TEXT    NOT NULL CHECK (result IN ('yes','no')),
    p_horizon      REAL,            -- mid-price implied probability at horizon, [0,1]
    yes_ask        REAL,            -- ask at horizon, for backtest entry pricing
    yes_bid        REAL,
    horizon_ts     INTEGER,         -- actual candle timestamp used
    tier           TEXT             -- 'live' or 'historical' (provenance)
);

CREATE TABLE IF NOT EXISTS candles (
    ticker    TEXT NOT NULL,
    ts        INTEGER NOT NULL,     -- end_period_ts, Unix seconds
    yes_bid   REAL,
    yes_ask   REAL,
    price     REAL,                 -- last-trade close
    volume    REAL,
    PRIMARY KEY (ticker, ts)
);

CREATE INDEX IF NOT EXISTS idx_settle   ON markets(settle_ts);
CREATE INDEX IF NOT EXISTS idx_category ON markets(category);
CREATE INDEX IF NOT EXISTS idx_candles  ON candles(ticker, ts);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open the database with row access by column name."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not already exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# --------------------------------------------------------------------------
# Value normalization
# --------------------------------------------------------------------------


def _num(d: dict, base: str) -> float | None:
    """Read d[base], d[base+'_dollars'] or d[base+'_fp'], as a float.

    Kalshi's field naming is not stable across tiers: the live candlestick
    endpoint returns `close_dollars` / `volume_fp` where the historical one
    returns `close` / `volume`. Every numeric read goes through here so a rename
    degrades to None rather than silently reading the wrong field.

    Values arrive as decimal-dollar STRINGS in [0,1] -- "0.5600" means 56%
    implied. They are used directly as probabilities and are NOT divided by 100.
    """
    if not isinstance(d, dict):
        return None
    for key in (base, f"{base}_dollars", f"{base}_fp"):
        if key in d and d[key] is not None:
            try:
                return float(d[key])
            except (TypeError, ValueError):
                return None
    return None


def to_unix(value: Any) -> int | None:
    """Normalize a Kalshi timestamp to Unix seconds.

    Timestamps arrive either as Unix ints (`end_period_ts`) or ISO-8601 strings
    with optional fractional seconds (`"2026-06-23T23:56:41.145222Z"`), depending
    on the field and the endpoint.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return int(
            datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
        )
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

MARKET_COLUMNS = (
    "ticker",
    "series_ticker",
    "category",
    "title",
    "close_ts",
    "settle_ts",
    "result",
    "p_horizon",
    "yes_ask",
    "yes_bid",
    "horizon_ts",
    "tier",
)


def upsert_market(conn: sqlite3.Connection, market: dict) -> None:
    """Write one market row, replacing any existing row with the same ticker.

    INSERT OR REPLACE makes ingest idempotent: an interrupted run can simply be
    re-run without producing duplicates or needing cleanup.
    """
    row = tuple(market.get(col) for col in MARKET_COLUMNS)
    placeholders = ", ".join("?" * len(MARKET_COLUMNS))
    conn.execute(
        f"INSERT OR REPLACE INTO markets ({', '.join(MARKET_COLUMNS)}) "
        f"VALUES ({placeholders})",
        row,
    )


def upsert_candles(
    conn: sqlite3.Connection, ticker: str, candles: Iterable[dict]
) -> int:
    """Write a market's candle rows. Returns how many were written.

    Each candle dict is expected already normalized: {ts, yes_bid, yes_ask,
    price, volume}. Rows without a timestamp are skipped, since (ticker, ts) is
    the primary key.
    """
    rows = [
        (
            ticker,
            c["ts"],
            c.get("yes_bid"),
            c.get("yes_ask"),
            c.get("price"),
            c.get("volume"),
        )
        for c in candles
        if c.get("ts") is not None
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO candles (ticker, ts, yes_bid, yes_ask, price, volume) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def db_summary(conn: sqlite3.Connection) -> dict:
    """Counts used for the ingest summary and the acceptance criteria."""
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    n_markets = q("SELECT COUNT(*) FROM markets")
    n_candles = q("SELECT COUNT(*) FROM candles")
    return {
        "n_markets": n_markets,
        "n_markets_priced": q("SELECT COUNT(*) FROM markets WHERE p_horizon IS NOT NULL"),
        "n_candles": n_candles,
        "candles_per_market": round(n_candles / n_markets, 1) if n_markets else 0.0,
        "categories": {
            r["category"]: r["n"]
            for r in conn.execute(
                "SELECT category, COUNT(*) AS n FROM markets "
                "GROUP BY category ORDER BY n DESC"
            )
        },
        "tiers": {
            r["tier"]: r["n"]
            for r in conn.execute(
                "SELECT tier, COUNT(*) AS n FROM markets GROUP BY tier"
            )
        },
    }
