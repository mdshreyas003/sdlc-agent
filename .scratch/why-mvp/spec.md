# Spec: Why-MVP, a rebuild of the legacy prototype around Decisions, Supersession and coding agents

Status: ready-for-agent

Vocabulary: `GLOSSARY.md`. Design records: ADR-0001 (agent-first), ADR-0002 (CockroachDB schema-change scope, held-out evaluation). The legacy prototype (`legacy/`, "Engineering Memory") is a **reference, not a base**. We copy proven ideas and small pieces of code from it, and leave its breadth behind.

## Problem Statement

A developer, or a coding agent working without any project history, can read what a piece of CockroachDB schema-change code does but not why it is that way. The reasons are spread across RFCs, PR descriptions, review threads and linked issues, and some of those reasons were later overturned. Keyword and vector search return text that *mentions* a topic, not the Decision that governs the code. They also quote dead Decisions as if they were still live. An agent that "cleans up" an odd-looking check or cluster setting can quietly reintroduce a bug the team already fixed.

The legacy prototype proved part of the answer: a graph of Stated Links, a fixed read-only query layer, and code that checks every quote word for word. But it stops at raw records. It has no notion of a Decision, no Supersession, and no agent-facing interface. It also spends most of its code on breadth that doesn't help win: three source systems, workspaces, credential management, background sync, a multi-provider LLM layer, a multi-round planning loop, and a full workbench UI. Its gold set is not human-verified, so it has no score it can stand behind.

## Solution

A small system with two jobs:

1. **Build** a graph from one scoped slice of CockroachDB history (schema-change RFCs, the PRs that touch the schema-changer code, and their linked issues, up to 2024-06-30). The graph holds Stated Links between records, plus **Derived** Decisions and Supersession edges, each pointing to the verbatim quote it rests on.
2. **Answer** through an MCP server with two tools:
   - `why(anchor)` returns the Live Decisions that govern a Code Entity, with an Evidence Chain, a High/Medium/Low confidence, the superseded history, the Person to Ask, or a refusal.
   - `check_change(diff)` returns Fence Warnings for Live Decisions that a proposed Change would contradict or reverse.

An evaluation harness scores the same tools against baselines on a human-verified gold set and a Held-out Window. It does this with the legacy evaluation discipline: same corpus, same models, committed prompts, a dev/test split, and bootstrap confidence intervals.

## User Stories

### Coding agent (primary user, ADR-0001)
1. As a coding agent, I want to call `why` with a function name, so that I learn the reasons behind it before I edit it.
2. As a coding agent, I want to call `why` with a file path, so that I get the Decisions governing that file as a whole.
3. As a coding agent, I want to call `why` with a cluster setting name, so that I understand why a setting exists and why it has its default.
4. As a coding agent, I want each answer to come back as structured data (Decisions, quotes, node IDs, confidence, refusal flag), so that I can act on it without parsing prose.
5. As a coding agent, I want an explicit refusal when no Live Decision reaches the Anchor, so that I don't treat silence or invented text as permission.
6. As a coding agent, I want a refusal to still include the nearest evidence and the Person to Ask, so that I know where to look next.
7. As a coding agent, I want to call `check_change` with my diff before committing, so that I learn if I'm about to reverse a Live Decision.
8. As a coding agent, I want each Fence Warning to name the Decision, quote it, and point to the Incident it prevented (if any), so that I can change course or justify the override.
9. As a coding agent, I want `check_change` to return no warnings for a diff that touches no governed Code Entity, so that I'm not slowed down by noise.
10. As a coding agent, I want superseded Decisions labelled as superseded and never presented as current, so that I don't restore dead behaviour.
11. As a coding agent, I want Refinements shown as partly live, so that I respect the parts of the earlier Decision that still hold.
12. As a coding agent, I want every node ID I'm given to resolve to a real record, so that I can follow up on any citation.

