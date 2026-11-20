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

## The real CockroachDB slice

Scope (ADR-0002, fixed in `src/whycode/history/scope.py`): the 28 schema-change RFCs, the pull requests merged
into master by 2024-06-30 whose commits touch `pkg/sql/schemachanger`, `pkg/sql/schema_changer.go`,
`pkg/sql/schemachange` or `pkg/sql/schema_change_cluster_setting.go` (1106 of them), the `A-schema-*` issues
opened by then (871), and the issues those pull requests and RFCs link to. The code index parses the scoped
packages plus the neighbouring files that register schema-change cluster settings, at cutoff commit `d132535`.

```sh
export GITHUB_TOKEN=$(gh auth token)    # only needed for responses that are not cached yet
export ANTHROPIC_API_KEY=...            # Sonnet 5.5 extracts Decisions (cached in .cache/models)
export NEO4J_PASSWORD=...               # plus NEO4J_URI / NEO4J_USERNAME for AuraDB

uv run whycode fetch                    # optional: the backfill alone (~9,400 REST calls, ~2 h of rate limit)
uv run whycode build --history github   # checkout + fetch (cached) + graph -> Neo4j; prints the counts
uv run whycode check-citations --sample 20   # every node id in 20 answers resolves (exit 1 if not)
```

- The checkout (`.cache/cockroach`, ~55 MB) is a sparse, blobless clone of the scoped directories at the cutoff
  commit. Every GitHub response is stored in `.cache/github`, so the backfill is resumable (re-run the same
  command after a stop; rate limits are waited out) and a re-run makes no GitHub calls (`"github_calls": 0` in
  the output; `--offline` refuses to touch the network at all). Both live under the ignored `.cache/`.
- `--limit N` bounds a run (the N most recently merged pull requests, the N most recent labelled issues, at most
  N linked issues); use the same `--limit` for `fetch` and `build` to stay on the cache. `--extractor none`
  builds the graph without Decisions (no Anthropic key needed).
- The build refuses to write a graph holding any date after the cutoff and prints `latest_date`. It writes the
  scoreboard corpus (`data/corpus.jsonl`, or `WHY_CORPUS`) and records the counts in `data/graph-counts.json`.
- Known approximations: issue selection and Incident labels use the labels GitHub shows today (label-at-cutoff
  is not replayed); issue and PR bodies are as edited today; Reviewable review bodies quote earlier comments
  ("Previously, X wrote…") inside the reviewer's post, so a Decision quoted only from such a block is attributed
  to the reviewer (the extractor takes the first post holding the quote, usually X's own earlier review).

`data/graph-counts.json` currently holds a **partial** bounded run (`--limit 15 --extractor none`, so no
Decisions): 0 Decisions, 42 Changes (15 PRs, 27 commits), 73 Discussions (15 PRs, 30 issues, 28 RFCs),
2458 Code Entities, 4 Incidents, 43 People. The full run replaces it.

Checks to do from Claude Code after the full build (not yet run: they need the Anthropic key): `why` on a
function (e.g. `pkg/sql.(*SchemaChanger).exec`), a file (`pkg/sql/schema_changer.go`) and a setting
(`schemachanger.job.max_retry_backoff`) should each return an Evidence Chain, and an Anchor no Decision reaches
should be refused.

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
those cases, then prints precision, recall and every disagreement for a human to check. On the real slice,
`whycode build --history github` judges inferred Supersession with Opus 5.5 (one cached call per candidate pair;
`--judge none` keeps explicit Supersession only). Not run on real data yet: it needs the Anthropic key.

## Tests

`uv run pytest tests` starts one disposable Neo4j container per session (Docker; with Colima the socket
override is set in `tests/conftest.py`), or uses `NEO4J_TEST_URI` / `NEO4J_TEST_PASSWORD` if set. Models are
always scripted in tests.

## Layout

| Module (`src/whycode/`) | Role |
|---|---|
| `history/` | History source seam (`HistorySource`), records, cutoff rules (`load_history`), fixture replay, GitHub REST payload mapping, RFC headers; the real slice: `scope.py`, `github.py` (cached transport, client, `GitHubHistorySource`), `checkout.py` |
| `codeindex/` | Code Entities, aliases, diff touches and exact name mentions; tree-sitter Go parser (same-package const setting keys, `WithName` aliases) |
| `audit.py` | The citation audit behind `whycode check-citations` |
| `linker.py` | Stated Links from written identifiers (closes, reverts, references) |
| `discussions.py`, `decisions.py` | Discussions as authored segments; Decision extraction behind the `DecisionProposer` seam, kept only with a verbatim quote |
| `build.py`, `graph/` | Graph building, the idempotent Neo4j store, and the export of citable records in the scoreboard's corpus format (`graph/corpus.py`) |
| `supersession.py` | Supersession detector: explicit parsing, candidate pairs, the judge seam (`SupersessionJudge`), the judge report |
| `answer/` | Fixed read-only query patterns (all honour `as_of` / `exclude`), composer seam, verifier, confidence scorer, `AnswerEngine`; `answer/systems.py` plugs it into the scoreboard |
| `mcp_server.py`, `cli.py` | MCP server (`why-mcp`) and the `whycode` command |
| `quotes.py`, `ids.py` | The one verbatim rule and the node id convention, shared with the scoreboard |

## Extension points for later tickets

- **02 (real slice), done.** `whycode build --history github` writes the real graph, the scoreboard corpus
  (`data/corpus.jsonl`) and `data/graph-counts.json`; see "The real CockroachDB slice". Tests serve a fake GitHub
  (`tests/fake_github.py`, the miniature history as native REST/GraphQL payloads) through the real client and
  cache. A setting's `WithName` / `WithRetiredName` names are in `CodeEntity.names` (stored on the node as
  `names`, and in `aliases`).
- **04 (Supersession), done.** `SUPERSEDES` / `REFINES` edges (later node -> earlier Decision) carry `basis`,
  `quote`, `source`, `observed_at` (`supersession.py` docstring). `build_graph(..., judge=None)` adds explicit
  Supersession only; pass a `SupersessionJudge` for inferred edges (`whycode build --judge`, by default the same kind
  as the extractor: Opus 5.5 for the real slice; the recorded fixture judge only knows fixture pairs). Hard `GOVERNS` edges now name their
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
