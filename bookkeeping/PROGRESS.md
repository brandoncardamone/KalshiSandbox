# Build Progress

The 10-step plan, start to finish. Updated at the end of every step.

**Project:** Prediction Market Calibration & Backtesting Engine
**Repo:** https://github.com/brandoncardamone/KalshiSandbox
**Started:** 2026-08-23
**Specs:** `IMPLEMENTATION_SPEC.md` and `PROJECT_OVERVIEW.md` (currently in `../Kalshi backtester/`)

Legend: ✅ done · 🔨 in progress · ⬜ not started · ⚠️ done with caveats

---

## ▶ Resume here — last updated 2026-08-23, end of Step 8

**Steps 0–8 complete. Next is Step 9 (`run.py --analyze` + `outputs/results.json`).**

State on disk:

| | |
|---|---|
| `kalshi.db` | **28 MB** — 2,715 markets, **1,983 priced**, 141,073 candle rows. Ingest does **not** need re-running |
| `outputs/` | `calibration.png`, `calibration_by_category.png`, `equity_curve.png` |
| Git | Steps 1–7 committed. **Step 8 is staged, not committed** |
| Suggested commit | `Step 8 of plan: Backtest with costs, slippage, Sharpe and drawdown` |
| Credentials | Working. `.env` at repo root, key outside all repos in `../Kalshi backtester/key/` |

`run.py --analyze` is **still not wired up** — that is Step 9, and it is the last
piece of real work. Until then the analysis functions are called directly from
Python. `results.json` does not exist yet; Step 10's README must quote only from
it, so Step 9 blocks Step 10.

### The five results that matter

**1. Headline calibration** (full sample, n=1,983): Brier **0.1558** vs baseline
0.1937, log loss **0.4634** vs 0.5759, skill **+0.196**, base rate 0.2627.

**2. Liquidity is the dominant story.** 322 of 1,983 markets (16.2%) are empty
books quoted around 0.045 / 0.906, mean spread **0.861**:

| Sample | n | Brier | Skill |
|---|---|---|---|
| Full | 1,983 | 0.1558 | +0.196 |
| Liquid (spread ≤ 0.20) | 1,661 | 0.1416 | **+0.313** |
| Illiquid (> 0.20) | 322 | 0.2289 | **−1.150** |

**7 of 12 series have zero illiquid markets**; `KXARGNACBSPREAD` alone supplies
254 of the 322.

**3. Longshot bias was NOT found**, in aggregate or in any category. All eight
tested deltas have |z| < 1.6. See [`DECISIONS.md` D16, D18].

**4. Calibration varies by category** — skill from **−0.031** (Sports) to
**+0.562** (Economics). Sports is negative only because of the illiquid
`KXARGNACBSPREAD` block; on liquid markets it is +0.224. See [D17].

**5. The backtest loses money, and the reason is that there was nothing to
harvest.** Liquid subsample: 169 out-of-sample trades, Sharpe/trade **−0.074**,
max drawdown **−11.37** per contract, mean **−0.0325**/contract. The gross edge
*before any costs* is +0.0086 with **t = +0.26** — indistinguishable from zero.
The full sample's huge apparent gross edge (+0.199, t = +9.03) is the empty-book
artifact and is erased almost exactly by the spread cost of −0.2199. See [D20,
D21, D22].

### Open question for Step 10, not yet decided

Whether the README headlines the **full sample** or the **liquid subsample**.
Recommendation on file: lead with the full sample and present the liquidity split
as the finding. Brandon has not ruled.

### Cautions carried forward

1. The `max_spread` filter was chosen **after** seeing results. Legitimate only
   because the justification is outcome-independent, both samples are reported,
   and it is a declared CONFIG value. All three must survive into the README.
2. Weather is 45% of the sample and supplies **479 of the 721** low-probability
   observations. No aggregate low-probability claim is really a claim about
   "Kalshi" — it is mostly a claim about three cities' temperature markets.
