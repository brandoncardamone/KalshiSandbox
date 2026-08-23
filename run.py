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
    "series_tickers":    [],          # filled after discovery; >=3 distinct categories
    "n_bins":            10,          # calibration bins
    "min_bin_n":         20,          # bins below this are reported but not interpreted
    "min_category_n":    40,          # categories below this are not interpreted
    "train_frac":        0.6,         # time-ordered train/test split for backtest
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


def main() -> None:
    args = parse_args()
    do_ingest = args.ingest or args.all
    do_analyze = args.analyze or args.all
    if not (do_ingest or do_analyze):
        raise SystemExit("nothing to do: pass --ingest, --analyze, or --all")
    raise SystemExit("pipeline not wired up yet (see steps 2-9 of the build plan)")


if __name__ == "__main__":
    main()
