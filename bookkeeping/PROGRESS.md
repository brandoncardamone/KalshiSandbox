# Build Progress

The 10-step plan, start to finish. Updated at the end of every step.

**Project:** Prediction Market Calibration & Backtesting Engine
**Repo:** https://github.com/brandoncardamone/KalshiSandbox
**Started:** 2026-08-23
**Specs:** `IMPLEMENTATION_SPEC.md` and `PROJECT_OVERVIEW.md` (currently in `../Kalshi backtester/`)

Legend: ✅ done · 🔨 in progress · ⬜ not started · ⚠️ done with caveats

---

## Status at a glance

| # | Step | Status | Backs which resume claim |
|---|---|---|---|
| 0 | Pre-work: read specs, plan, verify credentials | ✅ | — |
| 1 | Repo scaffold & secrets hygiene | ✅ | — |
| 2 | `client.py` + connectivity smoke test | ✅ | "asynchronous data pipeline" |
| 3 | SQLite schema & persistence | ✅ | "queryable SQLite store", "price series" |
| 4 | Series & market discovery ⟶ **checkpoint** | ✅ | "200+ resolved markets" |
| 5 | Price-series fetch + full ingest run | ⬜ | "price series", "200+ resolved markets" |
| 6 | Calibration core | ⬜ | "Brier score and log loss", "longshot bias" |
| 7 | Per-category breakdown | ⬜ | "across event categories" |
| 8 | Backtest: costs, slippage, drawdown | ⬜ | "costs and slippage", "Sharpe and drawdown" |
| 9 | `run.py` CLI + `results.json` | ⬜ | — (makes everything reproducible) |
| 10 | README + resume reconciliation + push | ⬜ | verifies **all** claims |

---

## The resume claims being defended

Every step above exists to make one of these literally true. Step 10 checks each
one against what was actually built, and any clause that isn't backed gets struck
from the resume rather than left standing.

> **Prediction Market Calibration & Backtesting Engine** | Python, Pandas, NumPy, SQLite
>
> - Built an **asynchronous** data pipeline pulling historical **price and settlement data** from the Kalshi API (**RSA-PSS authenticated**) across **200+ resolved markets**, normalizing outcomes and **price series** into a **queryable SQLite store**
> - Measured market **calibration** by bucketing market-implied probabilities against realized outcomes, computing **Brier score and log loss**, and quantifying systematic mispricing (e.g., **longshot bias**) **across event categories**
> - Backtested a **fade-the-mispricing** strategy with **costs and slippage**, reporting **out-of-sample Sharpe and drawdown**

---

## Step 0 — Pre-work ✅
*2026-08-23*

Read both specs, wrote the 10-step plan, confirmed the target repo, located the
existing RSA-PSS signing code in `ExpectedValue/expectedvalue.py`.

**Verified:** Python 3.13.11 present; all six dependencies (`httpx`, `pandas`,
`numpy`, `matplotlib`, `python-dotenv`, `cryptography`) already installed, so no
virtualenv was needed.

---

## Step 1 — Repo scaffold & secrets hygiene ✅
*2026-08-23*

### Built

| File | Purpose |
|---|---|
| `auth.py` | RSA-PSS signing, carried over from `expectedvalue.py` |
| `run.py` | The spec's `CONFIG` block verbatim + `--ingest/--analyze/--all` CLI skeleton |
| `.gitignore` | `.env`, `*.pem`, `*.key`, `first key.txt`, `kalshi.db`, `__pycache__/` |
| `.env.example` | Placeholder values only |
| `requirements.txt` | The six dependencies |
| `outputs/` | Empty; will hold the PNGs and `results.json` |

### Decisions

- **Built at the repo root**, not in `../Kalshi backtester/`. That folder has no
  git repo of its own, and the spec's deliverable tree puts these files at
  `KalshiSandbox/` root. `ExpectedValue/` is untouched beside them.
- **Signing contract kept identical** to the working code: `str(unix_millis) +
  METHOD + path_without_query`, RSA-PSS/SHA-256, base64, same three headers.
  Base URL stays `https://external-api.kalshi.com` per spec §3.1.
