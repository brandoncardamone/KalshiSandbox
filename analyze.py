"""Calibration analysis: proper scoring rules, reliability diagram, longshot bias.

The question: when the market said 34%, did it happen about 34% of the time?

Nothing here touches the API. Everything reads from the SQLite store built by
ingest.py, so the analysis is fast, repeatable, and independent of Kalshi being
up.
"""

from __future__ import annotations

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
        if sub.empty:
            return None
        n = int(sub["n"].sum())
        wpred = float((sub["mean_pred"] * sub["n"]).sum() / n)
        wreal = float((sub["realized"] * sub["n"]).sum() / n)
        return {
            "n": n,
            "mean_pred": round(wpred, 4),
            "realized": round(wreal, 4),
            "delta": round(wreal - wpred, 4),
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

    def draw(t, color, label, marker="o", z=3, annotate=True):
        pts = t[t["realized"].notna()]
        big = pts[pts["n"] >= 20]
        small = pts[pts["n"] < 20]
        if not big.empty:
            ax.errorbar(big["mean_pred"], big["realized"], yerr=big["se"],
                        fmt=marker, ms=7, capsize=4, lw=1.4, color=color,
                        label=label, zorder=z)
        if not small.empty:
            ax.errorbar(small["mean_pred"], small["realized"], yerr=small["se"],
                        fmt=marker, ms=7, capsize=4, lw=1.4, color=color,
                        alpha=0.35, mfc="white", zorder=z,
                        label=f"{label} — n<20, not interpreted")
        if annotate:
            for r in pts.itertuples():
                ax.annotate(f"n={int(r.n)}", (r.mean_pred, r.realized),
                            textcoords="offset points", xytext=(7, -12),
                            fontsize=7.5, color=color)

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
