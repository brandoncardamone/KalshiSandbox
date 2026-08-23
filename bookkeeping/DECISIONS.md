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
