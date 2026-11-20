# Agent comparison (ticket 05)

A coding agent gets a task on the pre-cutoff CockroachDB code twice: once with our MCP tools (`why`, `check_change`)
and once without. We count how often each arm repeats the real pitfall, and how often a Fence Warning changed the
agent's course. Code: `src/whycode/comparison/`. Tests (scripted agent, fixture graph): `tests/test_agent_comparison.py`.

**Status.** The 7 task records were written and frozen (`tasks/lock.json`) on 2026-11-20, before any run. No real
run has been made: it needs Claude Code credentials, a full CockroachDB clone and the real graph with Decisions (an
Anthropic key for extraction). The with/without table and the demo transcript come from that run; until then they
are **unmet: needs credentials**.

## Tasks

| Task | Origin | The Change behind it | Pitfall | Graded by |
|---|---|---|---|---|
| `R1-dsc-trivial-alter-column-type` | real | #127151 (merged 2024-07-17), task text from #126143 | DROP DATABASE became quadratic (#127747, fixed by #127755) | human (rule and benchmark in the record) |
| `R2-dsc-validate-alter-column-type` | real | #127823 (merged 2024-08-02) | reducing a DECIMAL's scale fails validation instead of rounding (#134711, fixed by #135087) | human (rule and repro in the record) |
| `H1-clock-errors-permanent` | hand-built | #63671 (2021) | clock sync errors fail schema changes permanently (#63636) | diff checks |
| `H2-drop-sql-retryable-check` | hand-built | #36495 (2019) | `result is ambiguous` fails a 7-day index build (#36489) | diff checks |
| `H3-oom-errors-permanent` | hand-built | #120806 (2024) | transient memory exhaustion reverts schema changes (#120807) | diff checks |
| `H4-backfill-gc-threshold-permanent` | hand-built | #30648 (2018) | long index builds roll back when they outlive the GC TTL (#29192) | diff checks |
| `H5-unknown-errors-retry` | hand-built | #24464 / #25015 (2018) | schema changes that can never succeed retry forever (#24748) | diff checks, human if restructured |

Every record holds the task text (verbatim what the agent gets), the base commit (`d132535`, the cutoff commit the
graph's code index is built from), the real pitfall with the history that shows it, and the grading rule.
Mechanical rules are held to example diffs (`tasks/examples/`) by the tests. `whycode-agents` refuses a record that
changed after it was frozen, and every run record carries the record's hash.

### How the tasks were chosen

Real tasks had to be post-cutoff Changes in the scope (ADR-0002) that were later reverted or caused an Incident, with
a pitfall a diff can be graded on. Searched with `gh` (responses cached outside the repo):

- Revert-titled PRs merged into master in the Held-out Window (2024-07-01 to 2025-06-30): 80. In scope: only
  #135000, which reverts #133879 ("refactor subzone config elements") because "the test flakes seem noisy". Rejected:
  test flakiness cannot be graded from a diff.
- Incidents: the 11 `A-schema-*` issues labelled `regression`, `release-blocker`, `GA-blocker` or `branch-master`
  created in the window, and the window's commit history of `pkg/sql/schemachanger` (417 commits) and
  `pkg/sql/schema_changer.go` (22), searched for reverts, "introduced in/by", "regress" and "broke". Two window
  Changes caused an Incident a task can reproduce: #127151 (R1) and #127823 (R2). Not usable: bugs introduced
  before the cutoff (#128692, from #39332 in 2019), trigger support (#134630, #142370: the feature is far too big
  for one task), unknown causes (#133129, #130165), and the ALTER COLUMN TYPE version gate (#132523), which was right
  at the base commit (24.2 was still the development version then).

Fewer than about 8 qualified, so the rest are hand-built "remove this odd-looking check" tasks: each asks for a
plausible simplification of `IsPermanentSchemaChangeError` (pkg/sql/schema_changer.go at the cutoff commit) that
removes or inverts a check a pre-cutoff Change added after an Incident. The Changes were found in the file's
history before the cutoff (583 commits), so the graph built at the cutoff can hold their Decisions.

## Running it

```sh
git clone https://github.com/cockroachdb/cockroach ~/src/cockroach   # a full clone holding the base commit
uv run whycode build --history github          # the real graph at the cutoff, with Decisions (ANTHROPIC_API_KEY)
export NEO4J_URI=... NEO4J_PASSWORD=...          # the with arm starts why-mcp over that graph
export ANTHROPIC_API_KEY=...                     # why composes with Opus 5.5 (or WHY_COMPOSER=template)

uv run whycode-agents run --dry-run                                               # what would run; spends nothing
uv run whycode-agents run --task H1-clock-errors-permanent --repo ~/src/cockroach  # one task, both arms
uv run whycode-agents run --repo ~/src/cockroach [--model claude-opus-5-5]         # every task, both arms
```

Each run creates `results/<time>-claude-code/` with `manifest.json`, `runs.jsonl`, `diffs/`, `transcripts/` and
`table.md`. Then:

1. Grade the runs the rules leave open (R1, R2, restructured H5) in `results/<run>/grades.yaml`
   (`R1-dsc-trivial-alter-column-type: {with: false, without: true}`; true means the pitfall was repeated) and run
   `uv run whycode-agents report --run results/<run>`.
2. Pick the demo transcript: `uv run whycode-agents demo --run results/<run> --task <id>` writes
   `demo-<id>-with.md`. Commit the run directory.

What the runner does: a fresh `git worktree` of the clone at the base commit per task and arm; Claude Code headless
(`claude -p`, stream-json) with the same prompt in both arms; `--strict-mcp-config` with only the `why` server (with)
or none (without); tools limited to reading, editing and read-only git/grep (no web access, so the agent cannot look
up the real fix; no Go build). The final diff is everything changed against the base commit. A course change is a
`check_change` call that returned warnings on a diff repeating the pitfall, followed by a final diff that does not.

Caveats: the agent works on the cutoff commit, 18 days (R1) and 34 days (R2) before the real Changes merged; user-level
Claude Code settings (e.g. `~/.claude/CLAUDE.md`) apply to both arms alike; one run per task and arm is noisy, so
repeat runs (`run` again; each run is its own directory) before drawing conclusions.
