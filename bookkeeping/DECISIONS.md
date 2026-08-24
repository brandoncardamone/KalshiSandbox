# Decisions

Choices made during the build where a different choice was genuinely plausible,
and the reasoning behind each. Recorded so they can be defended later — or
revisited if the reasoning turns out to be wrong.

Format: **the decision**, the alternative rejected, and why.

---

## D1 — Build at the repo root, not in `Kalshi backtester/`
*Step 1*

**Chose:** put the code at `KalshiSandbox/` root, beside the existing
`ExpectedValue/` folder.

**Rejected:** building in `Projects/Kalshi backtester/` where the specs live.

**Why:** that folder had no git repo of its own, and `KalshiSandbox` is the
stated push target. The spec's deliverable tree also puts these files at repo
root. Building elsewhere would have meant either a second repo or copying files
before every commit.

---

## D2 — Parse the private key once, not per request
*Step 1*

**Chose:** load and parse the PEM in `KalshiSigner.__init__`.

**Rejected:** the original approach in `expectedvalue.py`, which called
`load_private_key_from_file()` inside the request function.

**Why:** the original re-read and re-parsed the key from disk on **every** call.
Harmless for a handful of requests; wasteful for the hundreds ingest makes at
concurrency 8. The signing output is byte-for-byte the same — this changes
nothing about the security contract, only how often the file is touched.

---

## D3 — Keep the existing signing scheme untouched
*Step 1*

**Chose:** `str(unix_millis) + METHOD + path_without_query`, RSA-PSS/SHA-256,
base64, three headers — carried over exactly.

**Rejected:** rewriting it against the published API docs.

**Why:** the existing implementation demonstrably works, and the spec explicitly
says to reuse it rather than switch hosts or schemes. Rewriting working auth code
is pure downside risk. The same reasoning fixed the base URL at
`https://external-api.kalshi.com`.

---

## D4 — Use the mid-price as the probability estimate
*Locked by the spec; applies at Step 5*

**Chose:** `p_horizon = (yes_bid + yes_ask) / 2`.

**Rejected:** the ask, or the last trade price.

**Why:** using the **ask** folds the bid–ask spread into the measured
probability, so the market would look systematically overconfident when really we
were measuring trading costs. Using the **last trade** goes stale in thin markets
— it might be hours old, while the bid and ask reflect current belief.

The spread isn't ignored, it's just kept out of the *measurement*: the backtest
reintroduces it as an execution cost, which is where it actually belongs.

---

## D5 — Fix the observation at 24 hours before settlement
*Locked by the spec; applies at Step 5*

**Chose:** one observation per market, 24 hours before settlement.

**Rejected:** reading the price at close, or sweeping several horizons.

**Why:** contract prices converge mechanically toward 0 or 1 as settlement
approaches, so a price read at close is trivially accurate and measures nothing.
Backing off 24 hours makes it a real forecast. The horizon is a free parameter and
is stated explicitly alongside every result rather than buried.

A multi-horizon sweep is out of scope for this build — but because the full
candle series is stored, it becomes possible later **without re-ingesting**.

---

## D6 — Equal-width bins, not quantile bins
*Locked by the spec; applies at Step 6*

**Chose:** 10 bins of equal width across [0, 1], with `n` annotated on the plot.

**Rejected:** quantile bins (equal count per bin).

**Why:** quantile bins would hide the sparsity in the tails — and the tails are
exactly where longshot bias lives. Equal-width bins with visible sample counts
make the uncertainty legible instead of averaging it away. Bins below `n = 20` are
plotted but excluded from any interpretive claim.

---

## D7 — Store the full candle series, not just the horizon snapshot
*Locked by the spec; applies at Steps 3 and 5*

**Chose:** persist every hourly candle for the final 7 days of each market.

**Rejected:** storing only the single horizon observation.

**Why:** the research question only needs one price per market, so this is
strictly more data than the analysis requires. It is kept for two reasons: it
makes the resume's "price series" claim literally true (acceptance criterion 9
checks for it), and it makes a future horizon sweep possible without touching the
API again.

---

## D8 — Select the trading signal on training data only
*Locked by the spec; applies at Step 8*

**Chose:** sort by settlement time, split at 60%, identify overpriced bins using
only the earlier window, trade only the later one.

