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
| `build.py`, `graph/` | Graph building, the idempotent Neo4j store, and the export of citable records in the scoreboard's corpus format (`graph/corpus.py`) |
| `answer/` | Fixed read-only query patterns, composer seam, verifier, confidence scorer, `AnswerEngine` |
| `mcp_server.py`, `cli.py` | MCP server (`why-mcp`) and the `whycode` command |
| `quotes.py`, `ids.py` | The one verbatim rule and the node id convention, shared with the scoreboard |

## Extension points for later tickets

- **02 (real slice).** Implement `HistorySource` (`history/__init__.py`); REST bundles map through
  `history/github_rest.py`; `load_history` applies the cutoff whatever the source returns. `Rfc.authors` are GitHub
  logins (take them from the RFC PR). Index the checkout with `parse_go_tree(root, scope=[...])`; it reads literal
  setting keys only (add same-package consts and `WithName` aliases there). Add `--history github` to `cli.py`.
  Write the scoreboard corpus with `write_jsonl(path, corpus_records(graph))` (`graph/corpus.py`) so ids and texts
  match what `why` cites. Bare-name mention rules for soft links live in `CodeIndex.mentions`.
- **04 (Supersession).** Explicit inputs already in the graph: `REVERTS` edges (PR -> PR by exact `Revert "<title>"`,
  PR or commit -> commit by full SHA; a commit's PR is its `CONTAINS` source) and RFC `status` / `status_raw` node
  properties plus `REFERENCES` edges with locator `header:Status#...`. `SUPERSEDES` / `REFINES` are already allowed
  edge types (`graph/__init__.py`). Surface them in the `governing` pattern (`answer/patterns.py`), fill
  `DecisionView.status` / `superseded_by` / `explicit_or_inferred` in `answer/engine.py`, and add a supersession
  field to `DecisionGrounding` (`answer/confidence.py`). Judge model id: `llm.JUDGE_MODEL`.
- **05 (`check_change`).** `CodeIndex.touched_by(FileChange)` maps a diff to Code Entities; every `CodeEntity` field
  is stored on its graph node, so the server can rebuild a `CodeIndex` from the nodes of the diff's files.
  `FenceWarning` is in `contract.py`; register the tool next to `why` in `mcp_server.py`.
- **Scoreboard "ours" system.** `AnswerEngine` does not yet honour `Query.as_of` or `Query.exclude`; both need
  filters in the query patterns before our system can run window and ablation questions honestly.
