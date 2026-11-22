# 0001. Serve the evidence graph to coding agents over a read-only, workspace-scoped MCP server

Status: accepted (2026-11-22), amended for the HTTP endpoint. Covers `why`; `check_change` and Decision status are not built.

## Context

Coding agents edit code without knowing why it looks the way it does. The evidence graph (PRs, commits, Jira, chat)
holds that history. We expose it to agents as an MCP tool, `why(anchor)`, so an agent can ask before it edits.
The server hands history to a process we do not control, so the security decisions below come first.

## Decision

One tool, `why`, built on the agent's existing fixed Cypher harness (`src/hackfront/agent/harness.py`), served two ways:

- **stdio**, `hackfront mcp --workspace <ws>`: a local child process of the agent host. It needs the Neo4j login.
- **Streamable HTTP**, `https://<api>/mcp`, mounted on the deployed API (`mcp_http.py`). The agent sends only a
  per-workspace bearer token; the API holds the Neo4j login. This is the deployed way to connect.

A small client (`mcp_client.py`) spawns the stdio server for end-to-end checks.

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
5. **Network exposure is gated.** stdio opens no port. The HTTP endpoint answers only exactly `/mcp`, and only after a
   bearer token is checked (before any MCP handling); everything else under it is a 404.
6. **Per-workspace token.** `hfm_<workspace>.<random>`, 256 bits, shown once. Only its SHA-256 is stored, in the
   workspace's secrets record (compared in constant time). The workspace comes from the token, never from the request, so
   a token cannot reach another workspace. Issuing again rotates it; revoking stops it at once (up to 2 s when state
   is cached in Neo4j). Issue and revoke are behind the app's normal sign-in and access token
   (`POST|DELETE /api/w/{ws}/mcp-token`, or `hackfront mcp-token`).
7. **Redaction.** Titles and excerpts are masked for common credential shapes (GitHub, Slack, AWS, JWT, private keys,
   `Bearer ...`, `password=...`) in `redact.py`, so an excerpt is no longer strictly verbatim where it is masked.
8. **Audit log.** Each call logs one JSON line (workspace, anchor, refused, item count; never excerpts) to the app logs.
9. **Rate limit.** 60 calls a minute per workspace, in process (one instance).
10. **Safe inputs.** The anchor is validated by the harness (1 to 200 printable characters). Bad input is a refusal,
    not an error with internals.

### Known gaps (accepted for now)

- **stdio has no authentication.** Whoever can start the process with `NEO4J_*` set can read that workspace's graph.
  Prefer the HTTP endpoint for anything shared.
- **One token per workspace, no scopes, no expiry.** Anyone holding it reads that workspace's evidence until it is
  rotated. No per-user or per-agent tokens yet.
- **Redaction is pattern-based.** It will miss secrets that look like ordinary words, and personal data is not masked.
- **Evidence is untrusted text.** A PR or thread can contain instructions aimed at the agent (prompt injection).
  The server labels nothing as untrusted and does not filter. The agent host must treat results as data.
- **Audit log is not stored by us.** It lives in the host's logs and rotates with them. The rate limit is per process,
  and the endpoint needs a host that runs the app's startup (Render/container); a serverless host that skips it
  will not serve `/mcp`.
- **No Decision gate.** The planned "approved Decisions only" rule is not enforced because Decisions do not exist
  here yet.

## Consequences

- The HTTP endpoint meets the conditions this ADR first set for a network transport (token auth, redaction, audit log).
  The deployed API must run over HTTPS, since the token is a bearer credential.
- Adding `check_change(diff)` means the server receives code from the agent. It must analyse that diff without storing it or
  sending it to a model.
