"""Ingest: discovery, price-series fetch, and persistence to SQLite.

This module is built in stages. Currently implemented:

  * value normalization (`_num`, `to_unix`)   -- the parsing primitives
  * schema and persistence                    -- `init_db`, `upsert_market`, ...
  * discovery                                 -- `discover_series`, `discover_markets`
  * price series + horizon observation        -- `fetch_price_series`, `extract_horizon`
  * orchestration and gates                   -- `run_ingest`, `verify_ingest`

On the two tables: `markets` holds one row per market, `candles` holds one row
per market per hour. Splitting them avoids repeating a market's title, category
and result across all ~40 of its candles, and the `candles` table is what makes
the project's "price series" claim literally true rather than a snapshot.
"""

from __future__ import annotations

import asyncio
import math
import sqlite3
from collections import Counter, defaultdict
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


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------


async def get_cutoff_ts(client) -> int:
    """Unix seconds for market_settled_ts from GET /historical/cutoff.

    Used for provenance only. The historical candlestick endpoint returns no
    data (verified in step 2), so ingest sources everything from the live
    endpoints; the cutoff just records which side of the line a market sits on.
    """
    cutoff = await client.get("/historical/cutoff")
    return to_unix(cutoff.get("market_settled_ts"))


async def discover_series(client, categories: list[str] | None = None) -> list[dict]:
    """Return [{'series_ticker', 'category', 'title'}] for every series.

    GET /series returns all ~13k series in a single unpaginated response, and
    -- unlike the market object -- it does carry `category`. That is the whole
    reason discovery is series-first: category has to be captured here and
    stamped onto every market found beneath the series, or the per-category
    calibration breakdown has nothing to group by.
    """
    page = await client.get("/series")
    out = []
    for s in page.get("series") or []:
        cat = s.get("category")
        if categories and cat not in categories:
            continue
        ticker = s.get("ticker")
        if not ticker:
            continue
        out.append({"series_ticker": ticker, "category": cat or "unknown", "title": s.get("title")})
    return out


def normalize_market(raw: dict, series: dict, cutoff_ts: int) -> dict | None:
    """Turn a raw market object into a row for the `markets` table.

    Returns None if the market is unusable: no ticker, no settlement time, or a
    result that is not exactly 'yes' or 'no' (void and unresolved markets cannot
    be scored against an outcome).

    `category` and `series_ticker` are both taken from the series rather than the
    market, because the market object carries neither.
    """
    ticker = raw.get("ticker")
    result = (raw.get("result") or "").strip().lower()
    if not ticker or result not in ("yes", "no"):
        return None

    settle_ts = to_unix(raw.get("settlement_ts"))
    settle_source = "settlement_ts"
    if settle_ts is None:
        settle_ts = to_unix(raw.get("close_time"))
        settle_source = "close_time"
    if settle_ts is None:
        return None

    return {
        "ticker": ticker,
        "series_ticker": series["series_ticker"],
        "category": series.get("category") or "unknown",
        "title": raw.get("title"),
        "close_ts": to_unix(raw.get("close_time")),
        "settle_ts": settle_ts,
        "result": result,
        "p_horizon": None,      # filled by the price-series fetch
        "yes_ask": None,
        "yes_bid": None,
        "horizon_ts": None,
        "tier": "historical" if settle_ts < cutoff_ts else "live",
        "_settle_source": settle_source,   # provenance, not a table column
    }


async def discover_markets(
    client, series: dict, cutoff_ts: int, max_markets: int | None = None
) -> list[dict]:
    """Page settled markets for one series and normalize them.

    Filtering by series_ticker is not optional: the unfiltered feed is entirely
    auto-generated multivariate parlay markets (KXMVE...), which settle every few
    minutes, carry no candlestick history, and would swamp any real sample.
    """
    out = []
    async for raw in client.paginate(
        "/markets",
        {"series_ticker": series["series_ticker"], "status": "settled", "limit": 200},
        key="markets",
        max_items=max_markets,
    ):
        m = normalize_market(raw, series, cutoff_ts)
        if m is not None:
            out.append(m)
    return out


# --------------------------------------------------------------------------
# Price series and the horizon observation
# --------------------------------------------------------------------------

# Reasons a discovered market yields no usable observation. Tallied rather than
# silently dropped: "we kept 1900 of 2703" is a fact about liquidity only if you
# can say where the other 803 went.
SKIP_REASONS = (
    "no_candles",
    "none_at_horizon",
    "quote_missing",
    "quote_out_of_range",
    "quote_crossed",
    "api_error",
)