### New developer (secondary user)
13. As a new developer, I want to ask "why is this function like this?" and get the Decision, the Discussion that produced it, the Person to Ask, and the date, so that I don't have to interrupt a senior engineer.
14. As a new developer, I want every sentence in an answer to carry a citation I can open, so that I can verify it myself.
15. As a new developer, I want to see when a Decision was superseded, by what, and when, so that I don't follow outdated reasoning.
16. As a new developer, I want departed people marked as departed, with the next-best active person suggested, so that I contact someone who can actually answer.
17. As a new developer, I want a confidence label I can trust (High answers are right most of the time), so that I know how much to rely on it.
18. As a new developer, I want to ask a free-form question that names no exact Code Entity, and either get matched to one or get a clear refusal, so that I'm not misled by a loose match.

### Hackathon team (builder and evaluator)
19. As a builder, I want ingestion to run from one command and read from a local cache on re-runs, so that GitHub rate limits don't block iteration.
20. As a builder, I want re-running the build to produce the same graph (stable IDs, idempotent writes), so that results are reproducible.
21. As a builder, I want ingestion to stop at a configurable cutoff date, so that the Held-out Window really is hidden.
22. As a builder, I want every Derived node and edge tagged as derived and linked to its verbatim quote, so that Stated Links and model judgment never get mixed up.
23. As a builder, I want Decision extraction to throw away any candidate without a verbatim quote, so that hallucinated Decisions never enter the graph.
24. As a builder, I want explicit Supersession (RFC status, reverts, "supersedes #N") parsed without a model, so that it costs nothing and is always correct.
25. As a builder, I want inferred Supersession judged as supersedes / refines / unrelated, with a quoted justification, so that Refinements aren't wrongly marked dead.
26. As a builder, I want the supersession judge scored against the explicit cases, so that I know how far to trust inferred edges.
27. As a builder, I want answers produced only from nodes returned by fixed query patterns, so that the model can never query the database freely.
28. As a builder, I want citations and quotes checked in code after the answer is written, with anything unverifiable dropped and confidence lowered, so that a fabricated citation never reaches the user.
29. As a builder, I want confidence computed from graph properties (link type, source type, explicit vs inferred supersession, presence of a rationale quote), so that it's explainable and not just how sure the model sounds.
30. As an evaluator, I want a gold set with automatic labels from history, at least 30 human-written questions (including traps and unanswerable ones), and Held-out Window questions, so that the scores cover easy, hard and adversarial cases.
31. As an evaluator, I want every gold quote checked word for word against the raw corpus and marked human-verified before it counts, so that the reported scores can be defended.
32. As an evaluator, I want one command to run our system and every baseline (LLM alone, vector RAG, git-tools agent, our system without supersession) with the same models, so that differences come from method, not model.
33. As an evaluator, I want answer correctness, citation precision, supersession catch rate, refusal accuracy, invented-answer rate, and cost and latency reported per question type with confidence intervals, so that judges can see where we win and where we don't.
34. As an evaluator, I want a calibration plot of confidence against correctness, so that "High" visibly means something.
35. As an evaluator, I want an agent comparison: about 8 real post-cutoff Changes that were later reverted or caused an Incident, run with and without our tools, so that I can show the agents broke fewer reasons they didn't know about.
36. As an evaluator, I want the test split scored once, with prompts committed and not tuned on test questions, so that the numbers are honest.
37. As a presenter, I want a minimal human view of a `why` answer (Decision, Evidence Chain, superseded history, Person to Ask), so that the demo is legible to judges.

## Implementation Decisions

### Modules (deep, few, each behind a small interface)

