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

### Free-form questions and the Person to Ask

`why` also takes a question in words. A question that names exactly one Code Entity (`SchemaChanger.exec`,
`schema_changer.go`) resolves without a model. Otherwise one entity-matching step (Opus 5.5, cached) picks from a
shortlist of Code Entities whose names hold the question's words; if it is unsure, or picks something off the
shortlist, the answer is a refusal with `refusal_reason: "unresolved"`. A matched answer says so
(`anchor_matched: true`) and is at most Medium confidence. With `WHY_COMPOSER=template` there is no matching step:
such questions are refused. Rules: `src/whycode/answer/resolve.py` and the `_resolve` step of
`src/whycode/answer/engine.py`.

Departed people (inactive 12 months or more at the cutoff) carry `ask_instead`: the next-best active person, either
an active author or approver already in the answer, or the author or approver of the latest Change touching the
nearest enclosing area of the code, who is then listed with `via` naming that Change.

### The human view

One page per Answer for people (Decisions, Evidence Chain, superseded history, Person to Ask, refusal state), and
the same Answer as JSON for anything else. It renders on the server with no scripts or remote assets, so it works
offline against the fixture graph:

```sh
uv run whycode build                              # the fixture graph (recorded responses, no network)
WHY_COMPOSER=template uv run whycode serve        # serving http://127.0.0.1:8765/  (--port 0 picks a free port)
# open http://127.0.0.1:8765/?anchor=pkg/sql.isPermanentSchemaChangeError
curl 'http://127.0.0.1:8765/why?anchor=scbuild.Build'   # the Answer contract as JSON
```

Good demo Anchors on the fixture: `pkg/sql.isPermanentSchemaChangeError` (a revert and a refinement),
`sql.schemachanger.strict_planning_sanity_check.enabled` (departed people, with someone to ask instead),
`scrun.RunStatementPhase` (an RFC superseded by a later one), `scbuild.Build` (a refusal with the nearest evidence).

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
verbatim statement or justification, the chain to what holds now when the superseder was itself superseded
(`supersession_chain`), and whether history states it (explicit: reverts, RFC `Status:` headers,
"supersedes #N") or the judge inferred it (Opus 5.5 over pairs of Decisions governing the same code). Rules:
`src/whycode/supersession.py`; how answers use them: `src/whycode/answer/status.py` (the Live Decision rule) and
`src/whycode/answer/engine.py`.

### Graph schema notes

- Nodes: Change (PullRequest, Commit), Discussion (PullRequest, Issue, Rfc), Incident, Person, Decision, Code
  Entity (Package, File, Function, Setting), and Stub (referenced, never ingested, never cited).
- Stated edges: CONTAINS, TOUCHES, CLOSES, REFERENCES, REVERTS, AUTHORED, REVIEWED. Derived edges: YIELDS
  (Discussion -> Decision), GOVERNS (Decision -> Code Entity, hard or soft), SUPERSEDES / REFINES.
- SUPERSEDES / REFINES go from the later node to the earlier Decision and start at a Decision whenever one
  applies: a Decision of the superseding record that governs code the earlier Decision governs. A record starts
  the edge only when the superseding record yields no such Decision (a revert that records no Decision of its own,
  a successor whose Decisions are about other code), or when an RFC's `Status:` declares its own Decisions dead
  (obsolete, rejected, or superseded by something not ingested). `why` reports such a record as `superseded_by`,
  or None when it is the Decision's own record.

```sh
uv run whycode supersession-report --out eval/results/supersession-judge.md   # judge precision/recall vs explicit cases
```

It reads the built graph and asks the judge (default `--judge anthropic`, cached in `.cache/models`) about every
explicit Decision-to-Decision Supersession with the explicit statement masked, plus the candidate pairs around
those cases, then prints precision, recall and every disagreement for a human to check. On the real slice,
`whycode build --history github` judges inferred Supersession with Opus 5.5 (one cached call per candidate pair;
`--judge none` keeps explicit Supersession only). The judge's cost is bounded: each Decision is judged against its
5 nearest later Decisions (`--judge-max-later N`, 0 for no bound), and the build output's `inferred_supersession`
says how many pairs were judged and how many were not, by reason (past the bound, sharing only a containing file or
package, already linked explicitly, earlier Decision already superseded). Not run on real data yet: it needs the Anthropic key.

## `check_change` and Fence Warnings

`check_change(diff)` (MCP, next to `why`; or `git diff | uv run whycode check-change`) takes a unified diff and returns
the Code Entities it touches and a Fence Warning per Live Decision it reverses or may contradict: the Decision, its
verbatim quote, the Incidents it prevented and a confidence. No model is involved. `kind: reverses` means the diff
undoes lines that a Change implementing the Decision wrote, inside code the Decision governs; `kind: changes` means it
only edits a function or setting the Decision governs (one confidence level lower). Superseded Decisions never warn;
refined ones do, marked partly live. Editing a governed file outside its governed functions and settings is not
enough to warn. Rules: `src/whycode/answer/fence.py`; contract: `ChangeCheck` / `FenceWarning` in `contract.py`.
Proposed diffs against the fixture code are in `src/whycode/fixtures/miniature/proposed/`:

