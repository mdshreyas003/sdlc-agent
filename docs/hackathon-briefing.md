# whycode in one page (hackathon briefing)

## The product in one sentence

**A coding agent asks "why is this code like this?" before it edits, and gets back the decision that governs that code, quoted word for word from history, marked live or dead, with who to ask. Before it commits, it gets warned if its diff undoes a decision.**

## The problem, in simple words

Code tells you *what*. The *why* is scattered across PRs, review threads, issues and design docs (RFCs/ADRs).
Search finds text that *mentions* a topic, not the *decision*. And old decisions that were later reversed still look authoritative.
When the senior engineer leaves, the why leaves with them. In a "dark factory" where agents write most code, **nobody** has that memory: the agent will happily "clean up" an odd check and bring back a bug the team already fixed.

## The idea: the Decision is the unit of knowledge

```
 history (PRs, reviews, issues, RFCs)          code (Go functions, files, packages, settings)
            │                                              │
            ▼                                              ▼
     Decision  = what was chosen + why + verbatim quote ──GOVERNS──► Code Entity
            │
            ├── SUPERSEDES / REFINES ──► older Decision   (so dead ones are labelled dead)
            ├── came from ──► Discussion (PR / issue / RFC)
            ├── people ──► Person to Ask (active or departed)
            └── prevented ──► Incident (regression issue a PR closed)
```

Two tools on top, served over MCP so any agent (Claude Code, Cursor, …) can call them:

| Tool | Input | Output |
|---|---|---|
| `why(anchor)` | a function, file, package or setting | Live Decisions, Evidence Chain, superseded history, Person to Ask, High/Medium/Low confidence, **or a refusal** |
| `check_change(diff)` | a proposed diff | **Fence Warnings**: "this diff undoes PR #104500, which implemented Decision X" |

Plus a small human web page (`whycode serve`) showing the same answer.

## Philosophy (what to say when judges push)

1. **"The model proposes, code decides."** An LLM extracts Decisions, but a Decision is kept only if its quote appears word for word in the source. Answers are checked after writing: any citation not in the retrieved evidence, or any quote not verbatim, is dropped and confidence goes down. Nothing → refusal.
2. **No free-form database access.** The LLM never writes Cypher. A fixed set of read-only query patterns walks the graph. Safer and explainable.
3. **Stated vs Derived.** Links a source states (PR closes issue, "Revert …") are facts. Links a model infers (a Decision, an inferred supersession) are tagged `derived` and ranked lower in confidence.
4. **Confidence comes from the graph, not the model's tone** (explicit vs inferred supersession, hard vs soft link, rationale present…).
5. **Refuse rather than invent**, and even a refusal points to the nearest evidence and someone to ask.
6. **Agent-first** (ADR-0001): everyone else will build "chat over a repo". We build a guardrail for coding agents, and it is measurable: same task, agent with vs without our tools.
7. **Prove it** with a scoreboard against baselines (LLM alone, vector RAG, git-tools agent, ours without supersession) on held-out history.

## Why CockroachDB, why Go, why Neo4j

- **Neo4j**: the problem statement says "graph problem, Neo4j AuraDB, GraphRAG". The value is in relationships (decision → code, decision → superseding decision).
- **CockroachDB** (ADR-0002): richest *ground truth* already written by its authors: RFCs with `Status: superseded` headers, ~600 revert PRs, "Fixes #N" links, cluster settings ("config flags nobody understands"). Ground truth = we can **prove** our answers.
- **Only the schema-change area**, history up to 2024-06-30: narrow and deep demos better than 119k commits. Everything after that date is the **Held-out Window**: "did we report answers that later changed as changed?" and the source of real agent tasks.
- **Go parsing** (`codeindex/go.py`) only because CockroachDB is written in Go: we need its functions and cluster settings as Code Entities. This is the one language-specific piece.

## How it works: three phases

