# 03: Scoreboard: gold set, harness, vector-RAG and git-tools baselines

**What to build:** One command scores any system that returns the answer contract against a gold set, and prints a results table per question type with bootstrap confidence intervals. The gold set has three parts:
- **Automatic labels** from history: RFC status, "Fixes #N" links, reverts.
- **At least 30 human-written questions**, including at least 5 unanswerable (built by deleting the evidence they need), at least 5 reversed or refined Decisions, and some traps where events are close in time but not linked.
- **Held-out Window questions**, each with its answer before and after the cutoff.

The baselines are **vector RAG** over the same corpus and a **git-tools agent** (log, blame, show and search over the pre-cutoff checkout). Both use the same answering model and the same embedding model as our system. Metrics:
- answer correctness (fact-level judge)
- citation precision
- supersession catch rate
- refusal accuracy
- invented-answer rate
- cost and latency

Port the legacy runner, judge and bootstrap statistics as references.

**Blocked by:** None (can start immediately; build against the answer contract and plug into 01 or 02 when they land)

**Status:** ready-for-human (gold answers need human judgement; the harness and baseline code can be done by an agent)

- [ ] Every gold quote is checked verbatim against the raw corpus, and a question counts toward scores only if it is marked `human_verified`.
- [ ] The questions are split into dev and test sets. Prompts are committed. The test split is scored once.
- [ ] Both baselines run end to end and appear in the results table.
- [ ] The judge's agreement is reported against at least 15 hand-labelled answers.
- [ ] Harness tests with stub systems produce known metric values and reproduce fixed-seed intervals.

## Comments

2026-11-20: Agent work merged into `main`. Tested only on the fixture history with scripted models. Left for a human: write at least 30 gold questions plus Held-out Window questions and mark them `human_verified`, hand-label at least 15 answers for judge agreement, then score the test split once (`eval/README.md`).
