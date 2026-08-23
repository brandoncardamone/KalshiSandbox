# Project instructions

## Bookkeeping is mandatory

This project keeps a written record in `bookkeeping/`. It is **not optional
documentation** — it is a deliverable, and it is written for a human who wants to
understand the project without reading the code.

**At the end of every build step, before starting the next one, update all four
files that the step touched.** Do this as part of the step, not as a batch
afterwards. A step is not finished until its bookkeeping is written.

| File | Update when |
|---|---|
| `bookkeeping/PROGRESS.md` | **Every step.** Flip the status in the at-a-glance table, then write the step's section: what was built, decisions made, what was found, what was verified |
| `bookkeeping/GLOSSARY.md` | **Every step that introduces new jargon.** Add the terms to the right section, in plain language |
| `bookkeeping/QUESTIONS.md` | **Whenever a question is asked** — however small. Record it verbatim, answer it, and note why it mattered |
| `bookkeeping/DECISIONS.md` | When a choice is made that could plausibly have gone another way. Record the alternative rejected and the reasoning |

### How to write them

- **Plain language.** Assume the reader is smart but does not know the jargon.
  Define a term the first time it appears, or link to `GLOSSARY.md`.
- **Real numbers only.** Record what was actually observed, including failures,
  attrition counts, and null results. Never write a placeholder or an expected
  value as though it were measured.
- **Record what was found, not just what was built.** Surprises, bugs, and stale
  paths are the most valuable entries.
- **Keep the status table honest.** ✅ done · 🔨 in progress · ⬜ not started ·
  ⚠️ done with caveats. Never mark a step ✅ before its checks actually pass.

---

## Non-negotiables from the implementation spec

1. **Never fabricate results.** Every number in the README must come from a real
   run. A weak, null, or negative finding is reported exactly as observed.
2. **Never commit secrets.** Credentials come from environment variables. `.env`
   and key files stay gitignored.
3. **No lookahead bias.** Any backtest signal derives only from markets settling
   before the train/test split.
4. **Verify API response shapes before parsing.** Print a raw response and adapt;
   do not assume field names or units.
5. **The README quotes only numbers present in `outputs/results.json`.**

## Git

Do not add Claude or Anthropic as a co-author, and do not add a "Generated with
Claude Code" line to commits or PRs.