**1. Build** (`whycode build`) → `build.py`
GitHub/fixture history → Stated Links (`linker.py`) → Decision extraction with Sonnet, verbatim check (`decisions.py`) → hard GOVERNS (via the PR's diff) / soft (name mentioned) → Supersession: explicit by parsing, inferred by Opus judging pairs (`supersession/`) → Neo4j (`graph/store.py`).

**2. Answer** (`why`, `check_change`) → `answer/engine.py`
Resolve anchor → fixed query patterns (`patterns.py`) → live/superseded rule (`status.py`) → compose with Opus, one citation per sentence (`compose.py`) → verify in code (`verify.py`) → confidence (`confidence.py`). Fence warnings: `fence.py`.

**3. Prove** (`whycode-eval`, `whycode-agents`) → `eval/`, `comparison/`
Gold questions, judge, baselines, bootstrap confidence intervals, calibration plot; and the with/without-tools agent comparison on 7 frozen tasks.

## Code map (~9,000 lines of Python, 189 tests, all passing)

| Area | Lines | What it is |
|---|---|---|
| `history/` | 1.0k | fetch + cache GitHub PRs/issues/RFCs, fixture replay, scope (ADR-0002) |
| `codeindex/` | 0.4k | Go parser: packages, files, functions, cluster settings |
| `linker.py`, `decisions.py`, `discussions.py`, `build.py` | ~0.8k | turning records into Decisions and edges |
| `supersession/` | 0.7k | explicit + inferred supersession |
| `graph/` | 0.25k | Neo4j store |
| `answer/` | 1.6k | the engine behind `why` and `check_change` |
| `mcp_server.py`, `cli.py`, `view.py` | ~0.6k | interfaces: MCP, CLI, web page |
| `eval/` + `comparison/` | **2.9k** | **proof only**: scoreboard and agent comparison |
| `legacy/` | — | the previous prototype ("Engineering Memory", Kafka). Reference only, not used. Ignore it. |

So roughly two thirds is the product, one third is "prove it works". You can skip `eval/` and `comparison/` when explaining the product.

## Problem statement coverage

| Asked by the brief | Status |
|---|---|
| Ingest commits, PRs, issues, design docs | Built. Real run done only partially (15 PRs, **no Decisions extracted yet**: needs an Anthropic key) |
| Graph: code entities ↔ decisions, people, incidents | Built |
| Answer NL questions with evidence chain (decision, discussion, person, date) | Built (`why`, free-form question matching) |
| Detect supersession | Built: explicit + inferred, live / superseded / refined |
| Confidence signal + refusal | Built |
| *Beyond the brief*: `check_change` fence warnings for agents | Built |
| *Beyond the brief*: scoreboard vs baselines, agent comparison | Harness built; **no real numbers yet** (gold set is draft, no run) |

**The honest status: everything is proven on a hand-built miniature of CockroachDB history (the fixture) with scripted models. Nothing has run on real data with real models yet.** That gap is your hackathon delta.

## Demo you can run right now (no API key, no internet)

```sh
docker start whycode-neo4j            # Neo4j already created on this machine (password whycode-local)
export NEO4J_PASSWORD=whycode-local
uv run whycode build                  # fixture graph, recorded model responses
WHY_COMPOSER=template uv run whycode why pkg/sql.isPermanentSchemaChangeError
uv run whycode check-change src/whycode/fixtures/miniature/proposed/validation-errors-always-permanent.diff
WHY_COMPOSER=template uv run whycode serve   # open http://127.0.0.1:8765/?anchor=pkg/sql.isPermanentSchemaChangeError
```

The story that function tells (this is your demo script):
1. May 2 2023, PR #101200: "validation errors are permanent, stop retrying". → **superseded**
2. May 10, PR #101450 reverts it: upgrades caused transient failures (Incident #101400). → **refined**
3. June 20, PR #104500: permanent only once the cluster version is finalized. → **live**
4. An agent proposes `if catalog.HasValidationError(err) { return true }` (looks like a harmless cleanup).
   `check_change` → two Fence Warnings: "this undoes #104500" (High) and "this brings back what #101450 removed, which fixed Incident #101400".

A plain vector search would have quoted #101200, the dead decision, as the answer.

Other good anchors: `sql.schemachanger.strict_planning_sanity_check.enabled` (departed people → who to ask instead), `scrun.RunStatementPhase` (an RFC superseded by a later RFC), `scbuild.Build` (a refusal).

## Reusability / where it fits in a software factory

- **Any agent**: it's an MCP server. Plug into Claude Code, Cursor, an autonomous agent pipeline.
- **Any repo**: only `history/scope.py` (what to ingest) and `codeindex/` (which language) are CockroachDB/Go-specific. The Decision / Supersession / Fence model is generic.
- **Positions in the factory loop**: before edit (`why` as context), before commit (`check_change` as a gate), in review (future: a PR bot posting Fence Warnings), at onboarding (the human page).
- In a dark factory, humans no longer review every diff. **Fence Warnings are the institutional memory that replaces the senior engineer's "wait, we tried that in 2023".**