- **One structural change:** the private key is now parsed **once** at
  construction instead of re-read from disk on every request. The original called
  `load_private_key_from_file()` inside `my_get_function()`; fine for a handful of
  calls, wasteful for the hundreds ingest will make at concurrency 8. Same output.
- **Dropped the module-level API call.** The original ran a live request on
  import; `auth.py` is now import-safe.

### Found

1. **Stale key path.** `KALSHI_API_KEY_PATH` pointed at a location the key had
   been moved out of during the `ExpectedValue/` migration. First signer
   construction failed with `FileNotFoundError`. Fixed in the root `.env`.
   ⚠️ **`ExpectedValue/.env` still has the stale path, so `expectedvalue.py` is
   currently broken for the same reason.** One-line fix, not yet applied.
2. **Private key was inside a git repo.** Resolved during the Step 1–2 cleanup
   below.

### Verified

- Signer constructs, loads the 2048-bit key, emits three headers, 344-char
  base64 signature, 13-digit millisecond timestamp
- `git check-ignore` blocks `.env`, `*.pem`, `first key.txt`, `kalshi.db`
- `git add --dry-run` stages exactly five files, zero secrets
- No secret has **ever** been committed to this repo (checked full history)

---

## Interlude — credentials and repo cleanup ✅
*2026-08-23, between Steps 1 and 2*

Not a numbered step, but it closed a real security hole.

### New API key

A fresh key was issued and `.env` updated. Confirmed working against every
endpoint family the project needs:

| Request | Status |
|---|---|
| `GET /historical/cutoff` | **200** |
| `GET /markets?status=settled` | **200** |
| `GET /historical/markets` | **200** |
| `GET /series?category=Economics` | **200** |

So the key is not narrowly scoped — it reads market and historical data fine.

### First real API finding

```json
{"market_settled_ts": "2026-06-23T00:00:00Z", ...}
```

The cutoff is an **ISO-8601 string, not a Unix integer** — exactly the timestamp
variance spec §3.5 warns about. Practically: markets settled before
**2026-06-23** are historical-tier only; later ones are live-tier. About two
months of live data against a much deeper historical archive.

### Repo cleanup

