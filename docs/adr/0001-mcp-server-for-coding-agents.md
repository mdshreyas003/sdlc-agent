# 0001. Serve the evidence graph to coding agents over a read-only, workspace-scoped MCP server

Status: accepted (2026-11-22). Covers `why`; `check_change` and Decision status are not built.

## Context

Coding agents edit code without knowing why it looks the way it does. The evidence graph (PRs, commits, Jira, chat)
holds that history. We expose it to agents as an MCP tool, `why(anchor)`, so an agent can ask before it edits.
The server hands history to a process we do not control, so the security decisions below come first.

## Decision

`hackfront mcp --workspace <ws>` runs an MCP server over **stdio**. It has one tool, `why`, built on the agent's existing
fixed Cypher harness (`src/hackfront/agent/harness.py`). A small client (`mcp_client.py`) spawns it for end-to-end checks.

### Security properties

1. **Read-only.** All queries are fixed templates. Writes are refused statically (`WRITE_RE`), reads use read routing
   and a 10 s timeout, and the tool is annotated `readOnlyHint`. The model never writes Cypher; `cypher_query` is
   not exposed.
2. **Workspace isolation.** The server starts for one workspace and passes that workspace's scopes (repos, Jira
   projects, Slack channels) to every query. Artifacts outside them are never returned, and an empty scope list
   matches nothing.
3. **Minimal output.** A result holds the id, kind, title, a verbatim excerpt of at most 400 characters, source URL
   and time. It never returns full text, the `get` tool, raw payloads, or credentials. Stub records (referenced
   but never ingested) are never returned.
4. **Quote or refuse.** Excerpts are prefixes of stored text, not model output. With no evidence the tool returns
   `refused: true` ("Not established"); it never guesses. No model is involved, so no data goes to a model provider.
5. **No network listener.** stdio only: the server is a child process of the agent host, with no open port.
6. **Safe inputs.** The anchor is validated by the harness (1 to 200 printable characters). Bad input is a refusal,
   not an error with internals.

### Known gaps (accepted for now)

- **No authentication.** Whoever can start the process with `NEO4J_*` set can read that workspace's graph. The
  server inherits the host's Neo4j credentials, so a workspace's access control is the host's, not the server's.
- **Excerpts can hold secrets.** Tickets, threads and PR bodies may contain tokens or personal data, and the
  server returns them as written. No redaction yet.
- **Evidence is untrusted text.** A PR or thread can contain instructions aimed at the agent (prompt injection).
  The server labels nothing as untrusted and does not filter. The agent host must treat results as data.
- **No Decision gate.** The planned "approved Decisions only" rule is not enforced because Decisions do not exist
  here yet.
- **No audit log** of calls.

## Consequences

- Safe default for a local, single-user tool. Do not expose the process to other users or add an HTTP transport
  without adding auth (per-workspace bearer token), redaction and an audit log first.
- Adding `check_change(diff)` means the server receives code from the agent. It must analyse that diff without storing it or
  sending it to a model.
