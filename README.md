# whycode

Answers "why is this CockroachDB schema-change code the way it is?" for coding agents, over MCP: the Decisions
that govern a function, file, package or cluster setting, each with a verbatim quote, its Discussion, date,
Incidents and the Person to Ask, or an explicit refusal. Spec: `.scratch/why-mvp/spec.md`. Vocabulary:
`GLOSSARY.md`. Answer contract: `src/whycode/contract.py`.

## `why` on the fixture history

The fixture (`src/whycode/fixtures/miniature/`) is a hand-built miniature of CockroachDB history: RFCs (one
superseded by another), PRs with diffs and reviews, a regression fixed by a PR, a revert and a later refinement,
cluster settings, and records after the 2024-06-30 cutoff (the Held-out Window) that must never be ingested at
the default cutoff. Its recorded extraction and supersession-judge responses let the graph build offline.

```sh
# 1. A local Neo4j (or point NEO4J_URI/NEO4J_USERNAME/NEO4J_PASSWORD at AuraDB instead)
docker run -d --name whycode-neo4j -p 7687:7687 -e NEO4J_AUTH=neo4j/whycode-local neo4j:5
export NEO4J_PASSWORD=whycode-local

# 2. Build the fixture graph (recorded extractions and judgments; --extractor anthropic extracts with Sonnet 5.5
#    and then judges inferred Supersession with Opus 5.5; --judge none keeps explicit Supersession only)
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

## Supersession

`why` labels every Decision `live`, `superseded` or `refined` (partly live), with what superseded it, when, the
verbatim statement or justification, and whether history states it (explicit: reverts, RFC `Status:` headers,
"supersedes #N") or the judge inferred it (Opus 5.5 over pairs of Decisions governing the same code). Rules:
`src/whycode/supersession.py`; how answers use them: `src/whycode/answer/engine.py`.

```sh
uv run whycode supersession-report --out eval/results/supersession-judge.md   # judge precision/recall vs explicit cases
```

It reads the built graph and asks the judge (default `--judge anthropic`, cached in `.cache/models`) about every
explicit Decision-to-Decision Supersession with the explicit statement masked, plus the candidate pairs around
those cases, then prints precision, recall and every disagreement for a human to check.

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
| `supersession.py` | Supersession detector: explicit parsing, candidate pairs, the judge seam (`SupersessionJudge`), the judge report |
| `answer/` | Fixed read-only query patterns (all honour `as_of` / `exclude`), composer seam, verifier, confidence scorer, `AnswerEngine`; `answer/systems.py` plugs it into the scoreboard |
| `mcp_server.py`, `cli.py` | MCP server (`why-mcp`) and the `whycode` command |
| `quotes.py`, `ids.py` | The one verbatim rule and the node id convention, shared with the scoreboard |

## Extension points for later tickets

- **02 (real slice).** Implement `HistorySource` (`history/__init__.py`); REST bundles map through
  `history/github_rest.py`; `load_history` applies the cutoff whatever the source returns. `Rfc.authors` are GitHub
  logins (take them from the RFC PR). Index the checkout with `parse_go_tree(root, scope=[...])`; it reads literal
  setting keys only (add same-package consts and `WithName` aliases there). Add `--history github` to `cli.py`.
  Write the scoreboard corpus with `write_jsonl(path, corpus_records(graph))` (`graph/corpus.py`) so ids and texts
  match what `why` cites. Bare-name mention rules for soft links live in `CodeIndex.mentions`.
- **04 (Supersession), done.** `SUPERSEDES` / `REFINES` edges (later node -> earlier Decision) carry `basis`,
  `quote`, `source`, `observed_at` (`supersession.py` docstring). `build_graph(..., judge=None)` adds explicit
  Supersession only; pass a `SupersessionJudge` for inferred edges (ticket 02: `AnthropicSupersessionJudge` over
  the real slice; the recorded fixture judge only knows fixture pairs). Hard `GOVERNS` edges now name their
  implementing `change` and hold from its merge date. For `check_change` (05), a Live Decision is one whose
  `DecisionView.status` is not `superseded`. Known limits: a revert of a revert does not restore the original
  Decision; an RFC's status is read from its text as of the build, so a status set inside the Held-out Window is
  visible to `as_of` queries; `Person.active` is relative to the build cutoff.
- **05 (`check_change`).** `CodeIndex.touched_by(FileChange)` maps a diff to Code Entities; every `CodeEntity` field
  is stored on its graph node, so the server can rebuild a `CodeIndex` from the nodes of the diff's files.
  `FenceWarning` is in `contract.py`; register the tool next to `why` in `mcp_server.py`.
- **Scoreboard "ours" system, done.** `whycode.answer.systems:ours` and `:ours_without_supersession` (see
  `eval/README.md`). Build the graph through the end of the Held-out Window (`whycode build --cutoff <window end>`)
  and export the corpus from that graph; every pattern then filters by the query's `as_of` and `exclude` (record
  level, like the scoreboard's corpus). Our system reports no model usage yet, so its cost column is empty.
