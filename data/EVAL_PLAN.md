# Benchmark and evaluation plan

Goal: show, with numbers anyone can re-run, that our system gives **correct, cited, honest** "why" answers, and does it better than the obvious alternatives.

## 1. The one idea

A fair benchmark = **same data, same questions, same LLM, same budget**. Only the *method* changes. Then any difference in score is caused by our method (graph + claim verification), not by a bigger model or more data.

## 2. What we compare (systems)

| Id | System | Why it is in the table |
|---|---|---|
| B0 | LLM alone, no data | Shows how much the model already "knows" (Kafka and Python are famous). Honest floor. |
| B1 | Plain vector RAG over the same raw files, no graph, no verification | What most teams will build. This is the real rival. |
| S- | Our system without the quote verifier | Proves the verifier matters. |
| S | Our full system | The result. |

Optional later: B2 = a coding agent with grep/search tools on the same files.

## 3. The data

What we already have (`data/`): 20 KIP/PEP decision docs, 16 Jira issues, 10 GitHub issues/PRs, 30 Python threads, 1,070 Kafka mailing messages, 20 draft questions. All hashed in `raw/hashes.json`.

What is wrong with it today:

1. **Questions are too easy.** They come from the doc title and the answer is in the same doc. Plain RAG scores well on that. It proves nothing.
2. **Zero commits**, only 10 PRs. Our product's code-to-why story is untested.
3. **Mailing messages are not grouped into threads.**
4. **No hop evidence** (`gold_hop_evidence` empty) and nothing human-verified.
5. **Only 20 questions.** Too few to tell systems apart (see section 6).

### Fixes (simple, in this order)

1. **Hide the answer key.** Load everything into the system *except* the KIP/PEP page itself. The reason must then be found in Jira + mail + PRs, like a real company that never wrote a design doc. The KIP/PEP is used only as gold. (Keep a small "doc visible" set for the easy tier.)
2. **Three question tiers**, ~25 each (target 75):
   - **A Easy:** answer is in one document (current 20 live here).
   - **B Cross-artifact:** needs two or more artifacts (e.g. Jira + mail thread). Gold lists every artifact and its quote.
   - **C Unanswerable:** no reason exists in the data. Cheap way: take tier A/B questions and **delete their gold artifacts** from the corpus. No new annotation.
3. **Trap questions (~10):** a commit/PR sits near an unrelated discussion in time, with no reference between them. System must not claim a link.
4. **Contamination slice:** include recent KIPs/PEPs (newer than the LLM's training data). If we only win on famous old ones, it is memory, not retrieval.
5. **Pull a few hundred Kafka commits/PRs** that the Jira keys point to, so code-level questions exist.
6. **Human check:** you review every gold quote (`human_verified=true`). Have a second person re-check 20% and report agreement.

## 4. What we measure (five numbers, no more)

| Metric | How | Automatic? |
|---|---|---|
| **Correct answer** | Atomic gold facts per question ("mentions ZK metadata bottleneck"). Judge LLM ticks each fact. | Yes + 20% human audit |
| **Citation validity** | Every cited quote must appear verbatim in the cited artifact. | Yes, pure string check |
| **Evidence recall** | Did the answer cite the gold artifacts? | Yes |
| **Abstention accuracy** | Tier C: said "not established". Tiers A/B: did not refuse. | Yes |
| **Cost + time per question** | Tokens and seconds logged by the runner. | Yes |

Headline number: **confident-wrong rate** = share of answers that state something unsupported or cite something fake. Our claim is that this is near 0 for us and clearly higher for B0/B1.

## 5. Fairness rules (write these in the report)

- One LLM and one temperature for every system. Judge LLM is different from the answering LLM where possible.
- Same corpus for B1 and S. Same top-k budget of retrieved text.
- Prompts for every system are committed to the repo; none tuned on the test questions.
- Split questions: **dev (30%)** to tune prompts, **test (70%)** touched once for the final table.
- Report failures and losses too. A table that only shows wins is not believed.

## 6. How to read results

- With about 75 questions, a gap under ~10 points may be noise. Use a **bootstrap confidence interval** and **paired comparison** (same question, system A vs B). Run each system 3 times and average.
- Scores per tier, not one blended number. Expect: all systems tie on tier A, we should win on B, C and traps. If we do not, we learn that before the demo.

## 7. Work order

| # | Step | Output | Effort |
|---|---|---|---|
| 1 | Group mail into threads; pull commits/PRs for the 20 records | richer `raw/` | small |
| 2 | Converter: raw files → system's source shapes (Jira → Jira adapter, mail → Slack-shaped, PR → GitHub) and load a workspace with the KIP/PEP hidden | `eval` workspace in Neo4j | medium |
| 3 | Grow gold to ~75 (tiers A/B/C, traps, recent slice), you verify | `gold/questions.jsonl` | main cost, ~5 min per question |
| 4 | Runner: for each system and question write answer + citations + cost to JSONL (reuses `agent.run`) | `eval/run.py` | small |
| 5 | Scorer: the five metrics above, plus confidence intervals | `eval/score.py`, one results table | small |
| 6 | Run dev set, fix real problems, run test set once, put table in the pitch | final numbers | small |

Optional after that: a time-to-answer test with 3-5 engineers, with vs without the tool, on 10 questions.

## 8. Open questions

1. Is there an **organizer-provided dataset or judge**? If yes, run on it too; it is the only truly shared yardstick. Our own benchmark is where we show extra edge.
2. Can we use the same LLM key budget for B0/B1/S and the judge?
3. Do we need real Slack, or is "mailing list as Slack stand-in" acceptable? (We say it openly in the report.)

## Note on process

Repo is in the specification phase. Adding eval requirements (FR/AC for the benchmark) needs spec approval before any `eval/` code is written.