The private key had been placed in `Projects\Kalshi backtester\key\`, which was
outside `KalshiSandbox` but **inside** a different git repo — `Projects\` itself
was an accidental repo pointed at `github.com/brandoncardamone/random-fun-stuff`
with **no `.gitignore` at all**. A `git add -A` there would have published the
key.

Investigated before deleting anything:

- `Projects\.git` tracked exactly **one** entry: a gitlink (mode `160000`) to
  `random-fun-stuff`, with no `.gitmodules` — the signature of `git init` run one
  directory too high
- Its 3 local commits touched only `rainbowcursor.py`, which the last commit had
  already deleted
- That file's blob hash `11c2c96e…` is **identical** to the copy tracked in
  `random-fun-stuff/rainbowcursor/rainbowcursor.py`, so nothing was unique
- `git fsck` found **no** dangling or unreachable objects; no stashes
- The reflog showed this repo *used to be* the real `random-fun-stuff` before a
  reset, but everything it held was pushed and is now carried by the inner repo

**Outcome:** `Projects\.git` removed. `random-fun-stuff` and `KalshiSandbox`
verified healthy afterwards. The private key now sits in **no git repo at all**
and cannot be staged by anything.

---

## Step 2 — `client.py` + connectivity smoke test ✅
*2026-08-23*

### Built

`client.py` — `KalshiClient`, an async context manager owning four concerns and
no business logic:

- `get()` — signed request, `asyncio.Semaphore(8)` cap, exponential backoff with
  jitter (0.5 s base, 5 attempts, honours `Retry-After`) on **429 and 5xx only**;
  any other 4xx raises `KalshiAPIError` immediately. Re-signs on every attempt,
  since the signature covers a timestamp and a stale one would be rejected.
- `paginate()` — the cursor loop as an async generator, with a `max_items` stop
  and a repeated-cursor guard against endpoints that echo the final cursor
  forever.
- `stats` — counts requests, retries and rate-limits, so the README can state
  honestly how much retrying the real run needed.

Five throwaway probe scripts were written to the scratchpad and **not
committed**.

### Found — the seven things the probes turned up

**1. Prices are decimal-dollar strings. Confirmed on real data.**
A candle reports `"0.3300"`, meaning 33%. Already a probability. Dividing by 100
would have silently collapsed every calibration point into the corner.

**2. The `_dollars` suffix depends on the tier — worse than the spec warned.**
The spec said the suffix appears on "notably the batch candlestick endpoint." In
reality the two tiers disagree field-for-field on the *same* object:

| | live tier | historical tier |
|---|---|---|
| close price | `close_dollars` | `close` |
| mean price | `mean_dollars` | `mean` |
| volume | `volume_fp` | `volume` |
| open interest | `open_interest_fp` | `open_interest` |

Market objects use `_dollars` throughout (`yes_bid_dollars`, `yes_ask_dollars`,
`last_price_dollars`). The tolerant `_num()` accessor is mandatory, not optional.

**3. `settlement_ts` exists as an explicit field.** So the spec's `close_time`
fallback is not needed. It is ISO-8601 with microseconds
(`"2026-06-23T23:56:41.145222Z"`), and it differs from `close_time` by seconds to
minutes. `results.json` will record that the explicit field was used.

**4. There is no `series_ticker` field on market objects.** The live candlestick
endpoint needs one in its path. It has to be derived from the ticker prefix
(`KXHIGHNY-26AUG21-B77.5` → `KXHIGHNY`) or carried down from discovery. Carrying
it from discovery is what Step 4 does anyway, since category needs the same
treatment.

**5. `GET /markets` unfiltered is useless.** All 200 markets in the default feed
were `KXMVECROSSCATEGORY` — auto-generated multivariate parlay markets that
settle every 15 minutes and drown out everything else. They have no candlestick
history at all. Discovery **must** filter by `series_ticker`.

**6. 🔴 The historical tier serves metadata but NOT candlesticks.**
Every combination tried on real, liquid, non-parlay markets returned **zero**
candles — 7 d/60 m from settlement, 7 d/60 m from close, 30 d/1440 m, and
1-minute (which 400s on range length). A market with 68,937 volume returns an
empty array with a `200` status.

**7. …but the live tier reaches back about two months, and its candlesticks
work throughout — including for markets that settled before the cutoff.**

```
KXHIGHNY settled markets via /markets : 402
range                                 : 2026-06-17 .. 2026-08-22
settled BEFORE the 2026-06-23 cutoff  : 36
candles for a pre-cutoff market       : 39   <- works fine
```

Finding 6 + finding 7 together decide the data strategy — see
[`DECISIONS.md` D12](DECISIONS.md#d12--build-on-the-live-tier-the-historical-tier-cannot-supply-price-series).

### Also learned

- `GET /series` returns **13,386 series in one unpaginated response**, and
  `category` **is** present on the series object — 18 categories, led by Sports
  (3,481), Entertainment (2,510), Politics (2,221), with Economics (730) and
  Climate and Weather (354) both comfortably large enough.
- Series objects also carry `fee_multiplier` and `fee_type` (`"quadratic"`),
  which means the spec's assumed 0.07 taker multiplier can be **checked per
  series** in Step 8 rather than merely disclosed as an assumption.
- Candle counts per market vary by series: KXHIGHNY markets live ~40 hours and
  yield 37–40 hourly candles; KXCPIYOY yields 96–143. Both comfortably span the
  24 h horizon, but short-lived markets are where horizon attrition will come
  from.
- Not every candle has a usable quote. The last candle of a settled market
  routinely shows `yes_bid` close `0.0000` and `yes_ask` close `1.0000` — an
  empty book, maximum spread. These must be rejected, which is exactly what the
  spec's bid/ask validity checks do.

### Verified

| Check | Result |
|---|---|
| Pagination across pages | 402 KXHIGHNY markets retrieved via cursor, no duplicates, clean stop |
| Non-retryable errors raise | `400` on a bad candlestick range raised `KalshiAPIError` immediately, no retries |
| Semaphore cap holds | Measured **at the transport layer**: peak 8 simultaneous requests against a cap of 8 |
| Async actually helps | 24 markets: 0.93 s sequential → 0.21 s concurrent, **4.3× speedup**, identical results |
| Throughput | 40 markets' candlesticks (1,507 candles) in **0.29 s** |
| Retries needed so far | 0 retries, 0 rate-limits across ~150 requests |

### Fixed

**A brotli decoding bug.** `GET /series` (~630 KB) is served brotli-compressed,
and the installed `brotlicffi` decoder throws `"called with data when
can_accept_more_data() is False"` partway through the stream, killing the
request. `client.py` now pins `Accept-Encoding: gzip, deflate`. gzip decodes
cleanly and the bandwidth difference is irrelevant at this scale.

