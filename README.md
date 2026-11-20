# whycode

**Every claim is quoted, dated and checkable, or it is refused.**

Coding agents (and new engineers) can't see *why* code is the way it is. The reason lives in RFCs, PR reviews and
incident issues. So an odd-looking check gets "cleaned up" and the outage it prevented comes back.

`whycode` gives agents that history over [MCP](https://modelcontextprotocol.io), scoped today to CockroachDB's
schema-change code. Two tools:

| Tool | Ask | You get |
|---|---|---|
| `why(anchor)` | "Why is this function / file / package / cluster setting the way it is?" | The Decisions that govern it, each with a **verbatim quote**, its Discussion, date, Incidents, and a **Person to Ask**. Or an explicit refusal. |
| `check_change(diff)` | "I'm about to make this edit." | A **Fence Warning** for each live Decision the diff reverses or may contradict, with the quote and the incident it prevented. No model involved. |

Pitch and demo: [`docs/whycode.html`](docs/whycode.html). This page covers how it works and how to run it.

## Try it (offline, 60 seconds)

The repo ships a hand-built miniature of CockroachDB history (RFCs, PRs, a regression, a revert, cluster settings).
Model responses are recorded, so it builds with no GitHub token. You need [uv](https://docs.astral.sh/uv/) and Docker.

```sh
docker run -d --name whycode-neo4j -p 7687:7687 -e NEO4J_AUTH=neo4j/whycode-local neo4j:5
export NEO4J_PASSWORD=whycode-local

uv run whycode build                                   # build the graph from the fixture
WHY_COMPOSER=template uv run whycode why pkg/sql.isPermanentSchemaChangeError   # ask why, no API key needed
uv run whycode check-change src/whycode/fixtures/miniature/proposed/remove-retry-backoff.diff   # fence a bad diff
```

More ways in:

```sh
WHY_COMPOSER=template uv run whycode serve    # human view at http://127.0.0.1:8765/?anchor=scbuild.Build
claude                                        # in this repo: approve the `why` server in /mcp, then ask
                                              # "Use the why tool on pkg/sql.(*SchemaChanger).exec before changing its retry loop"
```

Set `ANTHROPIC_API_KEY` (and drop `WHY_COMPOSER=template`) to have Opus 5.5 compose the prose.
Demo anchors worth trying: `pkg/sql.isPermanentSchemaChangeError` (a revert, then a refinement),
`scrun.RunStatementPhase` (an RFC superseded by a later one), `scbuild.Build` (a refusal that shows the nearest evidence).

## When to use it

- An agent or person is about to **change, delete or "simplify"** code that looks odd, defensive or redundant.
- You need the **reason, source and owner** behind a design, not a summary of what the code does.
- You want a **guard in the agent loop**: run `check_change` on the diff before it lands.

Not for: code outside the indexed scope, or questions history never answered. Those are refused, by design.

## How it works

```
GitHub history ──► Decisions ──► Graph (Neo4j) ──► fixed queries ──► verified Answer
RFCs, PRs, reviews   only with     Changes, Discussions,   code → governing     every citation
issues, incidents    a verbatim    Incidents, People,      Decisions, live or    resolves, or
(cutoff-bound)       quote         Code Entities           superseded            it's a refusal
```

The design in four moves:

1. **History becomes a graph, and a Decision must be quoted.** A model proposes Decisions from Discussions, but one is
   kept only if its quote appears verbatim in the source. This is the single rule, in `quotes.py`.
2. **Answers come from fixed, read-only queries, not model memory.** Code Entities (parsed with tree-sitter) link to the
   Decisions that govern them. The model only phrases the result, and a verifier checks every cited node exists.
3. **Time is first-class.** Each Decision is `live`, `superseded` or `refined`, with what replaced it, when, and
   whether history states it (a revert, an RFC `Status:` line) or a judge inferred it. Superseded reasons never warn.
4. **Refuse rather than guess.** No evidence reaches the anchor → a refusal with `refusal_reason`. A loosely matched
   anchor caps confidence at Medium. Departed authors point to someone active (`ask_instead`).

### Honest evaluation

Records after **2024-06-30** (the Held-out Window) are never ingested at the default cutoff, so the agent comparison
and the scoreboard (`whycode-eval`) test on history the system has not seen. The build refuses to write a graph that
holds a later date.

### Code map

Every external dependency sits behind a small seam with a recorded or scripted stand-in, so tests never touch the
network or a model. The seams are the history source, the Decision proposer, the supersession judge, the composer and
the entity matcher.

| Where (`src/whycode/`) | What |
|---|---|
| `contract.py` | The Answer contract: the one schema every interface returns |
| `history/`, `codeindex/` | Records, cutoff rules, GitHub and fixture sources; the Go code index |
| `decisions.py`, `supersession/` | Quote-checked Decision extraction; explicit and inferred supersession |
| `build.py`, `graph/` | Graph build and the idempotent Neo4j store |
| `answer/` | Fixed queries, the Live Decision rule, composer, verifier, confidence, `fence.py` (`check_change`) |
| `mcp_server.py`, `cli.py`, `view.py` | Entry points: MCP (`why-mcp`), the `whycode` command, the human view |

## Go deeper

Real-slice build, flags and approximations, graph schema, free-form questions, agent comparison and tests:
[`docs/reference.md`](docs/reference.md). Vocabulary: [`GLOSSARY.md`](GLOSSARY.md). Decisions: [`docs/adr/`](docs/adr/).
