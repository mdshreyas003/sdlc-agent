# 01: `why` end to end on fixture history

**What to build:** A coding agent can call the `why` MCP tool with a function, file or cluster setting from a small hand-built miniature of CockroachDB history and get back the answer contract from `../spec.md`: Live Decisions, Evidence Chain, confidence, Person to Ask, or a refusal. This first path covers:
- the fixture history source
- Stated Links (identifiers in text, closes/fixes, contains)
- Decision extraction (Derived, kept only if its quote is verbatim)
- hard and soft governs links to Code Entities
- an idempotent graph
- fixed read-only query patterns
- composition
- the citation and quote verifier
- graph-based confidence

There is no Supersession yet: every Decision is treated as live. This ticket fixes the answer contract that later tickets build on. Port the verifier, the query-template safety checks and the text-reference extraction from `legacy/` as references. Do not port its sources, workspaces, providers or agent loop.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

- [ ] The fixture history contains at least: 2 RFCs with `Status:` headers, PRs with diffs and review comments, a "Fixes #N" issue labelled as a regression, a revert, and a cluster setting.
- [ ] Seam 1 tests (scripted model): Decisions exist only when their quote appears verbatim in the source. Hard and soft governs links hit the right Code Entities. All Derived nodes and edges are tagged `derived`. A re-run leaves node and edge counts unchanged. Nothing after the cutoff date is ingested.
- [ ] Seam 2 tests (scripted model):
  - A governed function, file and setting each return Decisions with quote, Discussion, Person to Ask and date.
  - An ungoverned Anchor returns a refusal with the nearest evidence.
  - A fabricated node ID or a quote that isn't verbatim never reaches the output, and confidence drops.
  - Departed people are flagged.
- [ ] `why` can be called from Claude Code through MCP against the fixture graph, using real models.
- [ ] The answer contract is written down where tickets 03–05 can import it.

## Comments

2026-11-20: Agent work merged into `main`. Tested only on the fixture history with scripted models. Left for a human: call `why` from Claude Code with real models (needs `ANTHROPIC_API_KEY` and Neo4j; steps in `README.md`).