### Correction to an earlier note

The first async-vs-sequential benchmark reported a peak of 24 simultaneous
requests, seemingly breaching the cap of 8. That was an error in the *test*: it
incremented its counter before `get()` acquired the semaphore. Re-measured by
wrapping the HTTP transport itself, the peak is exactly 8. The client was correct
throughout.

---

## Step 3 — SQLite schema & persistence ✅
*2026-08-23*

**Verdict: works. 27/27 checks passed, nothing blocked.**

### Built

The storage half of `ingest.py`. Both tables from spec §4 verbatim, plus the
parsing primitives everything downstream depends on:

| Function | Does |
|---|---|
| `connect()` | Opens the db with `row_factory` set, so rows are addressed by column name rather than position |
| `init_db()` | Creates tables and indexes if absent; safe to re-run |
| `_num()` | Tolerant numeric accessor — tries `close`, `close_dollars`, `close_fp` |
| `to_unix()` | Normalizes Unix ints and ISO-8601 strings (with or without microseconds) to Unix seconds |
| `upsert_market()` | `INSERT OR REPLACE` one market row |
| `upsert_candles()` | Bulk `INSERT OR REPLACE` a market's candles; skips rows with no timestamp |
| `db_summary()` | Counts for the ingest summary and acceptance criteria |

**Why two tables:** one market has ~40–140 candles. Flattening that into one
table would repeat each market's title, category, and result across every candle
row — wasteful, and it lets a market disagree with itself. `markets` holds facts
true once per market; `candles` holds facts true once per hour; they join on
`ticker`.

The `candles` table is the **only** thing backing "price series" on the resume.
One price per market is a snapshot, not a series. Criterion 9 checks
`COUNT(*) FROM candles` ≫ `COUNT(*) FROM markets`.

### Design notes

**`_num()` also accepts the `_fp` suffix**, beyond the spec's `_dollars`. Step 2
found quantity fields use it (`volume_fp`, `open_interest_fp`) where the
historical tier uses bare `volume`. Same drift, different suffix.

It also swallows unparseable values rather than raising. A junk price returns
`None`, which the Step 5 validity checks then reject as "no usable quote" and
**tally by reason** — so bad data is counted, not silently dropped or crashed on.

**The `CHECK (result IN ('yes','no'))` constraint is doing real work.** It is the
database refusing to store a mis-parsed outcome. Verified rejecting `'maybe'`,
`'YES'` (wrong case), `''`, and `'1'`. A CSV would accept all four and the
mistake would only surface as a strange-looking chart at the very end. This is
the same principle as Step 2's smoke test: fail at the moment of the error, not
three steps downstream.

**Settlement-timestamp provenance is tracked as counts, not a column.** Step 2
showed `settlement_ts` is present on real markets, so the spec's `close_time`
fallback should never fire. Rather than add a column outside the spec's schema,
the ingest summary counts how many markets used each source, and `results.json`
reports both — which satisfies §3.5's "record which was used" without a schema
deviation.

### Found

