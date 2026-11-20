# 02: Real CockroachDB slice

**What to build:** `why` answers questions about real Code Entities in CockroachDB's SQL schema-change area. Ingest (cached, from one command) pulls in the schema-related RFCs, the merged PRs that touch the schema-changer code (description, review comments, files, approvers), and the issues they link to plus the `A-schema-*` issues, all up to 2024-06-30. The code index parses the scoped Go packages and cluster settings at the cutoff commit. The scope is fixed by ADR-0002.

**Blocked by:** 01

**Status:** ready-for-human

- [ ] One command ingests the slice. A re-run reads from the local cache and makes no GitHub calls.
- [ ] Nothing dated after 2024-06-30 is in the graph.
- [ ] Graph counts (Decisions, Changes, Discussions, Code Entities, Incidents, People) are printed and recorded for the pitch.
- [ ] From Claude Code, `why` returns a full Evidence Chain for at least 3 real Anchors (a function, a file, a cluster setting), and a refusal for at least 1 Anchor with no governing Decision.
- [ ] Every cited node ID resolves (checked automatically over a sample of 20 answers).

**Prerequisites (human):** AuraDB credentials, a GitHub token and an Anthropic API key, provided as environment variables.

## Comments

2026-11-20: Agent work merged into `main`. Tested only on the fixture history with scripted models. Left for a human: the full GitHub backfill (`whycode fetch`, about 2 hours), Decision extraction with a real model, final graph counts, and the 3-real-Anchors-plus-1-refusal check from Claude Code.