def parse_candle(raw: dict) -> dict | None:
    """Normalize one raw candlestick into {ts, yes_bid, yes_ask, price, volume}.

    `yes_bid`, `yes_ask` and `price` arrive as nested OHLC objects; we take the
    close, i.e. the value standing at the end of that hour. Every numeric read
    goes through _num() because the field names differ by tier.
    """
    ts = to_unix(raw.get("end_period_ts"))
    if ts is None:
        return None
    return {
        "ts": ts,
        "yes_bid": _num(raw.get("yes_bid") or {}, "close"),
        "yes_ask": _num(raw.get("yes_ask") or {}, "close"),
        "price": _num(raw.get("price") or {}, "close"),
        "volume": _num(raw, "volume"),
    }


def extract_horizon(candles: list[dict], settle_ts: int, horizon_sec: int) -> tuple[dict | None, str | None]:
    """Pick the observation the calibration is built on.

    Returns (observation, None) or (None, skip_reason).

    Takes the LAST candle at or before settle_ts - horizon_sec. "At or before"
    keeps the observation at least the full horizon away from settlement -- never
    accidentally closer, which would flatter the forecast.

    p_horizon is the MID, (bid + ask) / 2, deliberately rather than the ask:
    using the ask would fold the bid-ask spread into the measured probability and
    make the market look systematically overconfident when we were really just
    measuring trading costs. The spread re-enters in the backtest as an
    execution cost, which is where it belongs.
    """
    if not candles:
        return None, "no_candles"

    target = settle_ts - horizon_sec
    eligible = [c for c in candles if c["ts"] <= target]
    if not eligible:
        return None, "none_at_horizon"

    c = max(eligible, key=lambda x: x["ts"])
    bid, ask = c["yes_bid"], c["yes_ask"]

    if bid is None or ask is None:
        return None, "quote_missing"
    # A bid at 0 or an ask at 1 means nobody is quoting that side: there is no
    # real two-sided market to take a midpoint of.
    if not (0.0 < bid < 1.0) or not (0.0 < ask < 1.0):
        return None, "quote_out_of_range"
    if ask < bid:
        return None, "quote_crossed"

    return {
        "p_horizon": (bid + ask) / 2.0,
        "yes_bid": bid,
        "yes_ask": ask,
        "horizon_ts": c["ts"],
    }, None


async def fetch_price_series(client, market: dict, config: dict) -> tuple[list[dict], dict | None, str | None]:
    """Fetch a market's hourly candles and derive its horizon observation.

    Returns (all_candles, observation_or_None, skip_reason_or_None). The full
    candle list is returned regardless of whether an observation could be
    derived -- the price series is stored either way, since it is what makes the
    'price series' claim accurate and it enables a later horizon sweep without
    re-hitting the API.
    """
    settle_ts = market["settle_ts"]
    lookback = config["series_lookback_d"] * 86400
    path = (
        f"/series/{market['series_ticker']}"
        f"/markets/{market['ticker']}/candlesticks"
    )
    try:
        resp = await client.get(
            path,
            {
                "start_ts": settle_ts - lookback,
                "end_ts": settle_ts,
                "period_interval": 60,
            },
        )
    except Exception:
        return [], None, "api_error"

    candles = [
        p for p in (parse_candle(r) for r in (resp.get("candlesticks") or []))
        if p is not None
    ]
    obs, reason = extract_horizon(candles, settle_ts, config["horizon_sec"])
    return candles, obs, reason


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


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


