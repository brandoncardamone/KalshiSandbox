"""Calibration analysis: proper scoring rules, reliability diagram, longshot bias.

The question: when the market said 34%, did it happen about 34% of the time?

Nothing here touches the API. Everything reads from the SQLite store built by
ingest.py, so the analysis is fast, repeatable, and independent of Kalshi being
up.
"""

from __future__ import annotations

import math
import sqlite3

import matplotlib

matplotlib.use("Agg")  # no display needed; write PNGs directly

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

EPS = 1e-6  # clip for log loss, which diverges at 0 and 1


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_frame(db_path: str) -> pd.DataFrame:
    """Load priced markets. Adds `outcome` as 1 for YES, 0 for NO."""
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT ticker, series_ticker, category, title, settle_ts, result, "
            "p_horizon, yes_bid, yes_ask, horizon_ts, tier "
            "FROM markets WHERE p_horizon IS NOT NULL AND result IS NOT NULL "
            "ORDER BY settle_ts",
            conn,
        )
    finally:
        conn.close()
    df["outcome"] = (df["result"] == "yes").astype(int)
    df["spread"] = df["yes_ask"] - df["yes_bid"]
    return df


def split_by_liquidity(df: pd.DataFrame, max_spread: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate markets with a genuine two-sided quote from empty books.

    The ingest already rejects a bid of 0 or an ask of 1, but that is not
    sufficient. A market quoted 0.045 / 0.906 passes that test while carrying no
    information at all: its mid of ~0.48 is an artifact of where two token orders
    happened to sit, not a probability anyone is willing to trade on.

    The observed spread distribution is starkly bimodal -- 1,649 of 1,983 markets
    sit at or below 0.10, then a separate cluster of 322 averages a spread of
    0.861 -- so the cut is reading a real gap in the data, not slicing a
    continuum at a convenient point.

    Returns (liquid, illiquid). Both are reported; nothing is discarded silently.
    """
    liquid = df[df["spread"] <= max_spread]
    illiquid = df[df["spread"] > max_spread]
    return liquid, illiquid


# --------------------------------------------------------------------------
# Proper scoring rules
# --------------------------------------------------------------------------


def brier(p: np.ndarray, o: np.ndarray) -> float:
    """Mean squared error between forecast and outcome.

    Lower is better; 0 is perfect. A forecast that always says 50% scores 0.25.
    """
    p, o = np.asarray(p, dtype=float), np.asarray(o, dtype=float)
    return float(np.mean((p - o) ** 2))


def log_loss(p: np.ndarray, o: np.ndarray) -> float:
    """Negative log likelihood of the outcomes under the forecasts.

    Punishes confident mistakes far harder than Brier does, because the log term
    diverges toward infinity near 0 and 1. Saying "1% chance" about something
    that happens is nearly unforgivable here. Clipped to [EPS, 1-EPS] so a
    forecast of exactly 0 or 1 cannot produce an infinite score.
    """
    p, o = np.asarray(p, dtype=float), np.asarray(o, dtype=float)
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p)))


def baseline_scores(o: np.ndarray) -> dict:
    """Scores for the naive forecaster that always predicts the base rate.

    Reported alongside the real scores because a Brier score means nothing in
    isolation -- it only means something relative to a reference.
    """
    o = np.asarray(o, dtype=float)
    base = float(np.mean(o))
    p = np.full_like(o, base)
    return {
        "base_rate": base,
        "baseline_brier": brier(p, o),
        "baseline_log_loss": log_loss(p, o),
    }


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------


def calibration_table(df: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    """Bin p_horizon into equal-width bins over [0, 1].

    Equal-width rather than quantile bins, deliberately: quantile bins would
    equalize the counts and hide how thin the tails are -- and the tails are
    exactly where longshot bias lives. Empty bins are kept as rows so the plot
    and the table show where the sample simply is not.

    Returns per bin: bin_lo, bin_hi, mean_pred, realized, n, se.
    """
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(df["p_horizon"], edges, right=False) - 1, 0, n_bins - 1)

    rows = []
    for b in range(n_bins):
        sel = df[idx == b]
        n = len(sel)
        if n:
            realized = float(sel["outcome"].mean())
            se = float(np.sqrt(realized * (1 - realized) / n))
            mean_pred = float(sel["p_horizon"].mean())
        else:
            realized = se = mean_pred = np.nan
        rows.append(
            {
                "bin_lo": edges[b],
                "bin_hi": edges[b + 1],
                "mean_pred": mean_pred,
                "realized": realized,
                "n": n,
                "se": se,
                "delta": realized - mean_pred if n else np.nan,
            }
        )
    return pd.DataFrame(rows)


def longshot_summary(tab: pd.DataFrame, min_bin_n: int = 20) -> dict:
    """Quantify deviation, with attention to the low-probability bins.

    delta = realized - mean_pred.
      negative delta  -> outcomes happened LESS often than priced (overpriced)
      positive delta  -> more often than priced (underpriced)

    Longshot bias is specifically a negative delta at low predicted probability:
    cheap unlikely outcomes being bid above their true frequency.

    Bins below min_bin_n are reported but excluded from every claim, because at
    small n the noise looks exactly like the effect.
    """
    usable = tab[(tab["n"] >= min_bin_n) & tab["realized"].notna()]
    low = usable[usable["bin_hi"] <= 0.3]
    high = usable[usable["bin_lo"] >= 0.7]

    def block(sub):
        """Aggregate a group of bins and test the delta against noise.

        The standard error is taken under the null hypothesis -- that outcomes
        arrived at exactly the rate the market priced -- so it uses mean_pred,
        not realized. Using realized would divide by zero whenever a group of
        markets all resolved the same way, which is common in the tails: fifty
        markets priced at 0.95 that all settled YES would otherwise report an
        infinite z instead of a modest one.
        """
        if sub.empty:
            return None
        n = int(sub["n"].sum())
        wpred = float((sub["mean_pred"] * sub["n"]).sum() / n)
        wreal = float((sub["realized"] * sub["n"]).sum() / n)
        se = float(np.sqrt(wpred * (1 - wpred) / n)) if 0 < wpred < 1 else None
        return {
            "n": n,
            "mean_pred": round(wpred, 4),
            "realized": round(wreal, 4),
            "delta": round(wreal - wpred, 4),
            "se_null": round(se, 4) if se else None,
            "z": round((wreal - wpred) / se, 2) if se else None,
            "significant_5pct": bool(se and abs((wreal - wpred) / se) >= 1.96),
        }

    return {
        "min_bin_n": min_bin_n,
        "bins_interpreted": int(len(usable)),
        "bins_excluded_small_n": int((tab["n"] < min_bin_n).sum()),
        "per_bin": [
            {
                "range": f"{r.bin_lo:.1f}-{r.bin_hi:.1f}",
                "mean_pred": None if np.isnan(r.mean_pred) else round(r.mean_pred, 4),
                "realized": None if np.isnan(r.realized) else round(r.realized, 4),
                "delta": None if np.isnan(r.delta) else round(r.delta, 4),
                "n": int(r.n),
                "interpreted": bool(r.n >= min_bin_n),
            }
            for r in tab.itertuples()
        ],
        "low_prob_bins": block(low),    # p <= 0.3
        "high_prob_bins": block(high),  # p >= 0.7
    }


# --------------------------------------------------------------------------
# Plot
# --------------------------------------------------------------------------


def _draw_reliability(
    ax,
    tab: pd.DataFrame,
    color: str,
    label: str,
    min_bin_n: int = 20,
    marker: str = "o",
    z: int = 3,
    annotate: bool = True,
    ms: float = 7,
    label_small: bool = True,
) -> None:
    """Draw one reliability curve with binomial error bars onto `ax`.

    Bins below min_bin_n are drawn hollow and faded rather than omitted: the
    reader should be able to see that the tail was sampled thinly, not be left
    to assume the curve simply stops there.
    """
    pts = tab[tab["realized"].notna()]
    big = pts[pts["n"] >= min_bin_n]
    small = pts[pts["n"] < min_bin_n]
    if not big.empty:
        ax.errorbar(big["mean_pred"], big["realized"], yerr=big["se"],
                    fmt=marker, ms=ms, capsize=4, lw=1.4, color=color,
                    label=label, zorder=z)
    if not small.empty:
        ax.errorbar(small["mean_pred"], small["realized"], yerr=small["se"],
                    fmt=marker, ms=ms, capsize=4, lw=1.4, color=color,
                    alpha=0.35, mfc="white", zorder=z,
                    label=(f"{label} — n<{min_bin_n}, not interpreted"
                           if label_small else None))
    if annotate:
        for r in pts.itertuples():
            ax.annotate(f"n={int(r.n)}", (r.mean_pred, r.realized),
                        textcoords="offset points", xytext=(7, -12),
                        fontsize=7.5, color=color)


def plot_calibration(
    tab: pd.DataFrame,
    out_path: str,
    n_total: int,
    horizon_hours: int,
    tab_liquid: pd.DataFrame | None = None,
    max_spread: float | None = None,
    n_liquid: int | None = None,
) -> None:
    """Reliability diagram: predicted vs realized, with the identity line.

    Plots the full sample and, when given, the liquid subsample over the same
    diagonal. Showing both is the point: the gap between the two lines IS the
    finding, and plotting only one of them would hide it either way.
    """
    fig, ax = plt.subplots(figsize=(7.6, 7.2))

    ax.plot([0, 1], [0, 1], "--", color="#888888", lw=1.2,
            label="perfect calibration", zorder=1)

    def draw(t, color, label, z=3, annotate=True):
        _draw_reliability(ax, t, color, label, z=z, annotate=annotate)

    if tab_liquid is not None:
        draw(tab, "#d62728", f"all markets (n={n_total:,})", annotate=False)
        draw(tab_liquid, "#1f77b4",
             f"spread ≤ {max_spread:.2f} (n={n_liquid:,})", z=4)
    else:
        draw(tab, "#1f77b4", f"all markets (n={n_total:,})")

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Market-implied probability (mid-price at horizon)")
    ax.set_ylabel("Realized frequency of YES")
    ax.set_title(
        f"Kalshi calibration: {n_total:,} settled markets\n"
        f"implied probability read {horizon_hours}h before settlement",
        fontsize=12,
    )
    ax.grid(alpha=0.25, lw=0.6)
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_longshot(
    tab: pd.DataFrame,
    out_path: str,
    n_total: int,
    horizon_hours: int,
    summary: dict,
    tab_liquid: pd.DataFrame | None = None,
    max_spread: float | None = None,
    n_liquid: int | None = None,
    summary_liquid: dict | None = None,
    min_bin_n: int = 20,
) -> None:
    """Deviation from the priced probability, which is where longshot bias lives.

    The reliability diagram answers "is it calibrated"; this chart answers "and
    if not, in which direction, and by how much". It plots
    `delta = realized - mean_pred` against the priced probability, so perfect
    calibration is the flat zero line rather than the diagonal, and the vertical
    axis is directly readable in percentage points of mispricing.

    Longshot bias would appear as points sitting BELOW zero on the left of the
    chart: unlikely outcomes happening less often than they were priced. The
    p <= 0.3 region is shaded to make that region unambiguous, and the measured
    aggregate delta for it is printed on the chart with its z-score, so the
    figure states the negative result rather than leaving it to be inferred from
    points that look close to a line.
    """
    fig, ax = plt.subplots(figsize=(9.5, 6.4))

    ax.axhspan(-1, 1, xmin=0, xmax=0.3, color="#f0f0f0", zorder=0)
    ax.text(0.145, 0.022, "longshot region (p ≤ 0.3)", ha="center", va="bottom",
            transform=ax.get_xaxis_transform(), fontsize=9, color="#999999",
            zorder=1)
    ax.axhline(0.0, color="#333333", lw=1.3, ls="--", zorder=2,
               label="perfectly calibrated (delta = 0)")

    def draw(t, color, label, z, off=0):
        pts = t[t["realized"].notna()]
        big, small = pts[pts["n"] >= min_bin_n], pts[pts["n"] < min_bin_n]
        if not big.empty:
            ax.errorbar(big["mean_pred"], big["delta"], yerr=big["se"], fmt="o",
                        ms=7, capsize=4, lw=1.4, color=color, label=label, zorder=z)
        if not small.empty:
            ax.errorbar(small["mean_pred"], small["delta"], yerr=small["se"],
                        fmt="o", ms=7, capsize=4, lw=1.4, color=color, alpha=0.35,
                        mfc="white", zorder=z)
        for i, r in enumerate(pts.itertuples()):
            ax.annotate(f"n={int(r.n)}", (r.mean_pred, r.delta),
                        textcoords="offset points",
                        xytext=(8, 5 if (i + off) % 2 else -13),
                        fontsize=7.5, color=color)

    if tab_liquid is not None:
        draw(tab, "#d62728", f"all markets (n={n_total:,})", 3, off=0)
        draw(tab_liquid, "#1f77b4",
             f"spread ≤ {max_spread:.2f} (n={n_liquid:,})", 4, off=1)
    else:
        draw(tab, "#1f77b4", f"all markets (n={n_total:,})", 3)

    # State the measured result on the figure itself.
    src = summary_liquid or summary
    lo, hi = src.get("low_prob_bins"), src.get("high_prob_bins")
    lines = []
    if lo:
        lines.append(
            "p ≤ 0.3:  delta {:+.4f}   z = {:+.2f}   n = {}   {}".format(
                lo["delta"], lo["z"], lo["n"],
                "SIGNIFICANT" if lo["significant_5pct"] else "not significant"))
    if hi:
        lines.append(
            "p ≥ 0.7:  delta {:+.4f}   z = {:+.2f}   n = {}   {}".format(
                hi["delta"], hi["z"], hi["n"],
                "SIGNIFICANT" if hi["significant_5pct"] else "not significant"))
    if lines:
        which = "liquid subsample" if summary_liquid else "full sample"
        ax.text(0.985, 0.975, (which + "\n" + "\n".join(lines)),
                transform=ax.transAxes, ha="right", va="top", fontsize=9,
                family="monospace",
                bbox=dict(boxstyle="round,pad=0.5", fc="#ffffff", ec="#bbbbbb"))

    lim = float(np.nanmax(np.abs(np.concatenate([
        tab["delta"].to_numpy(dtype=float),
        (tab_liquid["delta"].to_numpy(dtype=float)
         if tab_liquid is not None else np.array([0.0]))]))))
    lim = max(0.12, min(lim * 1.55, 1.0))
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-lim, lim)
    ax.set_xlabel("Market-implied probability (mid-price at horizon)")
    ax.set_ylabel("delta  =  realized frequency − implied probability")
    ax.set_title(
        "Longshot bias check: {:,} settled markets, priced {}h before settlement\n"
        "below zero = outcomes happened LESS often than priced (overpriced)".format(
            n_total, horizon_hours),
        fontsize=12)
    ax.grid(alpha=0.25, lw=0.6)
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------------


def _score_block(sub: pd.DataFrame, n_bins: int, min_bin_n: int) -> dict:
    """Scores, calibration table and longshot summary for one sample."""
    p, o = sub["p_horizon"].to_numpy(), sub["outcome"].to_numpy()
    tab = calibration_table(sub, n_bins)
    scores = {"brier": brier(p, o), "log_loss": log_loss(p, o), **baseline_scores(o)}
    scores["brier_skill_score"] = (
        1 - scores["brier"] / scores["baseline_brier"] if scores["baseline_brier"] else None
    )
    return {
        "n_markets": int(len(sub)),
        "mean_spread": round(float(sub["spread"].mean()), 4),
        **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in scores.items()},
        "calibration_table": tab.replace({np.nan: None}).to_dict(orient="records"),
        "longshot": longshot_summary(tab, min_bin_n),
        "_tab": tab,
    }


def run_calibration(df: pd.DataFrame, config: dict, out_dir: str = "outputs") -> dict:
    """Headline calibration metrics, table, plot, and longshot summary.

    Reported on the full sample AND on the liquid subsample. Both appear in
    results.json: the liquidity split turned out to be the dominant story in this
    data, and reporting only one of the two would misrepresent it in one
    direction or the other.
    """
    n_bins, min_bin_n = config["n_bins"], config["min_bin_n"]
    max_spread = config["max_spread"]
    liquid, illiquid = split_by_liquidity(df, max_spread)

    full_block = _score_block(df, n_bins, min_bin_n)
    liq_block = _score_block(liquid, n_bins, min_bin_n)
    illiq_block = _score_block(illiquid, n_bins, min_bin_n) if len(illiquid) else None

    plot_calibration(
        full_block["_tab"],
        f"{out_dir}/calibration.png",
        n_total=len(df),
        horizon_hours=config["horizon_sec"] // 3600,
        tab_liquid=liq_block["_tab"],
        max_spread=max_spread,
        n_liquid=len(liquid),
    )
    plot_longshot(
        full_block["_tab"],
        f"{out_dir}/longshot_bias.png",
        n_total=len(df),
        horizon_hours=config["horizon_sec"] // 3600,
        summary=full_block["longshot"],
        tab_liquid=liq_block["_tab"],
        max_spread=max_spread,
        n_liquid=len(liquid),
        summary_liquid=liq_block["longshot"],
        min_bin_n=min_bin_n,
    )

    for b in (full_block, liq_block, illiq_block):
        if b is not None:
            b.pop("_tab", None)

    return {
        "n_markets": int(len(df)),
        "horizon_hours": config["horizon_sec"] // 3600,
        "max_spread": max_spread,
        "full_sample": full_block,
        "liquid_sample": liq_block,
        "illiquid_sample": illiq_block,
        # convenience mirrors of the headline numbers, full sample
        "brier": full_block["brier"],
        "log_loss": full_block["log_loss"],
        "baseline_brier": full_block["baseline_brier"],
        "baseline_log_loss": full_block["baseline_log_loss"],
        "base_rate": full_block["base_rate"],
        "calibration_table": full_block["calibration_table"],
        "longshot": full_block["longshot"],
    }


# --------------------------------------------------------------------------
# Per-category breakdown  (step 7)
# --------------------------------------------------------------------------


def _cat_entry(name: str, sub: pd.DataFrame, config: dict) -> dict:
    """Everything measured for a single category, on both samples.

    Both the full category sample and its liquid subsample are scored, because
    the empty-book cluster found in step 6 is not spread evenly across
    categories -- reporting only one of the two would credit or blame a category
    for its order-book depth rather than for its forecasting.
    """
    n_bins, min_bin_n = config["n_bins"], config["min_bin_n"]
    liquid, illiquid = split_by_liquidity(sub, config["max_spread"])

    full_block = _score_block(sub, n_bins, min_bin_n)
    liq_block = _score_block(liquid, n_bins, min_bin_n) if len(liquid) else None
    # Scored too, because the illiquid half is where the per-category surprises
    # live: Sports' negative headline skill comes entirely from its illiquid
    # block, and a reader cannot check that claim unless the number is published.
    illiq_block = _score_block(illiquid, n_bins, min_bin_n) if len(illiquid) else None

    return {
        "category": name,
        "n_markets": int(len(sub)),
        "n_liquid": int(len(liquid)),
        "n_illiquid": int(len(illiquid)),
        "liquid_pct": round(100.0 * len(liquid) / len(sub), 1) if len(sub) else None,
        "series": sorted(sub["series_ticker"].unique().tolist()),
        "n_series": int(sub["series_ticker"].nunique()),
        "date_range": [int(sub["settle_ts"].min()), int(sub["settle_ts"].max())],
        "interpreted": bool(len(sub) >= config["min_category_n"]),
        "note": (
            None if len(sub) >= config["min_category_n"]
            else "insufficient sample: n={} < min_category_n={}; "
                 "reported, not interpreted".format(len(sub), config["min_category_n"])
        ),
        "full_sample": full_block,
        "liquid_sample": liq_block,
        "illiquid_sample": illiq_block,
    }


def plot_category_calibration(
    entries: list[dict],
    out_path: str,
    horizon_hours: int,
    max_spread: float,
    min_category_n: int,
) -> None:
    """One reliability diagram per category, on shared axis limits.

    Identical axes on every panel deliberately: the panels exist to be compared
    to each other, and rescaling each to its own data would make a category that
    only ever trades between 0.1 and 0.3 look like it spans the whole range.
    """
    # One overlay panel (spec 5.3: "one line per qualifying category over the
    # shared diagonal") followed by one panel per category. The overlay answers
    # "do the categories differ"; the individual panels answer "how", and each
    # question is illegible on the other's chart.
    n = len(entries) + 1
    ncols = 2 if n > 1 else 1
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.0 * ncols, 5.8 * nrows),
                             squeeze=False)
    flat = axes.ravel()

    ax0 = flat[0]
    ax0.plot([0, 1], [0, 1], "--", color="#888888", lw=1.1, zorder=1)
    palette = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b"]
    for k, e in enumerate([x for x in entries if x["interpreted"]]):
        block = e["liquid_sample"] or e["full_sample"]
        t = block["_tab"]
        pts = t[(t["realized"].notna()) & (t["n"] >= 20)]
        if pts.empty:
            continue
        ax0.plot(pts["mean_pred"], pts["realized"], "-o", ms=5, lw=1.5,
                 color=palette[k % len(palette)],
                 label="{} (n={:,})".format(e["category"], block["n_markets"]))
    ax0.set_xlim(-0.02, 1.02)
    ax0.set_ylim(-0.02, 1.02)
    ax0.set_aspect("equal")
    ax0.grid(alpha=0.25, lw=0.6)
    ax0.set_xlabel("Market-implied probability", fontsize=9)
    ax0.set_ylabel("Realized frequency of YES", fontsize=9)
    ax0.set_title("All qualifying categories, shared diagonal\n"
                  "liquid subsample, bins with n ≥ 20", fontsize=10.5)
    ax0.legend(loc="upper left", fontsize=8, framealpha=0.9)

    for ax, e in zip(flat[1:], entries):
        ax.plot([0, 1], [0, 1], "--", color="#888888", lw=1.1, zorder=1)

        full, liq = e["full_sample"], e["liquid_sample"]
        _draw_reliability(ax, full["_tab"], "#d62728",
                          "all (n={:,})".format(e["n_markets"]),
                          z=3, annotate=False, ms=6, label_small=False)
        if liq is not None:
            _draw_reliability(ax, liq["_tab"], "#1f77b4",
                              "spread ≤ {:.2f} (n={:,})".format(max_spread, e["n_liquid"]),
                              z=4, annotate=False, ms=6, label_small=False)

        flag = "" if e["interpreted"] else "  [n < {}: not interpreted]".format(min_category_n)
        ax.set_title(
            "{}{}\nBrier {:.4f} vs base-rate {:.4f}   |   {:.0f}% liquid".format(
                e["category"], flag, full["brier"], full["baseline_brier"],
                e["liquid_pct"]),
            fontsize=10.5,
        )
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_aspect("equal")
        ax.grid(alpha=0.25, lw=0.6)
        ax.set_xlabel("Market-implied probability", fontsize=9)
        ax.set_ylabel("Realized frequency of YES", fontsize=9)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
        if not e["interpreted"]:
            for s in ax.spines.values():
                s.set_color("#d62728")
                s.set_linewidth(1.6)

    for ax in flat[n:]:
        ax.axis("off")

    fig.suptitle(
        "Calibration by event category — implied probability read "
        "{}h before settlement".format(horizon_hours),
        fontsize=13,
    )
    fig.text(0.5, 0.005,
             "Hollow faded markers are bins with n < {} and are not "
             "interpreted. Error bars are binomial standard errors.".format(20),
             ha="center", fontsize=9, color="#555555")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def calibration_by_category(df: pd.DataFrame, config: dict,
                            out_dir: str = "outputs") -> dict:
    """Repeat the step-6 calibration question inside each event category.

    The aggregate curve mixes categories with very different structures. Daily
    temperature markets are ~6 mutually exclusive buckets of which exactly one
    resolves YES, so that sample sits at low probability BY CONSTRUCTION, not
    because anyone mispriced anything. Splitting by category is what separates a
    structural artifact from a genuine forecasting error.

    Categories below min_category_n are scored and reported with their n and an
    explicit note, never dropped -- dropping the thin ones would leave a reader
    unable to tell a category that was absent from one that was inconvenient.
    """
    min_category_n = config["min_category_n"]

    entries = [
        _cat_entry(name, sub, config)
        for name, sub in df.groupby("category", sort=False)
    ]
    # interpreted categories first, best Brier first within each group
    entries.sort(key=lambda e: (not e["interpreted"], e["full_sample"]["brier"]))

    plot_category_calibration(
        entries, "{}/calibration_by_category.png".format(out_dir),
        horizon_hours=config["horizon_sec"] // 3600,
        max_spread=config["max_spread"],
        min_category_n=min_category_n,
    )
    for e in entries:
        for key in ("full_sample", "liquid_sample", "illiquid_sample"):
            if e[key] is not None:
                e[key].pop("_tab", None)

    qualifying = [e for e in entries if e["interpreted"]]

    def _dispersion(key: str) -> dict | None:
        """How much does calibration actually vary between categories?

        A wide spread of skill scores means the aggregate number was hiding real
        differences; a narrow one means the aggregate was a fair summary of all
        of them.
        """
        vals = [e[key]["brier_skill_score"] for e in qualifying
                if e[key] is not None and e[key]["brier_skill_score"] is not None]
        if len(vals) < 2:
            return None
        return {
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "range": round(max(vals) - min(vals), 4),
        }

    def _row(e: dict) -> dict:
        full, liq = e["full_sample"], e["liquid_sample"]
        ill = e["illiquid_sample"]
        low = full["longshot"]["low_prob_bins"]
        high = full["longshot"]["high_prob_bins"]
        low_l = liq["longshot"]["low_prob_bins"] if liq else None
        high_l = liq["longshot"]["high_prob_bins"] if liq else None
        return {
            "category": e["category"],
            "n": e["n_markets"],
            "n_liquid": e["n_liquid"],
            "liquid_pct": e["liquid_pct"],
            "base_rate": round(full["base_rate"], 4),
            "brier": full["brier"],
            "baseline_brier": full["baseline_brier"],
            "brier_skill_score": full["brier_skill_score"],
            "log_loss": full["log_loss"],
            "brier_liquid": liq["brier"] if liq else None,
            "brier_skill_score_liquid": liq["brier_skill_score"] if liq else None,
            "n_illiquid": e["n_illiquid"],
            "brier_illiquid": ill["brier"] if ill else None,
            "brier_skill_score_illiquid": ill["brier_skill_score"] if ill else None,
            # longshot deltas, full sample and liquid subsample, each with the
            # z against the null that outcomes matched the priced probability
            "delta_low_bins": low["delta"] if low else None,
            "z_low_bins": low["z"] if low else None,
            "n_low_bins": low["n"] if low else None,
            "delta_high_bins": high["delta"] if high else None,
            "z_high_bins": high["z"] if high else None,
            "n_high_bins": high["n"] if high else None,
            "delta_low_bins_liquid": low_l["delta"] if low_l else None,
            "z_low_bins_liquid": low_l["z"] if low_l else None,
            "delta_high_bins_liquid": high_l["delta"] if high_l else None,
            "z_high_bins_liquid": high_l["z"] if high_l else None,
            "interpreted": e["interpreted"],
            "note": e["note"],
        }

    return {
        "min_category_n": min_category_n,
        "n_categories": len(entries),
        "n_categories_qualifying": len(qualifying),
        "qualifying_categories": [e["category"] for e in qualifying],
        "insufficient_sample_categories": [
            {"category": e["category"], "n": e["n_markets"]}
            for e in entries if not e["interpreted"]
        ],
        "comparison": [_row(e) for e in entries],
        "skill_dispersion_full": _dispersion("full_sample"),
        "skill_dispersion_liquid": _dispersion("liquid_sample"),
        "categories": entries,
    }


# --------------------------------------------------------------------------
# Backtest: costs, slippage, drawdown  (step 8)
# --------------------------------------------------------------------------


def taker_fee(price: float, contracts: int = 1) -> float:
    """Kalshi taker fee, rounded UP to the next cent.

    fee = ceil(0.07 * contracts * price * (1 - price) * 100) / 100

    Peaks at $0.0175 per contract at a price of 0.50 and falls toward zero at
    both extremes, because a contract at 0.98 has little value at risk.

    ASSUMPTION, and it must stay disclosed: the general 0.07 multiplier is used
    for every market. Kalshi charges different multipliers for some categories.
    The series objects fetched during discovery carry a `fee_multiplier` field,
    so this is verifiable rather than merely assumed -- see the disclosure in the
    README. Rounding up (never down) keeps the cost model pessimistic.
    """
    return math.ceil(0.07 * contracts * price * (1 - price) * 100) / 100


def apply_slippage(quoted_price: float, slippage_cents: float) -> float:
    """Make the execution price strictly worse than the quote.

    Backs the resume phrase "costs and slippage". Two separate components, and
    both are applied:

      1. SPREAD COST -- handled by the caller, which passes `1 - yes_bid` for a
         NO position rather than `1 - yes_ask`. That is crossing the spread:
         paying what someone will actually deal at, not the flattering midpoint.
         Assuming execution at the mid is the single most common way a backtest
         lies to itself.
      2. IMPACT / LATENCY -- this function: a further `slippage_cents` adverse to
         that price, for the delay between deciding and trading and for the
         effect of the order itself on a thin book.

    Clamped to 0.99 so the entry stays a valid contract price.
    """
    return min(quoted_price + slippage_cents / 100.0, 0.99)


def max_drawdown(equity: np.ndarray) -> float:
    """Largest peak-to-trough decline of a cumulative PnL curve.

    Returned in the curve's own units -- dollars per contract at unit size --
    and always <= 0.

    DEVIATION FROM THE SPEC, deliberate. Spec section 5.4 defines this as
    `min(equity / peak - 1)`, which is the right formula for a NAV curve that
    starts at some positive value. This curve is cumulative profit and starts at
    exactly 0, so that formula divides by zero on the first trade, and inverts
    its sign for every stretch where cumulative PnL is negative. The absolute
    peak-to-trough decline needs no starting-capital assumption, and this project
    makes none: position sizing is out of scope, so there is no bankroll to take
    a percentage of. `max_drawdown_fraction()` keeps the spec's form for anyone
    who wants it, guarded.

    The running peak starts at 0, not at the first trade, so a curve that only
    ever loses money is measured from where it began rather than from its first
    (already negative) point.
    """
    equity = np.asarray(equity, dtype=float)
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    return float(np.min(equity - peak))


def max_drawdown_fraction(equity: np.ndarray) -> float | None:
    """The spec's `min(equity/peak - 1)`, evaluated only where it is defined.

    Restricted to points where the running peak is strictly positive. Returns
    None when the curve never rises above its starting 0, which is exactly the
    case where the ratio form has no meaning.
    """
    equity = np.asarray(equity, dtype=float)
    if equity.size == 0:
        return None
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    ok = peak > 0
    if not ok.any():
        return None
    return float(np.min(equity[ok] / peak[ok] - 1.0))


def select_overpriced_bins(train: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Bins the TRAIN window says are overpriced. Never sees test data.

    A bin qualifies when outcomes arrived materially less often than the price
    implied (`realized < mean_pred - overprice_threshold`) on a sample large
    enough to mean something (`n >= min_bin_n`). Both conditions are declared
    CONFIG values, fixed before the test window is touched.

    This function is the whole defence against lookahead bias, which is the
    first thing a knowledgeable reader checks for. It takes `train` as its only
    data argument specifically so that it *cannot* see the test set.
    """
    tab = calibration_table(train, config["n_bins"])
    return tab[(tab["realized"] < tab["mean_pred"] - config["overprice_threshold"])
               & (tab["n"] >= config["min_bin_n"])]


def backtest(df: pd.DataFrame, config: dict) -> dict:
    """Fade the mispricing: buy NO where the training window says YES is dear.

    1. Sort by settle_ts and split at the train_frac quantile, by TIME.
    2. Pick overpriced bins on TRAIN ONLY.
    3. On TEST ONLY, buy one NO contract in every market whose p_horizon lands
       in one of those bins. Entry crosses the spread and then takes slippage.
    4. Score the trades in settlement order.

    Every reported metric is out-of-sample by construction: step 2 touches only
    markets that had already settled before the split timestamp.

    Returns the metrics plus the trade-by-trade frame under "_trades", which the
    plot needs and the caller drops before serializing.
    """
    d = df.sort_values("settle_ts").reset_index(drop=True)
    split_ts = float(d["settle_ts"].quantile(config["train_frac"]))
    train = d[d["settle_ts"] <= split_ts]
    test = d[d["settle_ts"] > split_ts]

    sel = select_overpriced_bins(train, config)
    edges = np.linspace(0.0, 1.0, config["n_bins"] + 1)

    base = {
        "split_ts": int(split_ts),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "train_frac": config["train_frac"],
        "overprice_threshold": config["overprice_threshold"],
        "slippage_cents": config["slippage_cents"],
        "fee_multiplier_assumed": 0.07,
        "bins_selected_on_train": [
            {
                "range": "{:.1f}-{:.1f}".format(r.bin_lo, r.bin_hi),
                "mean_pred": round(float(r.mean_pred), 4),
                "realized": round(float(r.realized), 4),
                "delta": round(float(r.delta), 4),
                "n_train": int(r.n),
            }
            for r in sel.itertuples()
        ],
    }

    if sel.empty:
        return {**base, "n_trades": 0,
                "note": "no bin in the training window met the overpricing "
                        "threshold; the strategy takes no position",
                "statistically_meaningful": False, "_trades": None}

    idx = np.clip(np.digitize(test["p_horizon"], edges, right=False) - 1,
                  0, config["n_bins"] - 1)
    trades = test[np.isin(idx, sel.index.to_numpy())].copy()

    if trades.empty:
        return {**base, "n_trades": 0,
                "note": "training window selected bins, but no test market "
                        "priced into them",
                "statistically_meaningful": False, "_trades": None}

    # Cross the spread: a NO contract costs 1 - yes_bid, not 1 - yes_ask.
    trades["quoted"] = 1.0 - trades["yes_bid"]
    trades["entry"] = trades["quoted"].apply(
        lambda q: apply_slippage(q, config["slippage_cents"]))
    trades["fee"] = trades["entry"].apply(taker_fee)
    trades["payout"] = (trades["outcome"] == 0).astype(float)
    trades["pnl"] = trades["payout"] - trades["entry"] - trades["fee"]
    trades = trades.sort_values("settle_ts").reset_index(drop=True)
    trades["equity"] = trades["pnl"].cumsum()

    # Cost attribution. gross is what the trade would have earned executing at
    # the midpoint with no fee -- the fantasy version. The three cost terms below
    # sum exactly to the gap between that and the real pnl, which is the whole
    # point of the "with costs and slippage" claim: it should be possible to see
    # how much each one took.
    trades["gross_pnl_at_mid"] = trades["payout"] - (1.0 - trades["p_horizon"])
    trades["cost_spread"] = trades["quoted"] - (1.0 - trades["p_horizon"])
    trades["cost_slippage"] = trades["entry"] - trades["quoted"]

    pnl = trades["pnl"].to_numpy()
    equity = trades["equity"].to_numpy()
    sd = float(np.std(pnl, ddof=1)) if len(pnl) > 1 else 0.0
    n_trades = int(len(trades))

    # A NO contract bought at `entry` pays 1.0 or 0.0, so the trade only makes
    # money if it wins more often than entry + fee. Comparing the achieved hit
    # rate to that threshold says whether the strategy was close or not close.
    breakeven = float((trades["entry"] + trades["fee"]).mean())
    peak_equity = float(np.maximum.accumulate(np.concatenate([[0.0], equity]))[-1])

    def _t(x):
        """t-statistic of a mean PnL against zero. Without this a mean of
        +0.0086 per contract reads as a small edge when it is in fact
        indistinguishable from no edge whatsoever."""
        x = np.asarray(x, dtype=float)
        if x.size < 2:
            return None
        se = float(np.std(x, ddof=1)) / math.sqrt(x.size)
        return round(float(np.mean(x)) / se, 2) if se else None

    t_net = _t(pnl)
    t_gross = _t(trades["gross_pnl_at_mid"].to_numpy())

    return {
        **base,
        "n_trades": n_trades,
        "hit_rate": round(float(trades["payout"].mean()), 4),
        "breakeven_hit_rate": round(breakeven, 4),
        "hit_rate_shortfall": round(float(trades["payout"].mean()) - breakeven, 4),
        "mean_entry_price": round(float(trades["entry"].mean()), 4),
        "mean_fee": round(float(trades["fee"].mean()), 4),
        "mean_slippage_cost": round(
            float((trades["entry"] - (1.0 - trades["p_horizon"])).mean()), 4),
        "mean_gross_pnl_at_mid": round(float(trades["gross_pnl_at_mid"].mean()), 4),
        "mean_cost_spread": round(float(trades["cost_spread"].mean()), 4),
        "mean_cost_slippage": round(float(trades["cost_slippage"].mean()), 4),
        "mean_cost_fee": round(float(trades["fee"].mean()), 4),
        "mean_pnl_per_contract": round(float(np.mean(pnl)), 4),
        "t_stat_gross_at_mid": t_gross,
        "gross_edge_significant_5pct": bool(t_gross is not None and abs(t_gross) >= 1.96),
        "t_stat_net": t_net,
        "net_pnl_significant_5pct": bool(t_net is not None and abs(t_net) >= 1.96),
        "total_pnl": round(float(np.sum(pnl)), 4),
        "std_pnl": round(sd, 4),
        "sharpe_per_trade": round(float(np.mean(pnl) / sd), 4) if sd else None,
        "max_drawdown": round(max_drawdown(equity), 4),
        "peak_equity": round(peak_equity, 4),
        "max_drawdown_fraction": (
            round(max_drawdown_fraction(equity), 4)
            if max_drawdown_fraction(equity) is not None else None),
        # The spec's ratio form divides by the running peak. When the curve
        # barely clears zero before falling, that peak is a few cents and the
        # ratio explodes into a meaningless number. Quote `max_drawdown`.
        "max_drawdown_fraction_reliable": bool(peak_equity >= 1.0),
        "final_equity": round(float(equity[-1]), 4),
        "statistically_meaningful": bool(n_trades >= 30),
        "note": (None if n_trades >= 30 else
                 "n_trades < 30: reported, but not statistically meaningful"),
        "_trades": trades,
    }


def plot_equity_curve(results: dict, out_path: str, slippage_cents: float) -> None:
    """Two panels: what the strategy earned, and what costs took from it.

    LEFT  -- net cumulative PnL for every sample that traded, on shared axes,
             with break-even drawn. On a chart where every line is under zero,
             the zero line is the only reference that matters.
    RIGHT -- the same trades for the liquid subsample, scored twice: once at the
             midpoint with no costs at all, and once as actually modelled. The
             gap between those two curves IS the cost of trading, and separating
             them is the difference between "there was no edge" and "there was an
             edge and it was too small to pay for" -- which are very different
             claims about a market.
    """
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(15.0, 6.0))
    colors = {"full sample": "#d62728", "liquid subsample": "#1f77b4"}
    drawn = False

    for label, res in results.items():
        t = res.get("_trades")
        if t is None or not len(t):
            continue
        drawn = True
        ax.plot(pd.to_datetime(t["settle_ts"], unit="s"), t["equity"], lw=1.6,
                color=colors.get(label, "#666666"),
                label="{} — {} trades, mean {:+.4f}/contract, Sharpe {}".format(
                    label, res["n_trades"], res["mean_pnl_per_contract"],
                    "n/a" if res["sharpe_per_trade"] is None
                    else "{:+.3f}".format(res["sharpe_per_trade"])))

    if not drawn:
        ax.text(0.5, 0.5, "no trades taken", ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color="#666666")

    ax.axhline(0, color="#333333", lw=1.0, ls="--", label="break-even")
    ax.set_xlabel("Settlement date (out-of-sample window)")
    ax.set_ylabel("Cumulative PnL, dollars per contract at unit size")
    ax.set_title("Net of all costs", fontsize=11.5)
    ax.grid(alpha=0.25, lw=0.6)
    ax.legend(loc="lower left", fontsize=8.5, framealpha=0.9)

    liq = results.get("liquid subsample", {})
    t = liq.get("_trades")
    if t is not None and len(t):
        x = pd.to_datetime(t["settle_ts"], unit="s")
        ax2.plot(x, t["gross_pnl_at_mid"].cumsum(), lw=1.6, color="#2ca02c",
                 label="at the midpoint, no costs — the fantasy version")
        ax2.plot(x, t["equity"], lw=1.6, color="#1f77b4",
                 label="as modelled: spread + {:.0f}¢ slippage + fee".format(
                     slippage_cents))
        ax2.fill_between(x, t["gross_pnl_at_mid"].cumsum(), t["equity"],
                         color="#d62728", alpha=0.13,
                         label="cost of trading ({:.4f}/contract)".format(
                             liq["mean_cost_spread"] + liq["mean_cost_slippage"]
                             + liq["mean_cost_fee"]))
        ax2.axhline(0, color="#333333", lw=1.0, ls="--")
        ax2.set_title("Liquid subsample: where the edge went", fontsize=11.5)
        ax2.set_xlabel("Settlement date (out-of-sample window)")
        ax2.set_ylabel("Cumulative PnL per contract")
        ax2.grid(alpha=0.25, lw=0.6)
        ax2.legend(loc="lower left", fontsize=8.5, framealpha=0.9)
    else:
        ax2.axis("off")

    fig.suptitle(
        "Fade-the-mispricing backtest — out-of-sample equity curve\n"
        "bins selected on the training window only; entry crosses the spread "
        "(1 − yes_bid) plus {:.0f}¢ slippage, Kalshi taker fee deducted".format(
            slippage_cents),
        fontsize=12.5)
    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_backtest(df: pd.DataFrame, config: dict, out_dir: str = "outputs") -> dict:
    """Backtest the full sample and the liquid subsample, and report both.

    Both are run for the same reason the calibration reports both: the illiquid
    markets are the ones the naive signal most wants to trade, and they are also
    the ones that cannot actually be traded. Showing only the liquid result would
    hide that the strategy's apparent edge lives where execution does not exist;
    showing only the full result would blame the strategy for order books rather
    than for its own logic.

    Note for the README: the liquid subsample is defined by `max_spread`, which
    was chosen after seeing the step-6 calibration. That disclosure travels with
    every number computed on it, this one included.
    """
    liquid, _ = split_by_liquidity(df, config["max_spread"])
    results = {
        "full sample": backtest(df, config),
        "liquid subsample": backtest(liquid, config),
    }

    plot_equity_curve(results, "{}/equity_curve.png".format(out_dir),
                      config["slippage_cents"])

    out = {}
    for label, res in results.items():
        res = dict(res)
        res.pop("_trades", None)
        out[label.replace(" ", "_")] = res
    # headline mirrors, liquid subsample: the only window where the entry price
    # the backtest assumes is one a real order could plausibly have got
    liq = out["liquid_subsample"]
    out["headline"] = {
        "sample": "liquid subsample (spread <= {})".format(config["max_spread"]),
        "n_trades": liq["n_trades"],
        "sharpe_per_trade": liq.get("sharpe_per_trade"),
        "max_drawdown": liq.get("max_drawdown"),
        "mean_pnl_per_contract": liq.get("mean_pnl_per_contract"),
        "hit_rate": liq.get("hit_rate"),
        "statistically_meaningful": liq.get("statistically_meaningful"),
    }
    return out