- **History source.** Fetches and caches the scoped RFCs, PRs (description, review comments, files changed, merge date, author, approvers) and linked or `A-schema-*` issues from GitHub, cut off at a configurable date. A fixture source with the same interface replays recorded payloads. *Legacy reference:* keep the "same clients, fake transport" idea and the cursor and page handling. Drop the Jira and Slack adapters, workspaces, and the background-job and progress machinery.
- **Code index.** Parses the scoped Go packages at the cutoff commit into package, file and function Code Entities, and pulls cluster settings out of their registration calls. No line-level anchoring and no blame replay.
- **Linker (Stated Links).** Turns source structure and identifiers written in text (`#N`, PR and commit URLs, "Fixes #N", RFC references, revert subjects) into Stated Links, each with an origin and a locator. *Legacy reference:* port the text-reference extraction and its "no fuzzy matching" rule nearly as is.
- **Decision extractor (Derived).** Uses Sonnet 5.5 to extract zero or more Decisions per Discussion: what was chosen, rationale, alternatives rejected, verbatim quote, date, authors. Each quote is checked against its source text in code before the Decision is kept. Each Decision links to Code Entities as either a **hard** link (through the diff of the Change that implements it) or a **soft** link (a name mentioned in the text that matches the code index).
- **Supersession detector.** Explicit Supersession comes from parsing, with no model. Inferred Supersession comes from candidate pairs that share a governed Code Entity (B later than A), which Opus 5.5 labels supersedes / refines / unrelated with a quoted justification. Inferred edges are tagged derived.
- **Graph store.** Neo4j AuraDB, written idempotently with stable canonical IDs. Records that are referenced but not ingested are stored as stubs and are never cited. *Legacy reference:* keep canonical-ID and upsert semantics; widen the schema.
- **Answer engine.** Behind `why(anchor)` and `check_change(diff)`, it runs four steps:
  1. **Resolve** the Anchor, by exact match first. Free-form questions get one entity-matching step; if that is unsure, refuse.
  2. **Traverse** a fixed set of parameterised, read-only query patterns: Anchor → governing Decisions → Supersession chain → Discussion → People, plus Incidents.
  3. **Compose** with Opus 5.5, using only the returned nodes, with one citation per sentence.
  4. **Verify** in code: drop citations not in the retrieved evidence, drop quotes that aren't word-for-word matches, lower confidence for anything dropped, and refuse if nothing survives.

  *Legacy reference:* port the verifier and the query-template safety checks (read-only, row and time caps, EXPLAIN check at startup). **Drop** the LangGraph understand / plan / evaluate loop, the multi-round planning, and the text-to-Cypher step. The query patterns are fixed, so no planning is needed.
- **Confidence scorer.** A pure function from graph properties to High / Medium / Low, calibrated on the dev split.
- **MCP server.** Exposes `why` and `check_change` and is the primary interface. A thin HTTP endpoint plus a one-page view for humans is the only UI.
- **Eval harness.** Gold set, systems, runner, scorer. *Legacy reference:* port the runner, the record shape shared by all systems, the fact-level judge, and the bootstrap and paired-difference statistics. Replace the BM25 baseline with dense vector RAG using the shared embedding model, and add the git-tools agent baseline and the "our system without supersession" baseline.

### Answer contract (shared by MCP, eval, and the human view)

```
Answer {
  anchor: {kind: function|file|package|setting, id}
  refused: bool
  confidence: High|Medium|Low
  decisions: [{id, choice, rationale, quote, date, status: live|superseded|refined,
               superseded_by?, explicit_or_inferred?, link: hard|soft}]
  evidence_chain: [{node_id, kind, url, quote}]
  people: [{handle, role: author|approver, active: bool}]
  incidents: [{id, url}]
  sentences: [{text, cites: [node_id]}]
}
FenceWarning { decision_id, entity_id, reason, quote, incident_ids, confidence }
```

### Graph schema (summary)

- **Nodes:** Decision (derived), Change, Discussion, Person, Incident, Code Entity (Package / File / Function / Setting), and stubs.
- **Stated relationships:** contains, closes or fixes, references, touches, authored or reviewed.
- **Derived relationships:** Discussion → Decision (yields); Decision → governs → Code Entity (hard / soft); Decision → supersedes / refines → Decision (explicit / inferred).
- Every relationship carries `origin` (stated | derived), a `locator` or quote, and `observed_at`.

### Simplifications relative to legacy (explicit cuts)