**Rejected:** identifying mispriced bins on the full dataset.

**Why:** this is the single thing a knowledgeable reader will check first. Using
the full dataset to pick which bins to trade means the strategy already knows
which bins turned out to be profitable — the result would be meaningless and the
project indefensible in an interview.

Corollary, also locked: **if the backtest loses money after costs, that ships as
the result.** Tuning the threshold until it turns positive would reintroduce
exactly the bias the split exists to prevent, just by a slower route.

---

## D9 — Remove the accidental `Projects\.git` repo
*Interlude, between Steps 1 and 2*

**Chose:** delete it, after verifying nothing unique was inside.

**Rejected:** adding a `.gitignore` to it instead.

**Why:** the private key sat inside its working tree and it had no `.gitignore`
at all, so one `git add -A` would have published the key. Adding a `.gitignore`
would have left the key one careless `-f` away; removing the repo means the key
is in no version control at all.

Safe because the repo tracked only a stray gitlink, its one real file was a
byte-identical duplicate of a file already pushed elsewhere, and `git fsck` found
nothing dangling. See [`QUESTIONS.md` Q2](QUESTIONS.md#q2--projects-isnt-supposed-to-be-a-git-repo-can-i-un-git-it-by-deleting-the-git-folder-inside-it) for the full check.

---

## D10 — Verify API response shapes before writing any parser
*Step 2*

**Chose:** print raw JSON for the cutoff, one market, and one candlestick first.

**Rejected:** parsing against the shapes given in the spec's examples.

**Why:** the two most likely bugs in this project produce **no error message**.
Treating decimal-dollar strings as cents silently collapses every calibration
point into the corner; asking for a field name that drifted (`close` vs
`close_dollars`) silently discards markets as "no usable quote." Both would only
surface as a plot that looks vaguely wrong at the very end.

Already justified once: the cutoff came back as an ISO-8601 string where a Unix
integer was equally plausible.

**Vindicated immediately.** The probes found that the `_dollars` suffix is not
confined to one endpoint as the spec suggested — the live and historical tiers
disagree field-for-field on the same object (`close_dollars` vs `close`,
`volume_fp` vs `volume`). Parsing against the spec's example would have silently
discarded every historical-tier candle as "no usable quote."

---

## D11 — Pin `Accept-Encoding` to gzip
*Step 2*

**Chose:** send `Accept-Encoding: gzip, deflate` on every request.

**Rejected:** letting httpx negotiate compression normally, or catching and
retrying the failure.

**Why:** Kalshi serves large responses with **brotli**, and the `brotlicffi`
decoder installed in this environment throws `"decoder process called with data
when can_accept_more_data() is False"` partway through the stream. It killed
`GET /series` (~630 KB) outright. Dropping brotli from the accepted encodings
makes the server send gzip, which decodes cleanly.

Retrying would not have helped — the failure is deterministic, not transient.
The bandwidth cost of gzip over brotli is irrelevant at this volume.

---

## D12 — Build on the live tier; the historical tier cannot supply price series
*Step 2*

**Chose:** source markets and candlesticks from the **live** endpoints
(`/markets`, `/series/{s}/markets/{t}/candlesticks`) and not use the historical
tier for ingest.

**Rejected:** the spec's §3.3 routing, which sends markets settled before the
cutoff to `/historical/markets/{t}/candlesticks`.

**Why:** the historical candlestick endpoint returns **zero candles** for real
markets, under every combination tried — 7 d at hourly, 7 d from close instead of
settlement, 30 d at daily, 1-minute (which 400s on range length). A market with
68,937 volume returns an empty array with a `200` status. The endpoint serves
market *metadata* fine; it just has no price history behind it.

Since the stored price series is the point of the `candles` table — and the
resume claim it backs — historical-tier markets are unusable regardless of how
many there are.

**What makes this safe:** the live `/markets` endpoint turns out to reach back
about two months, *past* the cutoff, and its candlestick endpoint works for those
older markets too. KXHIGHNY returns 402 settled markets spanning 2026-06-17 to
2026-08-22, of which 36 settled before the 2026-06-23 cutoff — and a pre-cutoff
market still returned 39 candles.

So the spec's warning ("querying `/markets` for older settled markets returns
empty results with a 200 status") does not reproduce within this window. The
cutoff is still fetched and recorded, but as **provenance** rather than routing:
each market is tagged `live` or `historical` by whether it settled before the
cutoff, so the README can state exactly how much of the sample sits either side.

**The cost, which goes in the README as a limitation:** the sample covers roughly
two months (mid-June to late-August 2026) rather than an arbitrary historical
depth. That is a real constraint on generalization — one calendar window, one
seasonal regime — and it is stated rather than hidden. It does not threaten the
sample size: KXHIGHNY alone supplies 402 markets against a target of 250.

---

## D13 — Choose series by horizon viability, not by market count
*Step 4*

**Chose:** 12 series across 4 categories, selected on a measured sample of how
many of their markets actually yield a usable quote 24 hours before settlement.

**Rejected:** selecting the largest series by settled-market count.

**Why:** the two largest categories are worthless for this project, and the raw
counts hide it completely. Crypto offers 828,993 settled markets and Financials
133,039 — between them, 99% of everything available. But `KXBTCD`,
`KXNASDAQ100U`, `KXBTC15M` and the rest are hourly and 15-minute contracts with
observed lifetimes of 0–23 hours. **They do not exist 24 hours before they
settle.** Sampling 25 markets from each of three Financials series produced
**0 usable observations, 75 of 75 failing `none_at_horizon`.**

Selecting on count would have meant an ingest of hundreds of thousands of markets
running for hours and yielding nothing. The viability probe that caught it took
25 seconds.

**The corollary that shaped the final list:** variation *within* a category
exceeds variation *between* categories. Economics runs from `KXAAAGASD` at 12%
usable to `KXFEDTWEETS` at 76%. So series are picked individually; no category is
taken wholesale.

---

## D14 — Pin a balanced sample rather than the largest one
*Step 4*

**Chose:** 3 weather cities rather than all 6, giving ~2,703 discovered markets
with weather at roughly 46% of the total.

**Rejected:** the maximum sample (~3,927 discovered), where weather would be
~64%.

**Why:** with weather at nearly two-thirds, the headline calibration number would
mostly be a statement about daily temperature markets while being *presented* as
a statement about the exchange. The per-category breakdown would still expose
that, but the aggregate would be quietly misleading — and the aggregate is what
gets quoted.

Balance costs sample size, but ~2,000 expected usable observations is eight times
the `target_markets` of 250, so precision was never the binding constraint here.

**Also rejected: capping every category evenly (~814 usable).** More honest still
for the aggregate, but it throws away most of the sample and thins out the tail
bins, which is exactly where longshot bias is measured and where noise is already
the problem.

**Timing matters as much as the choice.** The list was written into `CONFIG`
**before any prices were fetched**. Choosing series, seeing the calibration
result, then revising the series would be selecting on the outcome — the same
error as tuning the backtest threshold against the test set, and just as fatal to
the result's credibility.

---

## D15 — Split the sample by liquidity, and report both halves
*Step 6*

**Chose:** compute and report calibration on the full sample **and** on the
subsample with a bid-ask spread at or below 0.20, and plot both on the same
reliability diagram.

**Rejected:** (a) reporting only the full sample, (b) silently filtering out the
illiquid markets and reporting the better number.

**Why:** 322 of 1,983 priced markets (16.2%) are quoted around 0.045 / 0.906 --
an average spread of 0.861. That is not a wide market, it is an empty book with
two token orders near the extremes. Its midpoint lands near 0.5 arithmetically
while carrying no information at all, and because it lands near 0.5, all of those
markets pile into the middle bins.

The visible consequence was a mid-range delta of about -0.23 in bins 0.4-0.6,
which read as "the market massively overprices coin-flip events." That claim
would have been wrong, and it is exactly the sort of thing an interviewer would
probe.

The ingest's rejection rules could not have caught it: they reject a bid of 0 or
an ask of 1, and 0.045 / 0.906 passes all of them.

**Why 0.20 is defensible.** The spread distribution is starkly bimodal -- 1,461
markets at or below 0.05, 167 more below 0.10, 33 between 0.10 and 0.20, then a
separate cluster of 322 averaging 0.861. The threshold sits in a genuine gap, and
anything from roughly 0.15 to 0.25 gives the same split.

**The honesty requirement, stated plainly.** This filter was chosen **after**
seeing the results, which is ordinarily how a result gets fitted to a hypothesis.
Three things keep it legitimate, and all three must survive into the README:

1. The justification is a priori and independent of the outcome -- a spread of
   86 cents contains no probability information regardless of what it would do
   to the numbers.
2. **Both** sets of numbers are computed, stored in results.json, and plotted.
   Nothing is hidden, and a reader can disagree with the cut and still see the
   full-sample result.
3. The threshold is a declared CONFIG value with its reasoning recorded, not a
   quiet inline condition.

The distinction from illegitimate filtering: this removes observations that carry
no information, not observations that disagree with a preferred conclusion. The
liquid subsample is not the more flattering one in every respect either -- it has
a *higher* baseline Brier, so beating the baseline is a harder test there.

---

## D16 — Report the absence of longshot bias as the finding
*Step 6*

**Chose:** report that longshot bias was **not** found at any meaningful
magnitude, and lead the analysis with the liquidity effect instead.

**Rejected:** framing the ~1 percentage point tail deltas as evidence of longshot
bias because the signs happen to point the expected way.

**Why:** in the liquid subsample, low-probability markets (p <= 0.3, n=721) came
in at 0.0624 realized against 0.0751 predicted -- a delta of -0.0127. High
probability markets (p >= 0.7, n=150) ran +0.0197. Both point the direction the
longshot literature predicts, and both are about one percentage point.

At that magnitude it is not tradeable through a two-cent spread, let alone a
sixteen-cent one, and calling it a finding would be reading signal into noise.
The project overview anticipated exactly this: "a negative result is publishable,"
and the calibration measurement is the deliverable regardless of which way it
comes out.

What replaced it is a larger and better-evidenced effect: liquidity, where the
gap between the liquid and illiquid subsamples is roughly twenty times the size
of the tail deltas.


---

## D17 — Report Sports' negative skill score rather than quietly excluding the series

**Step 7.** Sports came back with a Brier skill score of **−0.031**: on the full
sample, the market's own prices are worse than ignoring them and always guessing
the 25.2% base rate. That is an embarrassing-looking number sitting in a project
whose headline is "markets are well calibrated."

The cause is specific and was traced before anything was written down. All 254
illiquid Sports markets come from **one series**, `KXARGNACBSPREAD`, quoted on
average bid 0.016 / ask 0.913 on markets that resolve YES 3.9% of the time. On
Sports' liquid markets the skill score is **+0.224**, in line with Weather.

**The option not taken:** drop `KXARGNACBSPREAD` from the sample. It has a real
justification — 71% of its markets have no order book — and the aggregate numbers
would all improve.

**Why not:** the series was pinned in Step 4 *before any prices were fetched*,
precisely so the sample could not be selected on the result. Removing it now,
after seeing that it hurts, is exactly the move that discipline exists to
prevent, and no post-hoc justification changes the order the decisions happened
in. It also throws away the most interesting thing in the data.

**What is done instead:** the negative number is reported as the headline for
Sports, immediately next to the liquid split that explains it, and next to the
series-level table showing 7 of 12 series have zero illiquid markets. The
explanation is falsifiable and a reader can check it. A quietly smaller sample
would not have been.

---

## D18 — Compute the longshot z-score under the null, not from the realized rate

**Step 7.** `longshot_summary()` originally reported a delta with no measure of
whether it could be noise. Adding one exposed a trap.

The obvious standard error is `sqrt(realized(1−realized)/n)`. It divides by zero
whenever every market in a group resolved the same way — which is common in the
tails and happened here: the Economics high-probability bins are **50 markets
priced at 0.9536 that all settled YES**. That formula reported **z = 10,375**,
i.e. "overwhelmingly significant," for a delta of 4.6 percentage points on 50
observations.

The correct standard error comes from the null hypothesis being tested —
"outcomes arrived at the rate the market priced" — so it uses `mean_pred`:
`sqrt(0.9536 × 0.0464 / 50) = 0.0298`, giving **z = 1.56**, not significant.

**Why this is recorded as a decision and not a bug fix:** the wrong version
produces a spectacular, quotable, completely false number, and it produces it
*silently* — there is no crash, no warning, just a very large z. It would have
gone into the README as the project's flagship finding. Every scoring group now
reports `se_null`, `z`, and `significant_5pct` together, so a delta can never
appear without its uncertainty attached.

---

## D19 — Refactor the Step 6 plot rather than duplicating the drawing code

**Step 7.** The category chart needed the same reliability curve the Step 6 chart
draws. Two options: copy the twelve lines, or lift them into a shared
`_draw_reliability()` and change working, already-committed code.

Copying is safer in the moment and worse afterwards — the two charts would drift,
and a repo meant to be read by someone deciding whether to interview is a bad
place for near-duplicate plotting logic.

The refactor was taken, with a guard: all ten Step 6 headline figures were
re-computed afterwards and checked against the values recorded in `PROGRESS.md`
(n, Brier, log loss, baseline, skill, and the same five for the liquid and
illiquid subsamples). **All ten unchanged.** The rule being followed is that
touching committed analysis code is fine as long as the old numbers are
reproduced and the check is written down — not that committed code is untouchable.


---

## D20 — Report drawdown in dollars per contract, not as the spec's ratio

**Step 8.** Spec section 5.4 defines `max_drawdown(equity)` as
`min(equity / peak - 1)`. That is the correct formula for a NAV curve that starts
at some positive value. This project's equity curve is **cumulative profit and
starts at exactly 0**, and on such a curve the formula divides by zero on the
first trade and inverts its sign for every stretch where cumulative PnL is
negative.

It is not a theoretical problem. Run as written it returned **−459.25** for the
full sample — a curve whose running peak was **4 cents** before it fell $18. The
ratio is arithmetically correct and completely meaningless.

**Decision:** `max_drawdown()` returns the largest peak-to-trough decline in the
curve's own units, dollars per contract at unit size, with the running peak
starting at 0 so a curve that only ever loses is measured from where it began.
Measured: **−18.37** (full), **−11.37** (liquid).

The spec's form is kept as `max_drawdown_fraction()`, evaluated only where the
running peak is strictly positive, and every result carries a
`max_drawdown_fraction_reliable` flag which is **False** for both samples here.
Nothing is hidden; the unusable number is still emitted, labelled unusable.

**Why deviate rather than invent a bankroll:** turning drawdown into a percentage
requires a starting capital, and position sizing is explicitly out of scope. Any
denominator would be a number made up to make a percentage possible.

---

## D21 — Ship the negative backtest without retuning anything

**Step 8.** Both samples lose money: −0.0411 per contract on the full sample
(t = −2.06, significantly negative), −0.0325 on the liquid subsample.

Every knob within reach would have improved it — loosen `overprice_threshold`
below 0.03, move the train/test split, drop the 1¢ slippage, restrict to the
bins that happened to work. Each has a plausible-sounding justification available
after the fact.

**None were touched.** The spec is explicit, and the reasoning is not merely
procedural: the entire value of the train/test split is that the parameters were
fixed before the test window was seen. Adjusting one *after* seeing the
out-of-sample result silently converts the test set into a training set, and
every number in the step becomes a fitted number wearing an out-of-sample label.
That is undetectable by a reader and would be the single most dishonest thing
this project could do.

`overprice_threshold` stays at 0.03, its spec value, and this is written into the
cautions in `PROGRESS.md` for anyone who revisits the file later.

---

## D22 — t-test the gross edge before calling it an edge

**Step 8.** The liquid subsample's gross PnL at the midpoint — before any costs —
is **+0.0086 per contract**. Written down on its own that reads as a real if
modest edge that transaction costs happened to exceed, which is a flattering and
very common way to describe a losing backtest: *the signal worked, the market
was too expensive to trade.*

Its t-statistic is **+0.26**. On 169 trades with a standard deviation of 0.43,
+0.0086 is indistinguishable from zero. There was no edge to be eaten.

Every PnL mean in the backtest now carries a t-statistic and a
`significant_5pct` flag beside it, gross and net, on both samples. This exposed
the mirror-image case too: the full sample's gross edge of +0.1989 is
**significant at t = +9.03** and is nonetheless entirely fake — it is the
empty-book artifact, cancelled almost exactly by a spread cost of −0.2199.

**The rule this encodes:** significance and reality are different questions, and
a mean without a standard error can be made to tell either story. Both are
reported for every figure, so neither the flattering reading nor the dramatic one
can be told without the number that contradicts it sitting next to it.

