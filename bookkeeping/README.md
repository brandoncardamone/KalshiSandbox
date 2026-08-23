# Bookkeeping

Plain-English records of how this project was built. Nothing here is imported by
the code — these files exist so the work can be reconstructed and understood
later, by a human, without re-reading the whole codebase.

| File | What it holds |
|---|---|
| [`GLOSSARY.md`](GLOSSARY.md) | Every term of art used in the project, defined in plain language, tagged with the step that introduced it |
| [`PROGRESS.md`](PROGRESS.md) | The 10-step build plan: status, what was actually done, what was found |
| [`QUESTIONS.md`](QUESTIONS.md) | Every question asked during the build, with the answer and why it mattered |
| [`DECISIONS.md`](DECISIONS.md) | Choices made and the reasoning, especially where a different choice was plausible |

## Update rule

These are updated **at the end of every build step**, before moving to the next
one. See [`../CLAUDE.md`](../CLAUDE.md) for the standing instruction.

The test of whether they're working: someone who has never seen this repo should
be able to read `PROGRESS.md` top to bottom and understand what was built and
why, reaching for `GLOSSARY.md` whenever a word is unfamiliar.
