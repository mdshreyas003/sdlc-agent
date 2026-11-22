# 0002. Memory is proposed by code, approved by a person, and served read-only

Status: proposed (2026-11-22), prototype on `feat/memory-triage-adrs`. See [docs/memory.md](../memory.md).

## Context

Agents need the team's decisions, rules and past incidents, not only raw history. Generating them automatically risks
confident, wrong guidance reaching every coding agent. Senior developers need to control what becomes memory.

## Decision

1. Triage (deterministic, no model) drafts entries from `why` evidence; a person edits and approves in the dashboard.
2. Agents read the last approved snapshot only. Drafts, staged revisions and rejected entries are never served.
3. The MCP server stays read-only (ADR 0001). Writes exist only on the authenticated HTTP API, so an agent cannot propose or approve.
4. Approve needs cited evidence and a current version number; reject needs a reason and suppresses re-proposals.
5. Memory is stored outside `:Artifact`, so evidence queries cannot return it and it is never cited as evidence.

## Consequences

- A rejected or unreviewed proposal costs nothing; a wrong approved one is the reviewer's responsibility and is attributable (`by`).
- Keyword triage will misclassify; the reviewer can re-kind or reject. A model drafter can replace `draft_body` later.
- Approved text can quote secrets from sources, as in ADR 0001: no redaction yet.
