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


def _crit(ok: bool, name: str, detail: str, **extra) -> dict:
    return {"pass": bool(ok), "criterion": name, "detail": detail, **extra}


def check_acceptance(results: dict, out_dir: str = "outputs") -> dict:
    """The twelve acceptance criteria from spec section 6, evaluated on real output.

    Criteria 9-12 exist specifically to verify the resume claims, so each of them
    reports the number it checked rather than a bare pass, and a failure names
    the resume clause that would have to be struck.
    """
    import os

    counts = results["counts"]
    cal = results["calibration"]
    cat = results["by_category"]
    bt = results["backtest"]
    gates = results["gates"]
    checks = {}

    # 1 -- exercised by whichever path produced this file.
    checks["c1_pipeline_runs"] = _crit(
        True,
        "python run.py --analyze completes",
        "this results.json was produced by a completed run; --all additionally "
        "re-runs the ingest, which is deliberately not exercised here because it "
        "would re-collect a different set of settled markets and invalidate the "
        "numbers recorded against this sample",
    )

    n = cal["n_markets"]
    checks["c2_usable_markets"] = _crit(
        n >= 200, "usable markets >= 200", f"{n} markets with p_horizon and result",
        value=n, threshold=200)

    c3 = gates["c3_direction"]
    checks["c3_direction"] = _crit(
        c3.get("pass", False), "HALT GATE: prices point the right way",
        f"mean p_horizon {c3.get('mean_p_yes')} (yes, n={c3.get('n_yes')}) vs "
        f"{c3.get('mean_p_no')} (no, n={c3.get('n_no')}), z = {c3.get('z')}",
        z=c3.get("z"))

    c4 = gates["c4_probability_range"]
    checks["c4_probability_range"] = _crit(
        c4["pass"], "all p_horizon strictly within (0,1)",
        f"{c4['out_of_range']} out of range; min {c4['min']}, max {c4['max']}")

    png = lambda f: os.path.exists(os.path.join(out_dir, f))  # noqa: E731
    checks["c5_calibration_png"] = _crit(
        png("calibration.png"), "outputs/calibration.png exists",
        "diagonal reference, binomial error bars and per-point n annotations are "
        "drawn by plot_calibration()")

    required = ["n_markets", "brier", "log_loss", "baseline_brier",
                "calibration_table", "longshot"]
    missing = [k for k in required if k not in cal]
    checks["c6_results_json_complete"] = _crit(
        not missing and "config" in results and "run_timestamp" in results,
        "results.json carries every required field",
        "missing: " + (", ".join(missing) or "nothing"))

    gi = os.path.join(os.path.dirname(out_dir) or ".", ".gitignore")
    gi_txt = open(gi, encoding="utf-8").read() if os.path.exists(gi) else ""
    secrets_ok = ".env" in gi_txt and "*.pem" in gi_txt
    checks["c7_no_secrets"] = _crit(
        secrets_ok, ".env and *.pem are gitignored",
        "verified in .gitignore; the private key itself lives outside every git "
        "repository, in ../Kalshi backtester/key/")

    # Checked mechanically, not by eye: verify_readme.py extracts every numeric
    # token from README.md and looks for it in the flattened results. The failure
    # mode this guards against is a number that was true three runs ago.
    readme = os.path.join(os.path.dirname(out_dir) or ".", "README.md")
    if not os.path.exists(readme):
        checks["c8_readme_quotes_results"] = _crit(
            False, "README quotes only numbers present in results.json",
            "README.md does not exist yet", deferred=True)
    else:
        try:
            import subprocess
            import sys as _sys
            r = subprocess.run([_sys.executable, "verify_readme.py"],
                               capture_output=True, text=True, timeout=120)
            tail = (r.stdout or "").strip().splitlines()
            checks["c8_readme_quotes_results"] = _crit(
                r.returncode == 0,
                "README quotes only numbers present in results.json",
                (tail[-2] if r.returncode == 0 and len(tail) >= 2
                 else "verify_readme.py reported untraceable numbers -- run it "
                      "directly for the list"))
        except Exception as exc:  # pragma: no cover - diagnostic path
            checks["c8_readme_quotes_results"] = _crit(
                False, "README quotes only numbers present in results.json",
                f"could not run verify_readme.py: {exc}")

    cr = counts["candle_rows"]
    checks["c9_price_series"] = _crit(
        cr > counts["priced"] * 10,
        "price series stored, not a single row per market",
        f"{cr:,} candle rows for {counts['priced']:,} priced markets "
        f"({counts['candles_per_priced_market']}/market)",
        backs="resume clause 'price series'")

    nq = cat["n_categories_qualifying"]
    per_cat_ok = all(
        all(k in e["full_sample"] for k in ("brier", "log_loss"))
        and "longshot" in e["full_sample"]
        for e in cat["categories"])
    checks["c10_by_category"] = _crit(
        nq >= 3 and per_cat_ok and png("calibration_by_category.png"),
        "by_category block with >= 3 qualifying categories",
        f"{nq} categories at or above min_category_n={cat['min_category_n']}: "
        f"{', '.join(cat['qualifying_categories'])}",
        backs="resume clause 'across event categories'")

    # 11 -- checked trade by trade, not asserted. Entry must be worse than the
    # midpoint AND worse than the passive quote, for every single trade.
    slip = bt["slippage_audit"]
    checks["c11_slippage"] = _crit(
        slip["all_worse_than_mid"] and slip["all_worse_than_passive"]
        and "slippage_cents" in results["config"],
        "entry price strictly worse than mid and passive quote",
        f"{slip['n_trades_checked']} trades checked; "
        f"worse than mid: {slip['all_worse_than_mid']}, "
        f"worse than passive: {slip['all_worse_than_passive']}; "
        f"slippage_cents = {results['config']['slippage_cents']}",
        backs="resume clause 'with costs and slippage'",
        **({"exceptions": slip["exceptions"]} if slip["exceptions"] else {}))

    liq = bt["liquid_subsample"]
    checks["c12_drawdown"] = _crit(
        liq.get("max_drawdown") is not None
        and liq.get("sharpe_per_trade") is not None
        and png("equity_curve.png"),
        "max_drawdown and sharpe_per_trade, out-of-sample only",
        f"sharpe_per_trade {liq.get('sharpe_per_trade')}, "
        f"max_drawdown {liq.get('max_drawdown')} per contract, computed on "
        f"{liq.get('n_trades')} trades that all settled after the split",
        backs="resume clause 'out-of-sample Sharpe and drawdown'")

    hard = {k: v for k, v in checks.items() if not v.get("deferred")}
    return {
        "criteria": checks,
        "n_pass": sum(1 for v in hard.values() if v["pass"]),
        "n_total_excluding_deferred": len(hard),
        "n_deferred": len(checks) - len(hard),
        "all_pass_excluding_deferred": all(v["pass"] for v in hard.values()),
    }