async def run_ingest(config: dict, log=print) -> dict:
    """Discovery -> price-series fetch -> SQLite. Returns summary stats.

    Markets are processed in chunks so progress is visible and each chunk is
    committed before the next begins: an interrupted run keeps everything it had
    already written, and re-running resumes cleanly because every write is an
    INSERT OR REPLACE keyed on the market ticker.
    """
    # Imported here so the module can be imported without credentials present.
    from auth import KalshiSigner
    from client import KalshiClient

    conn = connect(config["db_path"])
    init_db(conn)

    signer = KalshiSigner.from_env()
    stats = {
        "skipped": Counter(),
        "skipped_by_category": defaultdict(Counter),
        "settle_source": Counter(),
    }

    async with KalshiClient(signer, max_concurrency=config["max_concurrency"]) as client:
        cutoff_ts = await get_cutoff_ts(client)
        log(f"cutoff (market_settled_ts) = {_fmt_day(cutoff_ts)}")

        index = {s["series_ticker"]: s for s in await discover_series(client)}
        wanted = config["series_tickers"]
        missing = [t for t in wanted if t not in index]
        if missing:
            raise RuntimeError(f"pinned series not found in /series: {missing}")

        log(f"discovering markets across {len(wanted)} series ...")
        found = await asyncio.gather(
            *(discover_markets(client, index[t], cutoff_ts) for t in wanted)
        )
        markets = [m for group in found for m in group]
        for m in markets:
            stats["settle_source"][m.pop("_settle_source")] += 1
        log(f"discovered {len(markets)} settled markets")

        n_priced = 0
        n_candle_rows = 0
        chunk = 250
        for start in range(0, len(markets), chunk):
            batch = markets[start : start + chunk]
            results = await asyncio.gather(
                *(fetch_price_series(client, m, config) for m in batch)
            )
            for market, (candles, obs, reason) in zip(batch, results):
                # The full price series is stored regardless of whether a
                # horizon observation could be derived from it.
                n_candle_rows += upsert_candles(conn, market["ticker"], candles)
                if obs is not None:
                    market.update(obs)
                    n_priced += 1
                else:
                    stats["skipped"][reason] += 1
                    stats["skipped_by_category"][market["category"]][reason] += 1
                upsert_market(conn, market)
            conn.commit()
            log(
                f"  {min(start + chunk, len(markets)):>5}/{len(markets)} markets  "
                f"priced={n_priced}  candles={n_candle_rows}"
            )

        client_stats = dict(client.stats)

    summary = {
        "n_discovered": len(markets),
        "n_priced": n_priced,
        "n_skipped": len(markets) - n_priced,
        "skipped_reasons": dict(stats["skipped"]),
        "skipped_by_category": {
            k: dict(v) for k, v in stats["skipped_by_category"].items()
        },
        "settle_ts_source": dict(stats["settle_source"]),
        "n_candle_rows": n_candle_rows,
        "cutoff_ts": cutoff_ts,
        "client": client_stats,
        **db_summary(conn),
    }
    conn.close()
    return summary


def _fmt_day(ts: int | None) -> str:
    if ts is None:
        return "?"
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Acceptance gates (spec section 6, criteria 2/3/4/9)
# --------------------------------------------------------------------------


def verify_ingest(conn: sqlite3.Connection, min_markets: int = 200) -> dict:
    """Run the four post-ingest gates. Criterion 3 is a HALT gate.

    Criterion 3 is the weakest claim that still proves the pipeline works: it
    asks only whether prices point in the right direction at all. If markets
    that resolved YES were not priced higher than those that resolved NO, then
    prices are misparsed, outcomes are misparsed, or the two are misaligned --
    and every downstream number is meaningless while still plotting beautifully.
    """
    out = {}

    n = conn.execute(
        "SELECT COUNT(*) FROM markets WHERE p_horizon IS NOT NULL AND result IS NOT NULL"
    ).fetchone()[0]
    out["c2_usable_markets"] = {"value": n, "threshold": min_markets, "pass": n >= min_markets}

    rows = {
        r["result"]: (r["n"], r["mean_p"], r["var_p"])
        for r in conn.execute(
            "SELECT result, COUNT(*) AS n, AVG(p_horizon) AS mean_p, "
            "AVG(p_horizon*p_horizon) - AVG(p_horizon)*AVG(p_horizon) AS var_p "
            "FROM markets WHERE p_horizon IS NOT NULL GROUP BY result"
        )
    }
    ny, my, vy = rows.get("yes", (0, None, None))
    nn, mn, vn = rows.get("no", (0, None, None))
    if ny and nn and my is not None and mn is not None:
        se = math.sqrt(max(vy, 0) / ny + max(vn, 0) / nn) or float("inf")
        z = (my - mn) / se
        out["c3_direction"] = {
            "mean_p_yes": round(my, 4), "n_yes": ny,
            "mean_p_no": round(mn, 4), "n_no": nn,
            "difference": round(my - mn, 4),
            "z": round(z, 1),
            "pass": (my > mn) and z > 3.0,
        }
    else:
        out["c3_direction"] = {"pass": False, "reason": "missing one outcome class"}

    bad = conn.execute(
        "SELECT COUNT(*) FROM markets WHERE p_horizon IS NOT NULL "
        "AND (p_horizon <= 0 OR p_horizon >= 1)"
    ).fetchone()[0]
    rng = conn.execute(
        "SELECT MIN(p_horizon), MAX(p_horizon) FROM markets WHERE p_horizon IS NOT NULL"
    ).fetchone()
    out["c4_probability_range"] = {
        "out_of_range": bad, "min": rng[0], "max": rng[1], "pass": bad == 0
    }

    nm = conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    nc = conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
    out["c9_price_series"] = {
        "markets": nm, "candles": nc,
        "candles_per_market": round(nc / nm, 1) if nm else 0,
        "pass": nc > nm * 5,
    }

    out["all_pass"] = all(v.get("pass") for k, v in out.items() if k.startswith("c"))
    return out
