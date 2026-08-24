"""Entry point for the Kalshi calibration & backtesting engine.

    python run.py --ingest     # discover markets, fetch price series -> SQLite
    python run.py --analyze    # calibration, category breakdown, backtest
    python run.py --all        # both

Every tunable lives in CONFIG below so a run is reproducible from this file
alone. outputs/results.json records the config actually used alongside the
metrics it produced.
"""

from __future__ import annotations

import argparse

CONFIG = {
    "horizon_sec":       24 * 3600,   # read implied prob this far before settlement
    "series_lookback_d": 7,           # days of hourly candles stored per market
    "target_markets":    250,         # minimum settled markets to collect

    # Pinned 2026-08-23 from the step-4 discovery survey, BEFORE any prices were
    # fetched, so the sample cannot be selected on the result. Four categories,
    # each well clear of min_category_n.
    #
    # Chosen on measured 24h-horizon viability, not on market count. Crypto and
    # Financials are excluded despite being by far the largest categories
    # (KXBTCD alone has 291,438 settled markets) because those contracts are
    # hourly or 15-minute: they do not exist 24 hours before they settle, and
    # 0% of sampled markets yielded a usable quote at the horizon.
    "series_tickers": [
        # Climate and Weather -- daily city high temperature, ~76% usable.
        # NB structural base rate: ~6 mutually exclusive buckets per day, so
        # exactly one resolves YES and the sample skews to low probabilities.
        "KXHIGHNY", "KXHIGHCHI", "KXHIGHMIA",
        # Sports -- soccer totals and spreads, ~81-100% usable
        "KXBRASILEIROBGAME", "KXARGNACBSPREAD", "KXALLSVENSKANTOTAL",
        # Economics -- unemployment, Fed activity, TSA throughput, gas prices
        "KXUE", "KXFEDTWEETS", "KXTSAW", "KXAAAGASM",
        # Politics -- approval rating and fundraising
        "KXAPRPOTUSD", "KXACTBLUETOP",
    ],
    "n_bins":            10,          # calibration bins
    "min_bin_n":         20,          # bins below this are reported but not interpreted

    # Widest bid-ask spread at the horizon for a market to count as having a
    # genuine two-sided quote. Added after the step-6 run, on inspection of the
    # data rather than a priori: 16% of priced markets turned out to be quoted
    # around 0.045 / 0.906 -- an empty book whose midpoint carries no
    # information. The spread distribution is starkly bimodal (1,649 markets at
    # or below 0.10, then a separate cluster of 322 averaging 0.861), so this
    # reads a real gap rather than slicing a continuum.
    # Nothing is dropped: full-sample and liquid-subsample results are both
    # computed and both reported.
    "max_spread":        0.20,
    "min_category_n":    40,          # categories below this are not interpreted
    "train_frac":        0.6,         # time-ordered train/test split for backtest

    # A training-window bin counts as overpriced when outcomes arrived this
    # much less often than the price implied. Fixed at the spec value before
    # the test window was touched, and never retuned -- moving it after seeing
    # the out-of-sample result is precisely the lookahead the split prevents.
    "overprice_threshold": 0.03,
    "slippage_cents":    1.0,         # adverse execution assumption, on top of spread
    "max_concurrency":   8,
    "db_path":           "kalshi.db",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ingest", action="store_true", help="run the data pipeline")
    p.add_argument("--analyze", action="store_true", help="run calibration + backtest")
    p.add_argument("--all", action="store_true", help="run both")
    return p.parse_args()


def _print_gates(gates: dict) -> None:
    print("\n" + "=" * 70)
    print("ACCEPTANCE GATES")
    print("=" * 70)
    c2, c3, c4, c9 = (
        gates["c2_usable_markets"], gates["c3_direction"],
        gates["c4_probability_range"], gates["c9_price_series"],
    )
    mark = lambda ok: "PASS" if ok else "FAIL"  # noqa: E731
    print(f"[{mark(c2['pass'])}] criterion 2  usable markets: {c2['value']} "
          f"(need >= {c2['threshold']})")
    if "difference" in c3:
        print(f"[{mark(c3['pass'])}] criterion 3  HALT GATE -- price points the right way")
        print(f"         mean p_horizon | result=yes : {c3['mean_p_yes']}  (n={c3['n_yes']})")
        print(f"         mean p_horizon | result=no  : {c3['mean_p_no']}  (n={c3['n_no']})")
        print(f"         difference {c3['difference']:+}   z = {c3['z']}")
    else:
        print(f"[{mark(False)}] criterion 3  {c3.get('reason')}")
    print(f"[{mark(c4['pass'])}] criterion 4  p_horizon in (0,1): "
          f"{c4['out_of_range']} out of range, min={c4['min']}, max={c4['max']}")
    print(f"[{mark(c9['pass'])}] criterion 9  price series stored: {c9['candles']} candles "
          f"vs {c9['markets']} markets ({c9['candles_per_market']}/market)")


def do_ingest_run() -> dict:
    import asyncio

    from dotenv import load_dotenv

    from ingest import connect, run_ingest, verify_ingest

    load_dotenv()
    summary = asyncio.run(run_ingest(CONFIG))

    print("\n" + "=" * 70)
    print("INGEST SUMMARY")
    print("=" * 70)
    print(f"discovered      : {summary['n_discovered']}")
    print(f"priced          : {summary['n_priced']}")
    print(f"skipped         : {summary['n_skipped']}")
    for reason, n in sorted(summary["skipped_reasons"].items(), key=lambda kv: -kv[1]):
        print(f"    {reason:22s} {n:>6}")
    print(f"candle rows     : {summary['n_candle_rows']}")
    print(f"settle_ts source: {summary['settle_ts_source']}")
    print(f"categories      : {summary['categories']}")
    print(f"tiers           : {summary['tiers']}")
    print(f"http            : {summary['client']}")

    conn = connect(CONFIG["db_path"])
    gates = verify_ingest(conn)
    conn.close()
    _print_gates(gates)

    if not gates["all_pass"]:
        raise SystemExit(
            "\nHALTED: an acceptance gate failed. Analysis is not run on data that "
            "has not passed criterion 3 -- a Brier score computed on broken data is "
            "worse than none, because it looks like a finding."
        )
    return {"ingest": summary, "gates": gates}


def main() -> None:
    args = parse_args()
    do_ingest = args.ingest or args.all
    do_analyze = args.analyze or args.all
    if not (do_ingest or do_analyze):
        raise SystemExit("nothing to do: pass --ingest, --analyze, or --all")
    if do_ingest:
        do_ingest_run()
    if do_analyze:
        raise SystemExit("analysis not wired up yet (steps 6-9 of the build plan)")


if __name__ == "__main__":
    main()