def build_results(config: dict, out_dir: str = "outputs") -> dict:
    """Assemble every number the project produced into one auditable dict.

    This file is the single source of truth the README is allowed to quote from,
    which is the point of building it: a README written from console scrollback
    can drift from the code without anyone noticing, and a reader has no way to
    check it. Everything here is recomputed from the database on each run.
    """
    import datetime as _dt

    from analyze import (calibration_by_category, load_frame, run_backtest,
                         run_calibration, split_by_liquidity)
    from ingest import connect, derive_ingest_counts, verify_ingest

    conn = connect(config["db_path"])
    try:
        counts = derive_ingest_counts(conn, config["horizon_sec"])
        gates = verify_ingest(conn)
    finally:
        conn.close()

    df = load_frame(config["db_path"])
    calibration = run_calibration(df, config, out_dir)
    by_category = calibration_by_category(df, config, out_dir)
    backtest_res = run_backtest(df, config, out_dir)
    backtest_res["slippage_audit"] = audit_slippage(df, config)

    return {
        "run_timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "config": dict(config),
        "counts": counts,
        "gates": gates,
        "calibration": calibration,
        "by_category": by_category,
        "backtest": backtest_res,
    }


def audit_slippage(df, config: dict) -> dict:
    """Criterion 11, checked on every trade rather than asserted.

    The entry price must be strictly worse than the midpoint (which is what a
    naive backtest would have used) and strictly worse than the passive quote
    (which is what a resting order would have got). Any trade failing either test
    is counted and an example is kept, because `apply_slippage` clamps at 0.99
    and a clamp is exactly the kind of thing that can quietly make an entry
    better than the quote it was supposed to worsen.
    """
    from analyze import backtest, split_by_liquidity

    liquid, _ = split_by_liquidity(df, config["max_spread"])
    worse_mid = worse_passive = True
    checked = 0
    exceptions = []
    clamp = {}

    for label, sample in (("full sample", df), ("liquid subsample", liquid)):
        t = backtest(sample, config).get("_trades")
        if t is None or not len(t):
            continue
        checked += len(t)
        mid_entry = 1.0 - t["p_horizon"]        # what a mid-price backtest assumes
        passive_entry = 1.0 - t["yes_ask"]      # what a resting NO order would get
        bad_mid = t[t["entry"] <= mid_entry]
        bad_passive = t[t["entry"] <= passive_entry]
        if len(bad_mid):
            worse_mid = False
        if len(bad_passive):
            worse_passive = False
        # The 0.99 clamp can absorb part or all of the intended 1c slippage.
        # It never makes entry better than the quote, but it does make the cost
        # model softer than advertised on the worst books, so the extent is
        # measured and published rather than described in prose.
        applied = t["entry"] - t["quoted"]
        clamp[label] = {
            "n_trades": int(len(t)),
            "n_clamped": int((applied < config["slippage_cents"] / 100 - 1e-9).sum()),
            "mean_slippage_applied": round(float(applied.mean()), 5),
            "min_slippage_applied": round(float(applied.min()), 5),
            "intended_slippage": config["slippage_cents"] / 100,
        }

        for name, bad in (("not worse than mid", bad_mid),
                          ("not worse than passive quote", bad_passive)):
            if len(bad):
                r = bad.iloc[0]
                exceptions.append({
                    "sample": label, "problem": name, "n": int(len(bad)),
                    "example_ticker": r["ticker"],
                    "yes_bid": round(float(r["yes_bid"]), 4),
                    "yes_ask": round(float(r["yes_ask"]), 4),
                    "entry": round(float(r["entry"]), 4),
                })

    return {
        "n_trades_checked": checked,
        "all_worse_than_mid": worse_mid,
        "all_worse_than_passive": worse_passive,
        "slippage_cents": config["slippage_cents"],
        "clamp_effect": clamp,
        "exceptions": exceptions,
    }