3. The backtest result is negative and **must not be retuned**. `overprice_threshold`
   stays at 0.03. Anyone revisiting this: changing it after seeing the test result
   is the exact failure the split exists to prevent.
4. The sample covers a single ~2-month window (2026-06-17 → 2026-08-23) and 12
   series. It does not generalize to "Kalshi" and the README must not say it does.
5. `apply_slippage` clamps at 0.99, which made the model *less* punitive than
   intended on the worst empty-book trades. Disclosed in the Step 8 section.

---

## Status at a glance

| # | Step | Status | Backs which resume claim |
|---|---|---|---|
| 0 | Pre-work: read specs, plan, verify credentials | ✅ | — |
| 1 | Repo scaffold & secrets hygiene | ✅ | — |
| 2 | `client.py` + connectivity smoke test | ✅ | "asynchronous data pipeline" |
| 3 | SQLite schema & persistence | ✅ | "queryable SQLite store", "price series" |
| 4 | Series & market discovery ⟶ **checkpoint** | ✅ | "200+ resolved markets" |
| 5 | Price-series fetch + full ingest run | ✅ | "price series", "200+ resolved markets" |
| 6 | Calibration core | ✅ | "Brier score and log loss", "longshot bias" |
| 7 | Per-category breakdown | ✅ | "across event categories" |
| 8 | Backtest: costs, slippage, drawdown | ✅ | "costs and slippage", "Sharpe and drawdown" |
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

## Step 5 — Price-series fetch + full ingest ✅
*2026-08-23*

**Verdict: works. All four acceptance gates pass, including the halt gate —
emphatically. 1,983 usable markets and 141,073 candle rows in 1m53s.**

### Built

| Function | Does |
|---|---|
| `parse_candle()` | Raw candle → `{ts, yes_bid, yes_ask, price, volume}`, reading `close` from each nested OHLC object via `_num()` |
| `extract_horizon()` | Picks the last candle **at or before** `settle_ts − 24h`; returns the observation or a skip reason |
| `fetch_price_series()` | One candlestick call per market; returns all candles **plus** the observation |
| `run_ingest()` | Orchestrates discovery → fetch → SQLite, in committed chunks of 250 |
| `verify_ingest()` | The four acceptance gates |

`run.py --ingest` is now wired and prints the summary and gates.

**"At or before" is deliberate.** Candles are hourly and markets settle at
arbitrary times, so one rarely lands exactly on the 24-hour mark. Taking the last
candle *before* the target keeps every observation at least a full 24 hours out —
never accidentally closer to settlement, which would flatter the forecast.

**The full candle series is stored even when no observation can be derived.**
It's what makes the "price series" claim accurate, and it means a later horizon
sweep costs no additional API calls.

### Results

```
discovered      : 2715
priced          : 1983   (73.0%)
skipped         :  732
    quote_out_of_range   617
    none_at_horizon      115
candle rows     : 141073   (52.0 per market)
settle_ts source: {'settlement_ts': 2715}    <- close_time fallback never fired
tiers           : {'live': 2568, 'historical': 147}
http            : 3279 requests, 541 rate-limited, all recovered
```

**Attrition matched the Step 4 prediction closely**, which is the best available
evidence that the extraction logic is doing what the probe measured:

| Category | Predicted usable | Actual kept | Priced n |
|---|---|---|---|
| Sports | 81% | **87.7%** | 813 |
| Climate and Weather | 76% | **73.1%** | 895 |
| Politics | 60% | **83.0%** | 83 |
| Economics | 41% | **41.4%** | 192 |

All four categories clear `min_category_n` = 40, so criterion 10's requirement of
≥3 qualifying categories is already satisfied going into Step 7.

### The gates