**`idx_candles` is redundant.** SQLite automatically creates
`sqlite_autoindex_candles_1` for the `PRIMARY KEY (ticker, ts)`, which covers the
same columns in the same order. The spec asks for the explicit index, so it was
kept, but it earns nothing:

```
all indexes on candles:
   sqlite_autoindex_candles_1   <- implicit, from the PK
   idx_candles                  <- explicit, from the spec

query plan: SEARCH candles USING INDEX idx_candles (ticker=?)
```

The planner picks one and the other sits unused. Harmless, worth knowing.

### Verified

27 checks, all passing:

| Group | Checks |
|---|---|
| Schema | both tables, 3 named indexes, 12 + 6 columns, composite PK is `(ticker, ts)` |
| Re-runnable | `init_db()` three times in a row, no error |
| Idempotency | same market written 3× → **1 row**, last write wins; candles written 2× → 2 rows; `ts=None` skipped |
| Constraints | `result` of `'maybe'`/`'YES'`/`''`/`'1'` all **rejected**; NULL `settle_ts` rejected |
| `_num()` | live `close_dollars` → 0.33, historical `close` → 0.018, `volume_fp` works, missing/None/junk/non-dict → None, **and "0.5600" → 0.56, not divided by 100** |
| `to_unix()` | ISO with microseconds, plain ISO, passthrough int, None/empty/junk → None |
| Queries | category + date filter, and a `markets ⟕ candles` join, both execute |

### Fixed

`.gitignore` had `kalshi.db` and `kalshi.db-journal` listed literally, which
would miss `-wal` and `-shm` if SQLite's journal mode ever changes. Broadened to
`kalshi.db*`; all four variants now confirmed ignored.

---

## Step 4 — Discovery ⟶ checkpoint ✅
*2026-08-23*

**Verdict: works. 12 series pinned, 4 categories, 2,703 markets discovered
against a target of 250.**

### Built

Added to `ingest.py`: `get_cutoff_ts()`, `discover_series()`,
`normalize_market()`, `discover_markets()`. Category and `series_ticker` are both
stamped onto every market from the series that produced it, since the market
object carries neither. Markets whose `result` is not exactly `'yes'` or `'no'`
are dropped at normalization.

### Survey — phase 1 screen, phase 2 exact counts

8,277 requests over 8m50s covering 8 categories. Full results in
`survey_results.json` (scratchpad, not committed).

| Category | Best series | Markets |
|---|---|---|
| Climate and Weather | 6 × `KXHIGH*` cities, 408 each | 2,448 |
| Economics | `KXAAAGASD` 1,201, `KXTSAW` 190, `KXUE` 151 | 1,768 |
| Sports | `KXARGNACBSPREAD` 371, `KXALLSVENSKANTOTAL` 295 | 1,575 |
| Politics | `KXTRUMPENDORSEMENTS` 70, `KXAPRPOTUSD` 54 | 226 |
| Science and Technology | `KXLLM1` 88, `KXTOPMODEL` 84 | 388 |
| Financials | `KXNASDAQ100U` 112,920, `KXDJI` 13,060 | 133,039 |
| Crypto | `KXBTCD` 291,438, `KXBTC` 291,008 | 828,993 |
| Companies | `KXCOMPANYLAYOFF` 2 | 2 — **insufficient** |

### 🔴 Raw counts are deeply misleading — the viability probe

Market count is not sample size. A market that lives 15 minutes has **no price
24 hours before it settles**, so it contributes nothing. Sampling 25 markets per
series and applying step 5's exact acceptance conditions:

| Category | Usable at 24 h | Why the failures |
|---|---|---|
| Sports | **81%** | some markets open <24 h before kickoff |
| Climate and Weather | **76%** | one-sided book at the horizon |
| Politics | 60% | very mixed by series |
| Economics | 41% | very mixed by series |
| Science and Technology | 13% | one-sided book — longshot markets pinned at 0 or 1 |
| Financials | **0%** | markets live 18–23 h; nothing exists at the horizon |

**Crypto and Financials — the two largest categories by an enormous margin — are
worthless here.** `KXBTCD`'s 291,438 markets and `KXNASDAQ100U`'s 112,920 are
hourly and 15-minute contracts. Median observed lifetime 0–23 hours. Every single
sampled market failed with `none_at_horizon`.