```sh
uv run whycode check-change src/whycode/fixtures/miniature/proposed/remove-retry-backoff.diff
```

## Agent comparison

`uv run whycode-agents run --repo <cockroach clone>` gives Claude Code each task in `eval/agent-comparison/tasks/`
on the cutoff commit, with and without the MCP tools, and writes the with/without table. The task records (2 real
post-cutoff Changes, 5 hand-built "remove this odd-looking check" tasks) are frozen; no real run has been made yet
(it needs Claude Code credentials and the real graph). See `eval/agent-comparison/README.md`.

## Tests

`uv run pytest tests` starts one disposable Neo4j container per session (Docker; with Colima the socket
override is set in `tests/conftest.py`), or uses `NEO4J_TEST_URI` / `NEO4J_TEST_PASSWORD` if set. Models are
always scripted in tests.

## Layout

| Module (`src/whycode/`) | Role |
|---|---|
| `history/` | History source seam (`HistorySource`), records, cutoff rules (`load_history`), fixture replay, GitHub REST payload mapping, RFC headers; the real slice: `scope.py`, `github.py` (cached transport, client, `GitHubHistorySource`), `checkout.py` |
| `codeindex/` | Code Entities, aliases, diff touches (each changed line in its enclosing function or setting registration) and exact name mentions; tree-sitter Go parser (same-package const setting keys, `WithName` aliases) |
| `audit.py` | The citation audit behind `whycode check-citations` |
| `linker.py` | Stated Links from written identifiers (closes, reverts, references) |
| `discussions.py`, `decisions.py` | Discussions as authored segments; Decision extraction behind the `DecisionProposer` seam, kept only with a verbatim quote |
| `build.py`, `graph/` | Graph building, the idempotent Neo4j store, and the export of citable records in the scoreboard's corpus format (`graph/corpus.py`) |
| `supersession.py` | Supersession detector: explicit parsing, candidate pairs, the judge seam (`SupersessionJudge`), the judge report |
| `answer/` | Fixed read-only query patterns (typed rows; all see history through a `HistoryView`), the Live Decision rule (`status.py`), composer seam, verifier, confidence scorer, `AnswerEngine`; `answer/fence.py` is `check_change` (diff parsing, Fence Warnings); `answer/systems.py` plugs it into the scoreboard |
| `answer/resolve.py` | The entity-matching step for free-form questions (`EntityMatcher` seam) and its shortlist words |
| `mcp_server.py`, `cli.py` | MCP server (`why-mcp`: `why`, `check_change`) and the `whycode` command |
| `view.py` | The human view behind `whycode serve`: `/why` (JSON) and one server-rendered page per Answer |
| `comparison/` | The agent comparison: task records and grading, the runner (git worktrees, Claude Code headless seam), report and demo transcript (`whycode-agents`) |
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
- **05 (`check_change`), done.** `FenceChecker(reader).check(diff, as_of, exclude)` returns a `ChangeCheck`
  (`contract.py`; `FenceWarning` gained optional fields). Pull requests' TOUCHES edges to files now carry `added` /
  `removed` (the lines their diff wrote there), which is how `reverses` is decided; `CodeIndex.changed_lines` maps
  each changed line to its enclosing function or setting registration (so `touched_by`, and hard GOVERNS links, no
  longer credit the function a hunk header names when the change is in the next one). `supersession_statuses` in
  `answer/status.py` is the shared Live Decision rule. The human view (`whycode serve`) does not show Fence
  Warnings yet.
  Agent comparison: `eval/agent-comparison/README.md`.
- **06 (demo polish), done.** Scoreboard: `llm-alone` baseline and `whycode-eval calibration` (`eval/README.md`).
  Answer contract additions (all optional): `Answer.anchor_matched`, `Answer.refusal_reason`,
  `PersonView.ask_instead`, `PersonView.via`. Every interface builds its engine with `Settings.answer_engine(reader)`
  (composer plus entity matcher from the environment), so a new tool gets the same Anchor resolution.
- **Scoreboard "ours" system, done.** `whycode.answer.systems:ours` and `:ours_without_supersession` (see
  `eval/README.md`). Build the graph through the end of the Held-out Window (`whycode build --cutoff <window end>`)
  and export the corpus from that graph; every pattern then filters by the query's `as_of` and `exclude` (record
  level, like the scoreboard's corpus). Our system reports the usage of every model call an answer took (entity
  matching, composing) for the cost column; a cached response reports what it cost to make.