| Criterion | Result |
|---|---|
| **2** usable markets | **1,983** vs a floor of 200 ✅ |
| **3** HALT GATE — direction | mean `p_horizon` **0.5210** for YES (n=521) vs **0.2548** for NO (n=1,462); difference **+0.2662**, **z = 21.0** ✅ |
| **4** probability range | 0 out of range; min 0.015, max 0.985 ✅ |
| **9** price series stored | 141,073 candles vs 2,715 markets = **52.0/market** ✅ |

Criterion 3 is the one that mattered. It asks only whether prices point in the
right direction at all — the weakest claim that still proves prices and outcomes
are correctly parsed and correctly paired. A z of 21 is not a marginal pass; it
means the pipeline is sound and the analysis is worth running.

### Two observations worth carrying forward

**The bid-ask spread at the horizon averages 16.1 cents.** That is very wide, and
it is a real finding about liquidity 24 hours out. It also sets expectations for
Step 8: a strategy that must cross a 16-cent spread and then pay fees needs a
very large edge to survive. This is the strongest early signal that the backtest
may come back negative — which the spec anticipates and which would be reported
as-is.

**The raw distribution already hints at the answer**, though nothing is claimed
until Step 6 computes it properly:

```
p_horizon    n     realized
0.0-0.1    497      0.032
0.1-0.2    238      0.134
0.2-0.3    261      0.303
0.3-0.4    222      0.333
0.4-0.5    282      0.238     <- realized well below predicted
0.5-0.6    259      0.297     <- realized well below predicted
0.6-0.7     63      0.524
0.7-0.8     37      0.730
0.8-0.9     41      0.854
0.9-1.0     83      0.976
```