Had the series list been chosen on market count alone, the run would have spent
hours fetching hundreds of thousands of markets and produced **zero usable
observations**.

Two distinct failure modes, worth separating:

- **`none_at_horizon`** — the market did not exist 24 h before settling. Purely
  structural: short-dated contracts.
- **`quote_out_of_range`** — a candle exists, but bid or ask sits exactly at 0 or
  1: a one-sided book with no real two-sided quote. Dominates the longshot
  series (`KXLLM1` 25/25, `KXTECHRANKLISTAICODE` 23/25).

Within-category variation is larger than between-category variation, so series
must be picked individually, not by taking a category wholesale. Economics ranges
from `KXAAAGASD` at 12% to `KXFEDTWEETS` at 76%.

### Also learned

**Rate limiting is real and the backoff handles it.** 695 of 8,277 requests
(8.4%) came back `429`; every one succeeded after exponential backoff, with zero
failures. The client's retry policy is not decorative — it is the difference
between the survey completing and dying a third of the way through.

**Weather's base rate is structural.** All six `KXHIGH*` series show a YES rate of
exactly 0.167 — each day offers ~6 mutually exclusive temperature buckets and
exactly one resolves YES. Worth remembering when reading the calibration curve:
the weather sample is inherently concentrated at low probabilities.

### Pinned — the "balanced, 4 categories" option

Chosen for a sample where no single category dominates the aggregate (weather is
~46%, against ~64% if all six cities were taken). Written into
`CONFIG["series_tickers"]` **before any prices were fetched**, so the sample
cannot have been selected on the result.

| Category | Series | Discovered |
|---|---|---|
| Climate and Weather | `KXHIGHNY`, `KXHIGHCHI`, `KXHIGHMIA` | 1,224 |
| Sports | `KXARGNACBSPREAD`, `KXALLSVENSKANTOTAL`, `KXBRASILEIROBGAME` | 915 |
| Economics | `KXTSAW`, `KXUE`, `KXAAAGASM`, `KXFEDTWEETS` | 464 |
| Politics | `KXAPRPOTUSD`, `KXACTBLUETOP` | 100 |
| | **total** | **2,703** |

Expected ~2,000 usable after the measured attrition, against `target_markets`
of 250 and an acceptance floor of 200.

### Verified

| Check | Result |
|---|---|
| All 12 pinned tickers resolve in `/series` | ✅ none missing |
| Distinct categories ≥ 3 | ✅ **4** |
| Every category ≥ `min_category_n` (40) | ✅ lowest is Politics at 100 |
| Total ≥ `target_markets` (250) | ✅ **2,703** |
| Date range | 2026-06-17 .. 2026-08-23 |
| Outcome variation within each series | ✅ YES rates 0.100 – 0.863, so no series is degenerate |

The per-series YES rates span 0.100 to 0.863, which matters: a series where
almost everything resolves the same way contributes little to a calibration
curve. This spread means the sample covers a real range of probabilities rather
than piling up at one end.

`discover_series()` across categories, then `discover_markets()` paging
`/markets?series_ticker=…&status=settled` per chosen series.