def _print_acceptance(acc: dict) -> None:
    print("\n" + "=" * 70)
    print("ACCEPTANCE CRITERIA (spec section 6)")
    print("=" * 70)
    for key, c in acc["criteria"].items():
        mark = "DEFER" if c.get("deferred") else ("PASS" if c["pass"] else "FAIL")
        num = key.split("_")[0].lstrip("c")
        print(f"[{mark:>5}] {num:>2}. {c['criterion']}")
        print(f"         {c['detail']}")
        if c.get("backs"):
            print(f"         backs: {c['backs']}")
        if c.get("exceptions"):
            print(f"         EXCEPTIONS: {c['exceptions']}")
    print("-" * 70)
    print(f"{acc['n_pass']}/{acc['n_total_excluding_deferred']} pass, "
          f"{acc['n_deferred']} deferred to step 10")


def do_analyze_run(config: dict, out_dir: str = "outputs") -> dict:
    """Run every analysis, write outputs/results.json, check the criteria."""
    import json
    import os

    os.makedirs(out_dir, exist_ok=True)
    results = build_results(config, out_dir)
    path = os.path.join(out_dir, "results.json")

    def _dump():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2, sort_keys=False)

    # Written BEFORE the criteria are evaluated, then rewritten with the
    # acceptance block appended. Criterion 8 shells out to verify_readme.py,
    # which reads results.json off disk -- so checking first would silently grade
    # the README against the PREVIOUS run's file. That is not hypothetical: it
    # passed that way until outputs/ was deleted and the run started clean.
    _dump()
    results["acceptance"] = check_acceptance(results, out_dir)
    _dump()

    cal, cat, bt = results["calibration"], results["by_category"], results["backtest"]
    liq = bt["liquid_subsample"]
    print("\n" + "=" * 70)
    print("ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"markets analysed  : {cal['n_markets']:,}  "
          f"({results['counts']['date_range_utc'][0]} to "
          f"{results['counts']['date_range_utc'][1]})")
    print(f"Brier             : {cal['brier']:.4f}   baseline {cal['baseline_brier']:.4f}"
          f"   skill {cal['full_sample']['brier_skill_score']:+.3f}")
    print(f"log loss          : {cal['log_loss']:.4f}   baseline "
          f"{cal['baseline_log_loss']:.4f}")
    print(f"liquid subsample  : n={cal['liquid_sample']['n_markets']:,}  "
          f"Brier {cal['liquid_sample']['brier']:.4f}  "
          f"skill {cal['liquid_sample']['brier_skill_score']:+.3f}")
    ls = cal["full_sample"]["longshot"]["low_prob_bins"]
    if ls:
        print(f"longshot (p<=0.3) : delta {ls['delta']:+.4f}  z {ls['z']:+.2f}  "
              f"significant: {ls['significant_5pct']}")
    print(f"categories        : {cat['n_categories_qualifying']} qualifying of "
          f"{cat['n_categories']}  skill range {cat['skill_dispersion_full']['range']}")
    print(f"backtest (liquid) : {liq['n_trades']} trades  "
          f"mean {liq['mean_pnl_per_contract']:+.4f}/contract  "
          f"Sharpe/trade {liq['sharpe_per_trade']:+.4f}  "
          f"max drawdown {liq['max_drawdown']:.2f}")
    print(f"\nwrote {path}")

    _print_acceptance(results["acceptance"])
    return results


def main() -> None:
    args = parse_args()
    do_ingest = args.ingest or args.all
    do_analyze = args.analyze or args.all
    if not (do_ingest or do_analyze):
        raise SystemExit("nothing to do: pass --ingest, --analyze, or --all")
    if do_ingest:
        do_ingest_run()
    if do_analyze:
        do_analyze_run(CONFIG)


if __name__ == "__main__":
    main()
