# 06: Demo polish (first thing to drop if time runs out)

**What to build:**
- The remaining baselines (LLM alone; our system without supersession, if 04 didn't already add it) added to the scoreboard.
- A calibration plot of confidence (High / Medium / Low) against correctness on the dev split.
- A one-page human view of a `why` answer: Decision, Evidence Chain, superseded history, Person to Ask, refusal state.

**Blocked by:** 03, 04

**Status:** ready-for-human

- [ ] The results table includes all four baselines.
- [ ] The calibration plot is produced from the harness output by one command.
- [ ] The human view renders the answer contract for any Anchor and works offline against the fixture graph.

## Comments

2026-11-20: Agent work merged into `main`. Tested only on the fixture history with scripted models. Left for a human: produce the real calibration plot from a dev-split run (`whycode-eval calibration --run <dir>`).