**Revised after Step 2.** The original plan paged both `/markets` and
`/historical/markets` and routed on the cutoff. The historical tier is now used
for neither — it cannot supply candlesticks ([D12](DECISIONS.md#d12--build-on-the-live-tier-the-historical-tier-cannot-supply-price-series)).
The cutoff is still fetched, but only to tag each market `live` or `historical`
as provenance.

Two things must be carried down from series discovery onto every market, because
the market object carries **neither**: the **category**, and the
**`series_ticker`** that the candlestick path needs.

Filtering by series is not optional — the unfiltered feed is entirely
auto-generated parlay markets with no price history.

**Stops for review** so `CONFIG["series_tickers"]` can be pinned for
reproducibility — and so we learn *before* ingest whether the chosen series can
actually clear 200+ markets across 3+ categories with 40+ each.

---

## Step 5 — Price-series fetch + full ingest ⬜

One call per market for hourly candles over the final 7 days, via the live
endpoint `/series/{series}/markets/{ticker}/candlesticks`. **Every** candle row
persists. Then the horizon observation: last candle at or before
`settle_ts − 24h`, `p_horizon = (bid + ask) / 2`.

Settlement time comes from the explicit `settlement_ts` field, which Step 2
confirmed exists — the spec's `close_time` fallback is not needed, though which
was used still gets recorded in `results.json`.

Prices are read via a tolerant `_num()` accessor because the field names differ
by tier (`close_dollars` vs `close`), and taken from the `close` of each candle's
nested `yes_bid` / `yes_ask` objects.

Rejects tallied by reason. Expect 20–40% attrition, so over-fetch.

**Four hard gates run here:**

| Criterion | Check |
|---|---|
| 3 (**halt gate**) | mean `p_horizon` for `result='yes'` significantly **above** `result='no'`. If this fails, parsing is broken — stop and fix before any analysis |
| 4 | all `p_horizon` strictly within (0, 1) — anything > 1 is the cents/dollars bug |
| 2 | ≥ 200 usable markets |
| 9 | candle rows ≫ market rows |

---

## Step 6 — Calibration core ⬜

`brier()`, `log_loss()` (clipped to 1e-6), `calibration_table()` with 10
equal-width bins returning `mean_pred / realized / n / se`, and
`plot_calibration()` → `outputs/calibration.png` with the diagonal, error bars,
and per-point `n=` annotations at 150 dpi.

`longshot_summary()` computes `delta = realized − mean_pred`, restricted to bins
with `n ≥ 20` for any interpretive claim. Both scores reported against the
base-rate baseline so the numbers are interpretable.

---

## Step 7 — Per-category breakdown ⬜

For each category with ≥ 40 markets: its own Brier, log loss, N, binned table,
and longshot delta, plus a comparison table sorted by Brier. Categories under
threshold are reported **with their N and marked "insufficient sample"**, never
silently dropped. Emits `outputs/calibration_by_category.png`.

Sole backing for "across event categories" (criterion 10 needs ≥ 3 qualifying).

---

## Step 8 — Backtest ⬜

Sort by `settle_ts`, split at the 0.6 quantile. Identify overpriced bins on
**train only** (`realized < mean_pred − 0.03`, `n ≥ 20`), trade only the held-out
window. That ordering is the entire defence against lookahead bias.

- `apply_slippage()` — NO entry at `1 − yes_bid` (crossing the spread, *not*
  `1 − yes_ask`), then 1¢ further adverse, clamped to 0.99
- `taker_fee()` — `ceil(0.07 × C × P × (1−P))` to the next cent
- `max_drawdown()` on the sequential unit-size equity curve
- `sharpe_per_trade = mean(pnl) / std(pnl)`, stored under exactly that key,
  **never annualized**
- `outputs/equity_curve.png`

If `n_trades < 30`, flagged "not statistically meaningful" but still reported.
**If mean PnL is negative after costs, that ships as the result.** Tuning the
threshold until it turns positive would reintroduce exactly the bias the
train/test split exists to prevent.

---

## Step 9 — CLI + `results.json` ⬜

`--ingest`, `--analyze`, `--all`. `outputs/results.json` records every metric,
all config used, run timestamp, discovered/priced/skipped-with-reasons counts,
the `by_category` block, `slippage_cents`, `sharpe_per_trade`, `max_drawdown`,
and **which field supplied the settlement timestamp** (explicit field vs
`close_time` fallback), so the horizon definition stays honest.

This file becomes the single source of truth the README quotes from.

---

## Step 10 — README, resume reconciliation, push ⬜

README written **last**, quoting only numbers present in `results.json`:
summary → data → method → embedded `calibration.png` → findings in plain English
→ backtest → **mandatory limitations section** → how to run.

Then spec §9's table is walked against what was actually built and verified, and
each resume clause is marked supported or struck. A claim that survives on the
page but not in the repo is worse than no claim.