- One source system (GitHub, with RFCs read from the repository), not three.
- No workspaces, no credential UI or encryption, no background sync jobs, and no isolation by scope. One scoped corpus, configured by environment variables.
- One LLM provider (Anthropic): Sonnet 5.5 for extraction, Opus 5.5 for judging and composing, and one embedding model shared with the baselines. The multi-provider presets are dropped.
- No multi-round agent loop and no text-to-Cypher.
- No blame replay: the code index works on a checkout at the cutoff commit.
- No saved investigations, no SSE trace, no Next.js workbench, no video pipeline, and no deploy targets beyond what the demo needs.
- The legacy synthetic demo workspace is replaced by a small fixture history, which doubles as the test fixture.

## Testing Decisions

- **A good test** drives the system from the outside and checks only observable behaviour (the graph's contents, or the answer contract). It never checks prompts, intermediate state, or which query pattern ran. Models are replaced by scripted responses in tests; real-model behaviour is covered by the eval harness, not by unit tests.
- **Seam 1: graph building.** Input: a small fixture history (a few RFCs with `Status:` headers, PRs with diffs and review comments, a revert, a "Fixes #N" issue, a cluster setting) plus scripted extraction and judge responses. Assert on graph contents:
  - Decisions exist only when their quote appears word for word in the source.
  - Hard and soft governs links point to the right Code Entities.
  - Explicit Supersession is parsed from status and revert data.
  - The judge's three labels become the right edges, tagged derived.
  - A re-run leaves node and edge counts unchanged.
  - Nothing after the cutoff date is ingested.
- **Seam 2: MCP tools.** Input: the graph built in seam 1 plus scripted composer responses. Call `why` and `check_change` and assert on the answer contract:
  - A governed function, file and setting each return Live Decisions with a full Evidence Chain.
  - A superseded Decision is labelled superseded and never presented as live.
  - A Refinement is shown as partly live.
  - An ungoverned Anchor returns a refusal with the nearest evidence and the Person to Ask.
  - A fabricated node ID or a quote that isn't word for word never appears in the output, and confidence drops.
  - A diff that reverses a fixture Decision returns a Fence Warning.
  - An unrelated diff returns none.
  - Departed people are flagged.
- **Eval harness.** Tested through the same contract with stub systems: a known answer set produces known metric values, and the statistics reproduce fixed-seed intervals. The real-model runs are the evaluation itself, not tests.
- **Prior art (legacy, reference only):** fixture-replay ingestion tests against a disposable Neo4j; verifier unit tests with scripted models; end-to-end cases in a JSON file with `cites_all` / `answer_mentions_any` assertions; eval tests with stub systems. Reuse these patterns, not the code.

## Out of Scope

- Jira, Slack, mailing lists, and other sources of incidents or chat.
- Workspaces, multi-user or multi-tenant use, OAuth, credential management UI.
- Incremental or webhook sync; anything beyond a bounded backfill up to the cutoff.
- Line-level anchoring and blame.
- LLM-written Cypher; any multi-round agent planning.
- The PR bot that posts Fence Warnings on new pull requests (a "future growth" story only).
- Whole-repository ingestion; languages other than Go; other repositories.
- The Kafka corpus and its 75 legacy gold questions (superseded by ADR-0002; ideas reused, data not).

## Further Notes

- **Priority order** (hackathon):
  - **P0:** ticket 01 (`why` on fixtures) and ticket 03 (scoreboard), from hour 0. Then ticket 02 (real CockroachDB slice).
  - **P1:** ticket 04 (Supersession) and ticket 05 (`check_change` and the agent comparison).
  - **P2:** ticket 06 (demo polish).
- **A principle carried over from legacy:** "the model proposes, code decides". The new Derived layer keeps it: every Derived node is accepted only after a word-for-word quote check in code, and confidence ranks derived links below Stated Links.
- **Lessons from the legacy evaluation that apply directly:**
  - Hide the answer key (exclude RFC text from the system for questions that test cross-artifact reasoning).
  - Build unanswerable questions by removing evidence (ablation), so no new labelling is needed.
  - Include traps where events are close in time but not linked.
  - Report losses as well as wins.
- **Fixture history:** a hand-built miniature of the CockroachDB shapes, not synthetic company data. The same fixtures support the human-view demo when the network is unavailable.
