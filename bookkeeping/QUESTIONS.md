# Questions Asked During the Build

Every question raised while building, with the answer and why it mattered.
Nothing here is too small to record — the "obvious" questions are usually the
ones worth re-reading later.

Newest at the bottom. Each entry: the question as asked, the short answer, then
the detail.

---

## Q1 — Do you need the new Kalshi key from my account?
*2026-08-23, before Step 2*

**Short answer:** No — not unless the smoke test returns `401`.

The existing key loaded and signed correctly, which proves the file is a valid
2048-bit RSA private key. What that **doesn't** prove is that Kalshi still
accepts it — constructing a signature is a purely local operation. Only a live
request can confirm the key is still active on their side.

Two reasons a fresh key might be wanted anyway:

- **Scope.** The old key was created to read `portfolio/positions`. This project
  reads market and historical data — a smaller surface, so it should work, but a
  narrowly scoped key could have returned `403`.
- **Hygiene.** A dedicated read-only key means this project isn't sharing
  credentials with a trading account. A preference, not a blocker.

**What happened:** a new key was issued anyway, and tested against all four
endpoints the project uses. All returned `200`, so scoping was never an issue.

---

## Q2 — `Projects\` isn't supposed to be a git repo. Can I un-git it by deleting the `.git` folder inside it?
*2026-08-23, before Step 2*

**Short answer:** Yes. It contained nothing unique.

Deleting a `.git` folder destroys that repo's entire history, so this deserved
checking rather than assuming. What the investigation found:

- `Projects\.git` tracked exactly **one** entry — a **gitlink** (file mode
  `160000`) pointing at `random-fun-stuff`, with no `.gitmodules` file. That
  combination is the classic signature of `git init` run one directory too high.
- It had 3 local commits, all touching only `rainbowcursor.py`, and the most
  recent one had already **deleted** that file.
- The file's blob hash `11c2c96e…` was **byte-identical** to the copy tracked in
  `random-fun-stuff/rainbowcursor/rainbowcursor.py`. Identical content always
  produces an identical hash in git, so this is proof, not an estimate.
- `git fsck` reported no dangling or unreachable objects, and there were no
  stashes — so nothing was hiding outside the visible history.
- The reflog revealed this repo *used to be* the real `random-fun-stuff` before
  someone reset it, but everything it ever held had been pushed and is now
  carried by the inner repo, which is further ahead.

**Why it mattered:** the private key had been placed inside that repo's working
tree, and the repo had **no `.gitignore` at all**. A single `git add -A` would
have pushed the key to GitHub. Removing the repo means the key now sits in no
version control at all and cannot be staged by anything.

---

## Q3 — Why did I move it to `.git.disabled-backup` just to delete it?
*2026-08-23, before Step 2*

**Short answer:** You didn't need to. That was over-cautious.

The rename was suggested as a reversible safety net, but the evidence at that
point had already ruled out any loss — identical blob hash, nothing unpushed
that wasn't duplicated elsewhere.

The one thing it did buy: **unreachable objects** hadn't been checked yet. A
forgotten stash, or a commit orphaned by a `git reset`, wouldn't appear in the
normal history listing and would have been destroyed silently. Running
`git fsck --unreachable --dangling` against the backup came back empty, which
closed that gap.

**Lesson recorded:** verify *first*, then delete once. Renaming as insurance is
only worth it when a check is still outstanding.

---

## Q4 — Explain what Step 2 is actually saying; I'm lost in the terminology
*2026-08-23, before Step 2*

**Short answer:** Step 2 builds one object that knows how to talk to Kalshi, plus
a throwaway test that prints raw API responses before any parsing code is
written.

