# Glossary

Every piece of jargon this project uses, in plain language. Tagged with the step
that introduced it, so you can read only as far as you've built.

Jump to: [Prediction markets](#1-prediction-markets) · [The Kalshi API](#2-the-kalshi-api) · [Authentication](#3-authentication--secrets) · [Async & networking](#4-async--networking) · [Storage](#5-storage-sqlite) · [Statistics](#6-statistics--calibration) · [Backtesting](#7-backtesting) · [Git](#8-git--version-control)

---

## 1. Prediction markets

*Introduced: reading the specs (pre-Step 1)*

**Prediction market** — an exchange where you buy and sell contracts on whether a real-world event will happen. Kalshi is one. The thing being traded is a claim about the future, not a company or a commodity.

**Binary contract** — a contract with exactly two possible endings. It pays **$1 if the event happens** and **$0 if it doesn't**. No middle outcome. Everything in this project is a binary contract.

**YES side / NO side** — the two directions you can bet. Buying YES pays $1 if the event happens. Buying NO pays $1 if it doesn't. They're mirror images: if YES trades at 34¢, NO trades at roughly 66¢, because exactly one of them will pay out.

**Settlement / resolution** — the moment the real-world answer is known and the exchange pays out. After settlement a market's `result` is permanently `"yes"` or `"no"`. This project only uses markets that have already settled, because we need to know what actually happened in order to score the forecast.

**Implied probability** — the central idea of the whole project. Because a contract pays $1, its price *is* the market's probability estimate. A price of 34¢ means the market collectively believes there's a **34% chance**. So a market price can be read directly as a forecast, and any forecast can be graded.

**Bid** — the highest price a buyer is currently willing to pay. If you want to **sell right now**, this is what you get.

**Ask** (or *offer*) — the lowest price a seller is currently willing to accept. If you want to **buy right now**, this is what you pay.

**Spread** — the gap between bid and ask. If the bid is 55¢ and the ask is 57¢, the spread is 2¢. It's a real cost: buy and immediately sell and you lose it. A wide spread means a thin, illiquid market.

**Mid** (or *mid-price*) — the midpoint, `(bid + ask) / 2`. In the 55/57 example, 56¢. **This project uses the mid as its probability estimate**, deliberately. Using the ask would fold the spread into the number and make the market look systematically overconfident, when really we'd just be measuring trading costs.

**Last trade price** — what someone actually paid most recently. Rejected here as a probability estimate: in a thin market the last trade might be hours stale, while the bid and ask reflect what people believe *right now*.

**Longshot bias** — the documented tendency of betting markets to **overprice unlikely outcomes**. People enjoy buying cheap lottery tickets, so things priced at 5% happen less than 5% of the time. This is the specific mispricing the project goes looking for.

**Horizon** — how long before settlement we read the price. Fixed at **24 hours** here. It matters because prices mechanically converge to 0 or 1 as settlement approaches — a price read one minute before the answer is known is trivially accurate and measures nothing. Backing off 24 hours makes the forecast a real forecast.

---

## 2. The Kalshi API

*Introduced: Step 1–2*

**API** (Application Programming Interface) — the machine-readable version of a website. Instead of a page for humans, you ask a URL a question and get back structured data.

**REST / endpoint / path** — the style of API Kalshi uses. Each **endpoint** is a URL that answers one kind of question. The **path** is the part after the hostname, e.g. `/trade-api/v2/markets`.

**Base URL** — the unchanging prefix every request shares. Here: `https://external-api.kalshi.com/trade-api/v2`.

**Query string / parameters** — the `?status=settled&limit=100` part of a URL. Filters and options on a request.

**JSON** — the text format the answers come back in. Nested keys and values; Python parses it into dictionaries and lists.

**Status code** — a number on every response saying how it went. `200` = fine, `401` = authentication rejected, `403` = not allowed, `404` = doesn't exist, `429` = you're going too fast, `5xx` = the server itself broke. The key split: **4xx means the request was wrong, 5xx means the server was**.

**Candlestick** (*candle*) — a summary of trading over one fixed time slice. Each candle here covers **one hour** and reports the bid, ask, and traded price during that hour. The name comes from the chart shape traders draw. This project stores a week of hourly candles per market, which is the "price series" in the resume.

**`period_interval`** — how wide each candle is. Kalshi allows only `1` (minute), `60` (hour), `1440` (day). We use `60`.

**Live tier vs historical tier** — Kalshi splits its data in two. Recently settled markets are served by the normal endpoints; older ones live *only* behind separate `/historical/...` endpoints.

**Cutoff timestamp** — the dividing line between those two tiers, from `GET /historical/cutoff`. **Measured on 2026-08-23 as `2026-06-23T00:00:00Z`.** Markets that settled before that date must be requested from the historical endpoints. This matters enormously because asking the wrong endpoint returns an **empty list with a `200` success code** — it looks like "no markets exist" rather than an error.

**Cursor / pagination** — the API won't return thousands of results at once. It returns a page plus a **cursor**, an opaque bookmark token. Send the cursor back to get the next page; repeat until no cursor comes back. *Opaque* means don't try to read or build one yourself — just echo it.

**Unix timestamp** — a moment in time as a single integer: seconds since 1 Jan 1970 UTC. `1730000000` is a date. Compact and easy to compare, which is why everything gets normalized to it on ingest.

**ISO-8601** — the human-readable timestamp format, `"2026-06-23T00:00:00Z"`. Kalshi mixes both formats depending on the field, so ingest converts everything to Unix seconds.

**Decimal-dollar string** — **the single most dangerous detail in the API.** Prices arrive as text like `"0.5600"`, meaning 56%. They are already a probability between 0 and 1. Dividing by 100 out of a habit of thinking in cents produces `0.0056`, which **raises no error** and silently ruins every result.

**`_dollars` suffix** — field names drift between endpoints: one returns `close`, another returns `close_dollars`. Code reads either via a tolerant accessor rather than assuming one spelling. **Confirmed on real data in Step 2, and worse than the spec suggested** — the live and historical tiers disagree field-for-field on the *same* object:

| | live tier | historical tier |
|---|---|---|
| close price | `close_dollars` | `close` |
| volume | `volume_fp` | `volume` |
| open interest | `open_interest_fp` | `open_interest` |

**`_fp` suffix** — "fixed point." Marks quantity fields (`volume_fp`, `open_interest_fp`, `yes_bid_size_fp`) as opposed to price fields. Also arrives as a string: `"161.56"`.

**OHLC** — open, high, low, close. The four numbers summarising one candle. Inside a Kalshi candle, `yes_bid`, `yes_ask`, and `price` are each a nested object holding these. **This project uses `close`** — the value standing at the end of that hour.

**`event_ticker` / `series_ticker` / `ticker`** — three levels of naming, widest to narrowest. A **series** is a recurring question ("NYC daily high temperature", `KXHIGHNY`). An **event** is one instance of it (a particular day). A **market** is one specific threshold within that event (`KXHIGHNY-26AUG21-B77.5`, "between 77.5 and…"). Note that **market objects carry no `series_ticker` field** — it must be derived from the ticker prefix or carried down from discovery.

**Strike / `floor_strike` / `strike_type`** — the threshold the question turns on. "Will the high exceed 77.5°F" has a strike of 77.5 and a `strike_type` of `greater`.

**Open interest** — how many contracts are currently held open. Distinct from volume, which counts how many changed hands.

**Liquidity** — how easily you can trade without moving the price. Thin markets have wide spreads and stale prices.

**Multivariate / parlay market (`KXMVE…`)** — an auto-generated combination market that pays only if several separate conditions all land ("BTC above X **and** SOL below Y **and** XRP above Z"). Kalshi generates these constantly — they settle every 15 minutes and **dominate the unfiltered market feed**. They carry no candlestick history, so discovery must filter by series rather than taking whatever `/markets` returns by default.

**`fee_multiplier` / `fee_type`** — fields on the series object recording what that series is actually charged (`"quadratic"` is the `0.07 × P × (1−P)` shape). Useful because it lets the taker-fee rate be **verified per series** rather than assumed.

**`status: "finalized"`** — what settled markets actually report, even when requested with `status=settled`. Related but not identical vocabulary; filter on the request, don't assume the response echoes your filter.

---

## 3. Authentication & secrets

*Introduced: Step 1*

**API key** — proof of who you are. Kalshi's has two parts: a **key ID** (public, like a username) and a **private key file** (secret, like a password).

**Public-key cryptography** — a scheme with two matched keys. The private key signs; the public key verifies. Kalshi stores your public key; you keep the private one. Nothing secret ever crosses the network.

**RSA** — the specific algorithm. Ours is a **2048-bit** RSA key (the bit count is the key's size, and roughly its strength).

**PSS** (Probabilistic Signature Scheme) — the padding scheme wrapped around RSA. "Probabilistic" means signing the same text twice gives two different signatures, both valid. That's a security feature, not a bug — so don't be alarmed that signatures never repeat.

**Signature** — a short blob proving *you* sent *this exact request*. Here it's computed over `timestamp + HTTP_METHOD + path`, meaning a captured signature can't be replayed against a different endpoint or reused later.

**PEM** — the text file format the private key is stored in. Recognizable by its `-----BEGIN PRIVATE KEY-----` header. The extension doesn't matter; ours is a `.txt` file containing PEM content.

**Base64** — a way of writing raw binary as plain letters and digits so it can travel in an HTTP header. The 344-character signature is base64.

**Environment variable** — a setting read from outside the code, so secrets never appear in a source file. `KALSHI_API_KEY_ID` and `KALSHI_API_KEY_PATH` here.

**`.env` file / dotenv** — a local file holding those variables, loaded at startup by the `python-dotenv` library. **Never committed.** `.env.example` is its committed twin containing only fake placeholder values, so someone cloning the repo can see what's needed.

---

## 4. Async & networking

*Introduced: Step 2*

**Synchronous** — one thing at a time. Send a request, sit idle for 200 ms waiting, then continue. 300 markets this way is about a minute of doing nothing.

**Asynchronous (`async` / `await`)** — many requests in flight at once. While one waits on the network, Python starts another. `await` marks the points where "I'm about to wait, go do something else." **Not** multiple CPU cores — one worker who starts the next job instead of staring at the wall. This word is load-bearing on the resume, so the pipeline is genuinely async.

**Concurrency** — how many requests are in flight simultaneously. Capped at 8.

**Semaphore** — the thing enforcing that cap. A bouncer with 8 wristbands: take one to make a request, return it when done, request #9 waits at the door. Without it, async would fire all 300 requests at once and get us rate-limited or banned.

**Rate limiting** — the server refusing service when you ask too fast, signalled with status `429`.

**Retry** — trying a failed request again. Only sensible for `429` and `5xx`. Retrying a `401` just sends the same bad signature five more times.

**Backoff** — waiting before the retry instead of firing instantly.

**Exponential backoff** — doubling the wait each time: 0.5s → 1s → 2s → 4s → 8s. A struggling server needs room, not a faster hammering.

**Jitter** — a small random amount added to each wait. Without it, 8 requests that fail together back off by *identical* amounts and retry at the *identical* instant — a synchronized stampede. Jitter smears them apart.

**Wrapper / client** — one object that owns all the above, so the rest of the code just says `await client.get(path)` and gets JSON back. "Thin" means it adds no business logic of its own.

**Smoke test** — a quick check that the basics work before building on them. Named for switching on a circuit and seeing whether smoke comes out. Ours prints raw API responses so parsers are written against reality, not assumption.

**`Retry-After`** — a header a server may send with a `429`, naming how long to wait. When present it beats our own backoff calculation: the server knows better than we do.

**Compression / `Accept-Encoding`** — responses are compressed in transit. The client says which schemes it understands; the server picks one. **gzip** is the universal one; **brotli** is newer and compresses harder.

**Why this project pins gzip** — Kalshi serves large responses with brotli, and the `brotlicffi` decoder installed here crashes partway through the stream (`"called with data when can_accept_more_data() is False"`), killing the 630 KB `/series` request outright. Asking for gzip only sidesteps a library bug that no amount of retrying would fix.

**Async context manager (`async with`)** — the `__aenter__` / `__aexit__` pair that guarantees cleanup on exit, even if an error is raised. Here it closes the HTTP connection pool. Without it, connections leak.

**Connection pool** — reused open connections to the same host, so each request doesn't repay the cost of establishing one. Part of why 40 concurrent requests finish in 0.29 s.

**Transport layer** — the level where bytes actually move, beneath the client's own logic. Worth distinguishing because the semaphore cap can only be honestly measured *there*: an early benchmark counted requests before they acquired the semaphore and wrongly reported 24 in flight against a cap of 8. Measured at the transport, the peak was exactly 8.

---

## 5. Storage (SQLite)

*Introduced: Step 3*

**SQLite** — a full SQL database that lives in a single ordinary file, with no server to install or run. Ideal here: the data is a few hundred thousand rows and needs to be queryable, but nothing needs to be shared over a network.

**Table / row / column** — the spreadsheet analogy. This project has two tables: `markets` (one row per market) and `candles` (one row per hour per market).

**Schema** — the definition of what columns exist and what type each holds.

**Primary key** — the column(s) uniquely identifying a row. `ticker` for markets; the pair `(ticker, ts)` for candles.

**Index** — a lookup structure that makes filtering on a column fast, the way a book index beats reading every page.

**`INSERT OR REPLACE`** — write a row, silently overwriting any existing row with the same primary key. Makes the ingest **idempotent**: interrupt it and re-run, and you get the same result rather than duplicates.

**Idempotent** — running it twice has the same effect as running it once.

**Ticker** — the unique short code naming a market, e.g. `KXHIGHNY-25AUG23-B89`.

**Upsert** — "update or insert." Write a row if it's new, replace it if it already exists. `INSERT OR REPLACE` is SQLite's version.

**CHECK constraint** — a rule the database enforces on every write. Here, `CHECK (result IN ('yes','no'))` means a mis-parsed outcome is **refused**, not stored. Verified rejecting `'maybe'`, `'YES'` (wrong case), `''`, and `'1'`. A CSV would accept all four and the mistake would surface weeks later as a strange chart.

**`NOT NULL`** — a column that must have a value. `settle_ts` and `result` are both NOT NULL, because a market missing either is unusable for calibration and should fail loudly at write time.

**NULL** — "no value here," distinct from zero or empty string. `p_horizon` is deliberately nullable: a market can be stored with its outcome known but no usable quote at the horizon.

**Transaction / commit** — a group of writes that either all take effect or none do. If ingest is interrupted mid-write, the database is never left half-updated. `commit()` is the point at which changes become permanent.

**Composite primary key** — a primary key made of more than one column. `candles` uses `(ticker, ts)`: neither alone is unique, but the pair is — one market, one hour.

**Implicit / auto index** — SQLite silently creates an index for every primary key (`sqlite_autoindex_candles_1`). This makes the spec's explicit `idx_candles ON candles(ticker, ts)` redundant, since it covers the same columns in the same order. Kept for spec compliance; it earns nothing.

**Query plan (`EXPLAIN QUERY PLAN`)** — the database's own account of how it intends to answer a query, and which index it will use. The way to check an index is actually doing something rather than merely existing.

**`row_factory`** — a setting that makes query results addressable by column name (`row["p_horizon"]`) instead of position (`row[7]`). Positional access silently breaks the moment a column is added.

**Join** — combining two tables on a shared column. Here `markets ⟕ candles` on `ticker`, to pull a market's full price history alongside its outcome.

---

## 6. Statistics & calibration

*Introduced: specs; used in Steps 6–7*

**Calibration** — the core question. A forecaster is **well-calibrated** if the things they call 30% likely happen about 30% of the time. Note this is about *honesty*, not *skill*: always saying "50%" about coin flips is perfectly calibrated and completely useless.

**Realized frequency** — what actually happened. Of the markets priced near 30%, the fraction that resolved YES.

**Binning / bucketing** — grouping forecasts into ranges (0–10%, 10–20%, …) so they can be compared as a group. You can't check a single 34% forecast; you can check whether 200 forecasts near 34% came true about 34% of the time.

**Equal-width bins** — bins of identical size (10 bins of 10 percentage points). Chosen over quantile bins because quantile bins would disguise how few observations sit in the extremes — which is exactly where longshot bias lives.

**Reliability diagram** — the main chart. Predicted probability on the x-axis, realized frequency on the y-axis. Perfect calibration traces the **diagonal**. Points below the line = overpriced; above = underpriced.

**Brier score** — `mean((forecast − outcome)²)`. Squared error for probabilities. **Lower is better; 0 is perfect.** Punishes being wrong, and punishes being confidently wrong more.

**Log loss** — `−mean(o·ln p + (1−o)·ln(1−p))`. Same job as Brier but far harsher on confident mistakes, because the logarithm blows up toward infinity near 0 and 1. Saying "1% chance" about something that happens is near-unforgivable here.

**Proper scoring rule** — a scoring rule whose best strategy is reporting your true belief. Brier and log loss are both proper. This is why they're used instead of something like accuracy, which can be gamed.

**Baseline** — a dumb reference score to judge against. Here: always predicting the overall base rate. A Brier score means nothing alone; it means something compared to the baseline.

**Base rate** — how often the event happens overall, ignoring all forecasts.

**Standard error** — the uncertainty on an estimate, drawn as an error bar. With few observations in a bin, its realized frequency is noisy and shouldn't be trusted. Computed as `sqrt(p(1−p)/n)`.

**Sample size (`n`)** — how many observations in a bin. Bins with **n < 20** are plotted but explicitly **excluded from any claim**, because noise there can look exactly like a real effect.

**Delta** — `realized − predicted`. **Negative delta at low probabilities is longshot bias**: things happened less often than priced.

---

## 7. Backtesting

*Introduced: specs; used in Step 8*

**Backtest** — simulating a trading strategy on historical data to see what it would have earned. Easy to do; easy to do dishonestly.

**Lookahead bias** — the cardinal sin. Letting the simulation use information that wasn't available at decision time. It makes any strategy look brilliant and is the first thing a knowledgeable reader checks for.

**Train / test split** — the defence against it. Split the data **by time**: find the pattern using only earlier markets (**train**), then trade only later markets (**test**). Here 60% / 40%.

**Out-of-sample** — results measured on data the strategy never saw while being designed. The only results worth reporting.

**Fade the mispricing** — the strategy: when the market overprices something, bet *against* it. Concretely, buy NO on contracts the training data says are overpriced.

**Crossing the spread** — buying at the ask rather than the mid, i.e. paying the real price rather than the theoretical midpoint. Assuming you trade at the mid is the most common way backtests flatter themselves.

**Slippage** — the gap between the price you assumed and the price you'd really get, from delay and from your own order moving the market. Modelled here as **1¢ adverse, on top of** crossing the spread.

**Taker fee** — what Kalshi charges for an order that executes immediately against an existing one. `ceil(0.07 × contracts × P × (1−P))`, peaking at $0.0175 per contract at a 50¢ price. Deducted from every simulated trade.

**PnL** — profit and loss.

**Hit rate** — the fraction of trades that won.

**Sharpe ratio** — return divided by volatility, i.e. reward per unit of risk. Reported here as **Sharpe per trade** and never annualized, because annualizing needs holding-period and capital assumptions this project doesn't make. Saying "Sharpe" without that qualifier would be overclaiming.

**Equity curve** — cumulative profit plotted over time, in settlement order.

**Drawdown / maximum drawdown** — the worst peak-to-trough fall on that curve. Answers "what's the biggest loss I'd have sat through?" — a question average return completely hides.

**Unit position size** — assuming exactly one contract per trade. Position sizing is out of scope, so drawdown is reported at unit size and said so.

---

## 8. Git & version control

*Introduced: Step 1 (and the repo cleanup)*

**Repository (repo)** — a folder whose entire change history git tracks, stored in a hidden `.git` subfolder.

**Commit** — one saved snapshot, with a message.

**Remote / `origin`** — the copy hosted elsewhere, here on GitHub. `origin` is the conventional name for the main one.

**Push / fetch** — send local commits to the remote / retrieve remote commits.

**Branch** — a named line of development. `main` and `master` are both just default names.

**Blob** — git's word for one stored file's contents. Identified by a hash of the content, so **identical files have identical hashes** — which is how we proved `rainbowcursor.py` in the outer repo was byte-for-byte the same as the copy in `random-fun-stuff` and therefore safe to delete.

**Hash** — a short fingerprint of content, e.g. `11c2c96e`. Same content always gives the same hash; different content essentially never collides.

**`.gitignore`** — a list of files git should pretend not to see. How `.env` and private keys stay out of commits.

**Gitlink / submodule** — a pointer from one repo to *another repo* at a specific commit, stored with file mode `160000`. Usually deliberate; here it was the accidental result of running `git init` one directory too high.

**Reflog** — git's private log of where branches have pointed recently, including states thrown away by a reset. Used to confirm nothing unique was about to be lost.

**Dangling / unreachable objects** — saved content no longer referenced by any branch. Checked with `git fsck` before deleting a repo, since it's the one place orphaned work could hide.

**Working tree** — the actual files on disk, as opposed to the stored history.
