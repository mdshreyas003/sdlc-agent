# whycode

Answers "why is this CockroachDB schema-change code the way it is?" for coding agents, over MCP: the Decisions
that govern a function, file, package or cluster setting, each with a verbatim quote, its Discussion, date,
Incidents and the Person to Ask, or an explicit refusal. Spec: `.scratch/why-mvp/spec.md`. Vocabulary:
`GLOSSARY.md`. Answer contract: `src/whycode/contract.py`.

## `why` on the fixture history

The fixture (`src/whycode/fixtures/miniature/`) is a hand-built miniature of CockroachDB history: two RFCs, PRs
with diffs and reviews, a regression fixed by a PR, a revert, cluster settings, and records after the
2024-06-30 cutoff that must never be ingested. Its recorded extraction responses let the graph build offline.

```sh
# 1. A local Neo4j (or point NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD at AuraDB instead)
docker run -d --name whycode-neo4j -p 7687:7687 -e NEO4J_AUTH=neo4j/whycode-local neo4j:5
export NEO4J_PASSWORD=whycode-local

# 2. Build the fixture graph (recorded extractions; add --extractor anthropic to extract with Sonnet 5.5)
uv run whycode build

# 3. Ask from the shell (WHY_COMPOSER=template answers without a model)
export ANTHROPIC_API_KEY=...            # Opus 5.5 composes the answer
uv run whycode why pkg/sql/schema_changer.go
```

From Claude Code: the repo's `.mcp.json` registers the `why` server (`uv run why-mcp`). Start `claude` in the
repo with the variables above exported, approve the server in `/mcp`, then ask, for example, "Use the why
tool on `pkg/sql.(*SchemaChanger).exec` before changing its retry loop."

Configuration (all environment variables) is documented in `src/whycode/config.py`. Model responses are
cached in `.cache/models` so rebuilds are reproducible.

## Tests

`uv run pytest tests` starts one disposable Neo4j container per session (Docker; with Colima the socket
override is set in `tests/conftest.py`), or uses `NEO4J_TEST_URI` / `NEO4J_TEST_PASSWORD` if set. Models are
always scripted in tests.

## Layout

| Module (`src/whycode/`) | Role |
|---|---|
| `history/` | History source seam (`HistorySource`), records, cutoff rules (`load_history`), fixture replay, GitHub REST payload mapping, RFC headers |
| `codeindex/` | Code Entities, aliases, diff touches and exact name mentions; tree-sitter Go parser |
| `linker.py` | Stated Links from written identifiers (closes, reverts, references) |
| `discussions.py`, `decisions.py` | Discussions as authored segments; Decision extraction behind the `DecisionProposer` seam, kept only with a verbatim quote |
| `build.py`, `graph/` | Graph building and the idempotent Neo4j store |
| `answer/` | Fixed read-only query patterns, composer seam, verifier, confidence scorer, `AnswerEngine` |
| `mcp_server.py`, `cli.py` | MCP server (`why-mcp`) and the `whycode` command |
| `quotes.py`, `ids.py` | The one verbatim rule and the node id convention, shared with the scoreboard |