Full definitions of every term live in [`GLOSSARY.md`](GLOSSARY.md) — sections
[2](GLOSSARY.md#2-the-kalshi-api) and [4](GLOSSARY.md#4-async--networking) cover
this step. The short version:

| Term | Plain meaning |
|---|---|
| **async / await** | Many requests in flight at once instead of waiting for each in turn. `await` marks "I'm about to wait — go do something else." Not multiple CPU cores |
| **semaphore** | A bouncer with 8 wristbands. Never more than 8 requests in flight, and the 9th waits at the door |
| **429 vs 5xx vs 4xx** | `429` = slow down, `5xx` = their server broke — both worth retrying. Other `4xx` = *you* are wrong, so retrying just repeats the mistake |
| **exponential backoff** | Wait longer after each failure: 0.5s → 1s → 2s → 4s. A struggling server needs room, not faster hammering |
| **jitter** | A random nudge on each wait, so 8 requests that fail together don't all retry at the same instant |
| **cursor pagination** | The API returns one page plus a bookmark token. Send the token back for the next page, until no token comes back |
| **smoke test** | A quick "does it work at all" check before building on top of it |

**Why the smoke test comes before any parsing** — this was the part worth
understanding. The spec flags two failure modes that produce **no error at all**,
just silently wrong numbers:

1. **Prices are decimal strings.** `"0.5600"` means 56%, already a probability.
   Dividing by 100 out of cents-thinking gives `0.0056`. Nothing crashes, charts
   still render, and every point on the calibration curve quietly collapses into
   the bottom-left corner.
2. **Field names drift between endpoints** — `close` on one, `close_dollars` on
   another. Ask for the wrong key and you get `None`, markets get discarded as
   "no usable quote," and the sample silently shrinks with no error raised.

One instance was already caught without looking for it: the cutoff arrived as
`"2026-06-23T00:00:00Z"`, an ISO date string, where a Unix integer was equally
plausible. Guessing would have been wrong.

---

## Q5 — So was everything with Step 2 okay? That wasn't clear
*2026-08-23, after Step 2*

**Short answer:** Yes. The code works, nothing is blocked.

The confusion came from the step report mixing two very different kinds of
information without separating them:

**1. Did the code work?** Yes, completely. `client.py` signs requests, caps
concurrency at exactly 8, retries the right errors and not the wrong ones, pages
cursors correctly, and runs 4.3× faster than sequential. Every check passed.

**2. What did the probes teach us?** Three of the spec's assumptions turned out
to be wrong against the live API. That is not a failure — **it is the entire
reason Step 2 exists.** The spec was written from documentation; the smoke test
tested it against reality.

Only one of the three actually mattered: the historical endpoints don't return
price history, so ingest uses the live endpoints instead. The real cost is that
the sample covers ~2 months rather than arbitrary historical depth. It goes in
the README as a limitation and doesn't threaten the sample size — one series
alone supplies 402 markets against a target of 250.

**Things that genuinely went wrong, both fixed:** a brotli decoder crash on the
630 KB `/series` response (fixed by pinning gzip), and a miscount in the
benchmark that made the concurrency cap look broken (the test measured before the
semaphore was acquired; the client was correct).

**Process lesson recorded:** step reports should lead with the verdict — *did it
work, is anything blocked* — and put findings and detail underneath. Burying
"everything passed" beneath a list of API surprises reads as though something
failed.

---

## Q6 — How long does the rest of the project take, and when is it best to sleep?
*2026-08-23, after Step 3*

**Short answer:** ~2.5 hours of build time and only minutes of machine time.
There is no long-running process to sleep through.

| Step | Machine time | Build time |
|---|---|---|
| 4 Discovery | ~1–2 min | ~15 min |
| 5 Full ingest | ~1–5 min | ~25 min |
| 6 Calibration | seconds | ~20 min |
| 7 Per-category | seconds | ~15 min |
| 8 Backtest | seconds | ~25 min |
| 9 CLI + results.json | seconds | ~15 min |
| 10 README + reconciliation | — | ~25 min |

Step 5 is the heaviest and still finishes in minutes — Step 2 measured **40
markets' candlesticks in 0.29 s** at concurrency 8, so even 800 markets is under
a minute of requests. That speed *is* the "asynchronous" claim on the resume
doing its job. Everything after it is pandas over a few hundred rows.

**So the bottleneck is the approval gates between steps, not compute.** Waiting
out a process would mean waiting on nothing.

**Nothing is time-sensitive.** The only thing that shifts overnight is that the
live tier is a rolling ~2-month window, so a later ingest gains a day at the
recent end and loses one at the old end. Immaterial, and the exact date range is
recorded in `results.json` regardless.

---

## Q7 — Commit after each step, or one big commit at the end? Which looks better to recruiters?
*2026-08-23, after Step 3*

**Short answer:** commit after each step. Not close.

**Practical reason:** if a later step produces something suspicious, `git diff`
between step commits shows exactly what changed. One giant commit means bisecting
800 lines by hand.

**The recruiter reason is more nuanced than it looks.** A recruiter almost
certainly will not open the commit history. A **hiring engineer** on a technical
screen sometimes will — and a single "initial commit" containing an entire
finished project reads as a code dump. It says nothing about how the work was
done, and invites the obvious question about whether it was generated in one
shot.

A history that runs scaffold → client → schema → discovery → ingest →
calibration → categories → backtest → README shows infrastructure first, then
data, then analysis, then findings. It reads as *built* rather than *produced*.

**Two things that matter more than commit count:**

1. **Don't fake it.** Never write finished code and retroactively slice it into
   invented commits. Real timestamps and real messages are the entire point.
2. **Message quality beats granularity.** Nine meaningful commits beat forty
   saying "fix", "update", "wip".

**Caveat specific to this project:** the README is written last, from real
results, so it necessarily lands in the final commit. That is correct — a README
committed earlier would be quoting numbers that did not yet exist.

**Decision:** commit at the end of each step from Step 4 onward; push at Step 10
after review. Steps 1–3 get three commits reflecting what was genuinely built in
each, since they were in fact built in that sequence.

---

## Q8 — So Step 8 is done?
*2026-08-23, after Step 8*

Yes. Built, verified, and staged — but **not committed**, since Brandon runs the
commits from Step 5 onward.

What "done" covers:

- All six functions built: `taker_fee`, `apply_slippage`, `max_drawdown`,
  `select_overpriced_bins`, `backtest`, `run_backtest`.
- Cost primitives unit-tested against hand-computed values **before** any result
  was trusted — `taker_fee(0.50) = 0.02`, the 0.99 slippage clamp, and the
  drawdown edge cases including a curve that only ever loses.
- Backtest run on both samples: **368** and **169** out-of-sample trades.
- Sharpe per trade (**−0.108** / **−0.074**) and max drawdown (**−18.37** /
  **−11.37** per contract) reported, test window only.
- Lookahead audit passed on both samples, including the scramble test.
- `outputs/equity_curve.png` emitted.
- Resume bullet 3 checked clause by clause — all four clauses backed, nothing to
  strike.

**The one thing to be aware of:** the result is **negative**. Both samples lose
money. That is a finding rather than a failure, and it is not going to be tuned
into a positive number — see [`DECISIONS.md` D21]. If anyone asks about this
project, the backtest losing is the most defensible part of it, because the
reason it loses is measured rather than guessed: the gross edge before costs has
a t-statistic of **+0.26**, meaning there was no exploitable mispricing at a
24-hour horizon to begin with.

**Still outstanding:** Steps 9 (`run.py --analyze` + `results.json`) and 10
(README + resume reconciliation + push). Step 9 blocks Step 10, because the
README may only quote numbers that exist in `results.json`.