The mid-range bins look substantially overpriced on the YES side. **A caution to
carry into interpretation:** much of the sample is mutually exclusive buckets
(one day's temperature split ~6 ways), where exactly one of the group resolves
YES by construction. Combined with a 16-cent spread, some of this may be
structural rather than a tradeable inefficiency. Step 7's per-category breakdown
is what separates those explanations.

### Note

`min` candles per market is **1** — a few markets have almost no price history.
They are stored, and they are excluded from the analysis automatically because a
single candle cannot satisfy the 24-hour horizon.

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

## Step 6 — Calibration core ✅
*2026-08-23*

**Verdict: works, 14/14 unit checks pass — and it surfaced a data-quality problem
that changes what the headline result means.**

### Built

`analyze.py`: `load_frame()`, `brier()`, `log_loss()`, `baseline_scores()`,
`calibration_table()`, `longshot_summary()`, `plot_calibration()`,
`run_calibration()`, plus `split_by_liquidity()` (added mid-step, see below).

Verified against known values before touching real data: perfect forecast → Brier
0, always-50% → 0.25, worst possible → 1.0; log loss of always-50% → ln 2, and
confident-but-wrong → 4.61 while Brier gives it 0.98, confirming log loss
punishes confident error far harder. Clipping prevents infinities. **End-to-end
check:** 40,000 synthetic perfectly-calibrated forecasts trace the diagonal with
max |delta| = 0.0128.

### Headline results, full sample (n = 1,983)

| Metric | Value | Baseline (always predict base rate) |
|---|---|---|
| Brier | **0.1558** | 0.1937 |
| Log loss | **0.4634** | 0.5759 |
| Brier skill score | **+0.196** | 0 by construction |
| Base rate (YES) | 0.2627 | |

### 🔴 The mid-range anomaly, and what it actually was

The first run showed a large deviation **in the middle of the curve, not the
tails** — the opposite of the expected longshot bias:

```
0.4-0.5   n=282  pred 0.465  realized 0.238   delta -0.2275
0.5-0.6   n=261  pred 0.526  realized 0.299   delta -0.2266
```

That is a big claim if taken at face value: *the market massively overprices
coin-flip events.* It is also wrong.

Checking the spread inside those bins:

```
0.4-0.5   mean spread 0.464   (bid 0.233  ask 0.697)
0.5-0.6   mean spread 0.499   (bid 0.276  ask 0.774)
```

Those are not wide markets. They are **empty books**. Across the whole sample,
322 markets (16.2%) have a mean spread of **0.861**, quoted around
**0.045 / 0.906** — two token orders sitting near the extremes with nothing in
between. Their midpoint lands near 0.5 arithmetically while carrying no
information whatsoever, which is precisely why they flooded the middle bins.

The spread distribution is starkly bimodal, so this is a real gap in the data
rather than a continuum sliced at a convenient point:

```
spread <= 0.05  : 1461
0.05 - 0.10     :  167
0.10 - 0.20     :   33
> 0.20          :  322   <- mean spread 0.861
```

**The ingest's existing rejection rules could not catch this.** They reject a bid
of 0 or an ask of 1; a quote of 0.045 / 0.906 passes every one of them.

### Results split by liquidity

| Sample | n | Brier | Baseline | Skill | Log loss | Mean spread |
|---|---|---|---|---|---|---|
| Full | 1,983 | 0.1558 | 0.1937 | +0.196 | 0.4634 | 0.161 |
| **Liquid (spread ≤ 0.20)** | **1,661** | **0.1416** | 0.2060 | **+0.313** | **0.4273** | **0.026** |
| Illiquid (> 0.20) | 322 | 0.2289 | 0.1064 | **−1.150** | 0.6495 | 0.861 |

The illiquid subsample scores a **negative** skill score — its prices are
materially *worse* than simply guessing the base rate, which is what one should
expect from a midpoint computed over an empty book.

On the liquid subsample the anomaly largely disappears and the curve tracks the
diagonal:

```
0.0-0.1  n=497  pred 0.0434  real 0.0322  -0.0112
0.1-0.2  n=224  pred 0.1455  real 0.1295  -0.0160
0.2-0.3  n=260  pred 0.2495  real 0.3038  +0.0543
0.3-0.4  n=200  pred 0.3392  real 0.3550  +0.0158
0.4-0.5  n=144  pred 0.4496  real 0.4167  -0.0329
0.5-0.6  n=127  pred 0.5469  real 0.4961  -0.0508
0.6-0.7  n= 59  pred 0.6395  real 0.4915  -0.1480
0.7-0.8  n= 31  pred 0.7505  real 0.7742  +0.0237
0.8-0.9  n= 37  pred 0.8359  real 0.8378  +0.0019
0.9-1.0  n= 82  pred 0.9494  real 0.9756  +0.0262
```

### Longshot bias: not found

This is a negative result and it is reported as one.

| Region | n | mean predicted | realized | delta |
|---|---|---|---|---|
| Low, p ≤ 0.3 (liquid) | 721 | 0.0751 | 0.0624 | **−0.0127** |
| High, p ≥ 0.7 (liquid) | 150 | 0.8803 | 0.9000 | **+0.0197** |

The signs are in the direction longshot bias predicts — unlikely things slightly
overpriced, likely things slightly underpriced — but the magnitude is around one
percentage point. That is far too small to trade through a spread, and small
enough that it should not be described as a meaningful finding.

**The genuine finding is the liquidity effect, which is roughly twenty times
larger than the longshot effect.** Where a real two-sided market exists, Kalshi
is well calibrated. Where it does not, the midpoint is not a probability.

### Output

`outputs/calibration.png` — reliability diagram plotting **both** samples over the
shared diagonal, with error bars and per-point n annotations. Showing both is the
point: the gap between the red and blue lines is the finding, and plotting either
one alone would misrepresent it in one direction or the other.

`brier()`, `log_loss()` (clipped to 1e-6), `calibration_table()` with 10
equal-width bins returning `mean_pred / realized / n / se`, and
`plot_calibration()` → `outputs/calibration.png` with the diagonal, error bars,
and per-point `n=` annotations at 150 dpi.

`longshot_summary()` computes `delta = realized − mean_pred`, restricted to bins
with `n ≥ 20` for any interpretive claim. Both scores reported against the
base-rate baseline so the numbers are interpretable.

---

## Step 7 — Per-category breakdown ✅
*2026-08-23*

Runs the whole Step 6 question again separately inside each event category, to
find out whether the single aggregate curve was a fair summary or was hiding
categories that behave nothing like each other.

### Built

`calibration_by_category(df, config)` in `analyze.py`, plus two supporting
pieces:

- `_cat_entry()` — scores one category on **both** samples (all its markets, and
  its liquid subsample), keeping n, the liquid share, the series behind it, its
  date range, and a per-category longshot summary.
- `plot_category_calibration()` — a 2×2 grid of reliability diagrams,
  `outputs/calibration_by_category.png`. Every panel shares identical axes on
  purpose: the panels exist to be compared, and rescaling each to its own data
  would make a category that only ever trades between 0.1 and 0.3 look like it
  spans the whole range.

Two changes were made to existing Step 6 code:

1. The reliability-curve drawing was lifted out of `plot_calibration()` into a
   module-level `_draw_reliability()`, so both charts share one code path
   instead of drifting apart. **Verified no Step 6 number moved** — all ten
   headline figures re-checked against the values recorded in this file.
2. `longshot_summary()` now also reports `se_null`, `z`, and
   `significant_5pct`. The standard error is taken **under the null hypothesis**
   — that outcomes arrived at exactly the rate the market priced — so it is
   computed from `mean_pred`, not from `realized`. This matters: the Economics
   high-probability bins are 50 markets priced at 0.9536 that **all** resolved
   YES, and a `realized`-based standard error is exactly zero there, which
   reported a z of **10,375**. Under the correct null it is **1.56**, which is
   not significant. That is the number that would have gone into the README.

### The comparison — full sample, sorted by Brier

All four categories clear `min_category_n = 40`, so **nothing was marked
"insufficient sample"** and nothing was dropped. Criterion 10 needs ≥ 3
qualifying; there are **4**.

| Category | n | series | base rate | Brier | baseline | **skill** | log loss |
|---|---|---|---|---|---|---|---|
| Politics | 83 | 2 | 0.1446 | **0.0959** | 0.1237 | +0.224 | 0.3051 |
| Economics | 192 | 4 | 0.5260 | **0.1091** | 0.2493 | **+0.562** | 0.3434 |
| Climate and Weather | 895 | 3 | 0.2268 | **0.1362** | 0.1754 | +0.223 | 0.4059 |
| Sports | 813 | 3 | 0.2522 | **0.1944** | 0.1886 | **−0.031** | 0.5711 |

**The aggregate was not a fair summary.** Skill score ranges from **−0.031 to
+0.562** across categories — a spread of 0.593, three times the aggregate value
of +0.196. Reporting only the headline number would have been the misleading
choice.

Note the Brier column and the skill column **disagree on the ranking**. Politics
has the best raw Brier (0.0959) but only middling skill, because its base rate is
0.1446 — a forecaster who blindly said "14.5%" every time would already score
0.1237. Economics has a worse raw Brier and by far the best skill, because its
base rate is 0.5260 and guessing is genuinely hard there. This is why the
baseline column is not optional.

### 🔴 Sports scores *worse than guessing* — and why

Sports skill is **−0.031**: the market's own prices are less accurate than
ignoring them and always saying "25.2%". That is the kind of result that should
be checked before it is believed. It survives checking, and the cause is
specific.

Splitting each category by liquidity:

| Category | liquid n | Brier | skill | illiquid n | Brier | skill |
|---|---|---|---|---|---|---|
| Politics | 70 (84%) | 0.0712 | +0.419 | 13 | 0.2292 | −0.761 |
| Economics | 137 (71%) | 0.0711 | **+0.714** | 55 | 0.2039 | +0.184 |
| Climate and Weather | 895 (**100%**) | 0.1362 | +0.223 | **0** | — | — |
| Sports | 559 (69%) | 0.1763 | +0.224 | 254 | 0.2342 | **−5.193** |

On liquid markets only, Sports is **+0.224** — right in line with Weather. The
entire negative result is the 254 illiquid markets, and those are not scattered:

**All 254 come from a single series, `KXARGNACBSPREAD`** (Argentine football
spreads), 254 of its 356 markets. Their average quote is **bid 0.016 / ask
0.913** — a midpoint of 0.465 on markets that resolve YES **3.9%** of the time.
Nobody was quoting these; the midpoint is an arithmetic artifact of two lonely
orders, and treating it as a probability is what produces a skill score of −5.2.

Illiquidity by series, to show how concentrated it is:

| Series | n | illiquid | share |
|---|---|---|---|
| `KXARGNACBSPREAD` | 356 | 254 | **71.3%** |
| `KXUE` | 102 | 43 | 42.2% |
| `KXAPRPOTUSD` | 51 | 13 | 25.5% |
| `KXFEDTWEETS` | 42 | 10 | 23.8% |
| `KXAAAGASM` | 11 | 2 | 18.2% |
| the other **7 series** | 1,421 | **0** | 0% |

Seven of twelve series have no illiquid markets at all. This retroactively
strengthens the Step 6 liquidity split ([`DECISIONS.md` D15]): it is not a
gradual quality gradient across the exchange, it is a handful of specific,
nameable series with no order book.

### Longshot bias, per category: still not found

`delta = realized − mean_pred`, with the z-score under the null that outcomes
matched the priced rate. Liquid subsample:

| Category | side | n | delta | z | significant at 5%? |
|---|---|---|---|---|---|
| Politics | p ≤ 0.3 | 46 | −0.0154 | −0.55 | no |
| Economics | p ≤ 0.3 | 31 | −0.0198 | −0.50 | no |
| Economics | p ≥ 0.7 | 50 | +0.0464 | +1.56 | no |
| Climate and Weather | p ≤ 0.3 | 479 | −0.0136 | −1.22 | no |
| Sports | p ≤ 0.3 | 137 | −0.0025 | −0.09 | no |
| Sports | p ≥ 0.7 | 50 | −0.0124 | −0.28 | no |
| **aggregate** | p ≤ 0.3 | 721 | −0.0127 | −1.29 | no |
| **aggregate** | p ≥ 0.7 | 150 | +0.0197 | +0.74 | no |

**Not one delta reaches significance in any category, on either sample.** Every
|z| is below 1.6.

The one thing worth saying: the low-probability delta is **negative in all four
categories** on the liquid subsample, which is the direction longshot bias
predicts. Four out of four agreeing in sign is mildly suggestive. But the
magnitudes are all ~1–2 percentage points and each is individually inside the
noise, so this is reported as *directionally consistent, statistically absent* —
not as a finding. It reinforces [`DECISIONS.md` D16] rather than overturning it.

### Weather: the structural caution, checked

The caution carried in from Step 6 was that Weather (895 markets, 45% of the
sample) is ~6 mutually exclusive buckets per day with exactly one resolving YES,
so its low-probability concentration is structural rather than evidence of
anything. Confirmed: Weather's base rate is **0.2268**, close to the 1/6 ≈ 0.167
the structure implies, and 479 of its markets sit in the p ≤ 0.3 bins.

The important consequence: Weather contributes **479 of the 721** markets in the
aggregate low-probability bins. Any aggregate longshot claim would have been
mostly a claim about three cities' temperature markets wearing a general label.
Splitting by category is what makes that visible, which is precisely what this
step existed to do.

### Output

`outputs/calibration_by_category.png` — 2×2 grid, 150 dpi. Each panel plots the
category's full sample (red) and liquid subsample (blue) over the diagonal, with
binomial error bars; bins under n = 20 are drawn hollow and faded rather than
omitted, so a thinly sampled tail reads as thin rather than as absent. Panel
titles carry Brier, the base-rate baseline, and the liquid share. Any category
below `min_category_n` would additionally get a red panel border and a "not
interpreted" flag in its title — none did here.

The Sports panel is the one to look at: the red points at 0.45–0.55 sit far below
the diagonal while the blue points track it closely. That gap is the empty books,
drawn.

---

## Step 8 — Backtest ✅
*2026-08-23*

Trades the mispricing the calibration work found, pays realistic costs for it,
and reports what is left. Backs the third resume bullet in full.

### Built

In `analyze.py`:

| Function | What it does |
|---|---|
| `taker_fee(price, contracts)` | `ceil(0.07 × contracts × p × (1−p) × 100)/100`. Rounds **up**, so the cost model never flatters itself |
| `apply_slippage(quoted, cents)` | Adds 1¢ adverse to an already spread-crossed price, clamped to 0.99 |
| `max_drawdown(equity)` | Largest peak-to-trough fall of the cumulative PnL curve, in dollars per contract |
| `max_drawdown_fraction(equity)` | The spec's ratio form, guarded — see D20 |
| `select_overpriced_bins(train, config)` | The signal. Takes `train` as its **only** data argument so it cannot see test |
| `backtest(df, config)` | Split, select, trade, score |
| `run_backtest(df, config)` | Runs the full sample and the liquid subsample, emits `outputs/equity_curve.png` |

`overprice_threshold: 0.03` was added to CONFIG — the spec hard-coded it, and a
declared value that can be audited is better than a magic number buried in a
function. It was fixed at the spec's value **before** the test window was
touched and has never been changed since.

### The strategy

Split the sample by time at the 0.6 quantile of `settle_ts`. On the **training
window only**, find bins where outcomes arrived materially less often than the
price implied (`realized < mean_pred − 0.03`, `n ≥ 20`). Then, on the **test
window only**, buy one NO contract in every market priced into one of those bins.

Entry is deliberately pessimistic, and it is where most backtests cheat:

- **Cross the spread.** A NO contract costs `1 − yes_bid`, not `1 − yes_ask` and
  certainly not `1 − mid`. You pay what someone will actually deal at.
- **Then take slippage.** A further 1¢ adverse, for latency and for the effect of
  the order on a thin book.
- **Then pay the fee**, rounded up to the next cent.

### Lookahead audit

The first thing a knowledgeable reader attacks. Five checks, all passing on both
samples:

| # | Check | Result |
|---|---|---|
| 1 | Every trade settles strictly after the split timestamp | ✅ |
| 2 | Train and test share no ticker | ✅ |
| 3 | Train + test accounts for the whole sample | ✅ |
| 4 | Bin selection reproducible from the train slice alone | ✅ |
| 5 | **Bin selection unchanged when every test outcome is randomly scrambled** | ✅ |

Check 5 is the decisive one. If the signal could see the future in any way,
destroying the future would change it. It does not change it — the selected bins
come back byte-identical.

### Results — both negative, reported as they came

| | full sample | liquid subsample |
|---|---|---|
| split date | 2026-08-05 | 2026-08-02 |
| train / test | 1,200 / 783 | 999 / 662 |
| **n_trades** | **368** | **169** |
| hit rate | 0.7908 | 0.6923 |
| break-even hit rate needed | 0.8319 | 0.7248 |
| shortfall | **−4.1 pp** | **−3.2 pp** |
| mean entry price | 0.8189 | 0.7107 |
| mean PnL / contract | **−0.0411** | **−0.0325** |
| t-stat on net PnL | −2.06 (**significant**) | −0.97 (not significant) |
| total PnL | −15.13 | −5.49 |
| **Sharpe per trade** | **−0.108** | **−0.074** |
| **max drawdown** | **−18.37** | **−11.37** |
| statistically meaningful (n ≥ 30) | yes | yes |

Both lose money. That is the honest outcome and it ships as-is — the spec is
explicit that tuning parameters until the number turns positive would reintroduce
exactly the lookahead the train/test split exists to prevent. Nothing was retuned.

Sharpe is **per trade**, never annualized. Drawdown is in **dollars per contract
at unit size**, because position sizing is out of scope and there is no bankroll
to take a percentage of.

### 🔴 Where the edge went — the cost attribution

The strategy wins 69% of its trades and still loses money. That needs explaining
rather than asserting, so every trade is scored twice: once at the midpoint with
no costs (the fantasy version) and once as actually modelled. The three cost
terms reconcile the two exactly.

| dollars per contract | full sample | liquid subsample |
|---|---|---|
| gross PnL at the mid | **+0.1989** | **+0.0086** |
| − spread cost | −0.2199 | −0.0174 |
| − slippage | −0.0072 | −0.0096 |
| − taker fee | −0.0130 | −0.0141 |
| **= net PnL** | **−0.0411** | **−0.0325** |
| t-stat on the *gross* edge | **+9.03 (significant)** | **+0.26 (not significant)** |

**Two completely different stories, and the t-stats are what separate them.**

*Full sample:* a large, statistically overwhelming apparent edge of +0.199 per
contract — and it is **entirely fake**. It is the empty-book artifact from Step 6
in trading form: the midpoint says 0.50, so fading it looks enormously
profitable, but a NO contract on those books costs `1 − 0.016 = 0.984`. The
spread cost of −0.2199 erases the +0.1989 almost exactly, because they are the
same number seen from two sides. Risking $1.00 to win $0.00.

*Liquid subsample:* the gross edge is **+0.0086 with t = +0.26**. That is not a
small edge — it is **no edge at all**, indistinguishable from zero. Costs of 4.1¢
then turn nothing into a loss.

So the finding is not "there was an edge and costs ate it." It is stronger and
less flattering: **at a 24-hour horizon, on liquid markets, there was no
exploitable mispricing to begin with**, and the apparent one in the full sample
was an artifact of markets nobody was quoting. This is consistent with the whole
project — Step 7 found no significant longshot bias in any category, and a
strategy cannot harvest a bias that is not there.

### A note against my own cost model

The 1¢ slippage cost came out to only **−0.0072** on the full sample, below the
1¢ intended, because `apply_slippage` clamps entry at 0.99 and many empty-book
entries were already at 0.984. The clamp made the model *less* punitive on
exactly the trades that most deserved punishment — and those trades still lost
heavily. The conclusion is not sensitive to it, but the clamp is a real softness
in the model and is recorded here rather than left to be discovered.

### Output

`outputs/equity_curve.png` — two panels, 150 dpi.

- **Left:** net cumulative PnL for both samples over the out-of-sample window,
  with break-even drawn. Both curves descend.
- **Right:** the liquid subsample's trades scored at the mid (green) against as
  modelled (blue), with the widening gap shaded. That shaded wedge is the cost of
  trading, and the fact that the green line also hovers around zero is the real
  finding.

### Resume bullet 3, checked clause by clause

| Clause | Backed by | Verdict |
|---|---|---|
| "Backtested a fade-the-mispricing strategy" | `backtest()`, 368 / 169 out-of-sample trades | ✅ |
| "with costs and slippage" | `taker_fee` + spread crossing + `apply_slippage`, attributed separately | ✅ |
| "reporting out-of-sample Sharpe" | `sharpe_per_trade` −0.108 / −0.074, test window only | ✅ |
| "and drawdown" | `max_drawdown` −18.37 / −11.37 per contract | ✅ |

All four clauses stand. Nothing needs striking from bullet 3. The numbers are
negative, which is a result, not a failure to produce one.

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
