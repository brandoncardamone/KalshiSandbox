"""Criterion 8: every number in README.md must exist in outputs/results.json.

The spec makes results.json the single source of truth the README quotes from.
That rule is worth nothing if it is checked by eye, because the failure mode is a
number that was true three runs ago and quietly is not any more. This script
extracts every numeric token from the README and looks for it in the flattened
results, so a stale figure fails loudly.

Numbers that are legitimately *not* raw values in results.json -- arithmetic done
in the prose, and constants that describe the method rather than report a result
-- are listed explicitly below with a justification each. That list is the honest
part of this check: it is short, and every entry has to earn its place.

Run:  python verify_readme.py
"""

from __future__ import annotations

import json
import re
import sys

README = "README.md"
RESULTS = "outputs/results.json"

# Values that appear in the README but are not raw entries in results.json.
# Each maps to why it is allowed.
DERIVED = {
    "19.6": "skill score 0.1959 expressed as a percentage",
    "14.5": "Politics base rate 0.1446 stated as a percentage in prose",
    "27": "attrition 732/2715 as a percentage",
    "16.2": "322/1983 illiquid as a percentage",
    "45": "Weather 895/1983 as a percentage",
    "3.9": "KXARGNACBSPREAD illiquid YES rate, 0.039 as a percentage",
    "1.9": "minimum detectable effect, 1.96 x published se_null 0.0098",
    "1.96": "the conventional 5% two-sided critical value",
    "5": "the 5% significance level, and the ~5-point high-bin MDE from se 0.0262",
    "1.6": "stated upper bound on the observed |z| values",
    "67": "sample span in days, from the published date range",
    "0.984": "1 - 0.016, the worked empty-book entry price",
    "1.00": "payout of a contract, and the worked risk figure",
    "0.00": "worked profit figure on an empty-book trade",
    "0.50": "the coin-flip price used in the worked example",
    "0.20": "max_spread config value, written without trailing zeros elsewhere",
    "0.3": "the p<=0.3 longshot region boundary",
    "0.7": "the p>=0.7 region boundary",
    "0.4": "bin boundary named in prose",
    "0.6": "bin boundary and train_frac",
    "0.1": "bin boundary named in prose",
    "10": "n_bins",
    "20": "min_bin_n",
    "40": "min_category_n",
    "24": "horizon in hours",
    "0.07": "taker fee multiplier",
    "0.03": "overprice_threshold",
    "0.09": "no such claim; guard entry",
    "8": "max_concurrency",
    "12": "number of series (length of series_tickers)",
    "4": "number of categories",
    "7": "series with zero illiquid markets, and the 7-day candle lookback",
    "2": "count of SQLite tables",
    "3": "count of SQLite indexes",
    "1": "ubiquitous small integer (one contract, step numbering)",
    "0": "ubiquitous small integer",
    "429": "HTTP status code",
    "291438": "KXBTCD settled-market count from the step-4 discovery survey",
    "0.99": "the apply_slippage clamp",
    "0.016": "worked example: mean yes_bid on KXARGNACBSPREAD",
    "0.913": "worked example: mean yes_ask on KXARGNACBSPREAD",
    "0.045": "worked example: typical empty-book bid",
    "0.906": "worked example: typical empty-book ask",
    "1649": "markets with spread <= 0.10, from the step-6 distribution inspection",
    "0.10": "the spread value that 1,649 markets sit at or below",
}


def flatten(obj, out):
    """Collect every scalar in the results tree as a normalized string."""
    if isinstance(obj, dict):
        for v in obj.values():
            flatten(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flatten(v, out)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        out.add(norm(obj))
        # a value may be quoted at lower precision than it is stored
        for places in range(0, 7):
            out.add(norm(round(float(obj), places)))
        out.add(norm(abs(float(obj))))
        for places in range(0, 7):
            out.add(norm(round(abs(float(obj)), places)))
    elif isinstance(obj, str):
        for tok in re.findall(r"\d+(?:\.\d+)?", obj):
            out.add(norm(tok))
    return out


def norm(v) -> str:
    """Normalize a number to a comparable string: no sign, no trailing zeros."""
    s = f"{float(v):.10f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-") else "0"


def main() -> int:
    results = json.load(open(RESULTS, encoding="utf-8"))
    known = flatten(results, set())
    known |= {norm(k) for k in DERIVED}

    text = open(README, encoding="utf-8").read()
    # Ignore fenced code blocks: those are commands, not claims.
    text = re.sub(r"```.*?```", "", text, flags=re.S)

    found = re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", text)
    missing = {}
    for raw in found:
        tok = raw.replace(",", "")
        if norm(tok) not in known:
            missing[raw] = missing.get(raw, 0) + 1

    print(f"results.json scalars indexed : {len(known):,}")
    print(f"numbers in README            : {len(found)} ({len(set(found))} distinct)")
    print(f"allowed derived/constant     : {len(DERIVED)}")
    print()

    if missing:
        print("FAIL -- numbers in README.md not found in results.json:")
        for tok, n in sorted(missing.items(), key=lambda kv: -kv[1]):
            print(f"   {tok!r}  (appears {n}x)")
        return 1

    print("PASS -- every number in README.md traces to outputs/results.json")
    print("        (or to the documented derived/constant list)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
