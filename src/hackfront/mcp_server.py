"""Minimal MCP server: `why(anchor)` over a workspace's evidence graph, for coding agents.

Run: `hackfront mcp --workspace kafka` (stdio). Read-only: it reuses the agent's fixed Cypher harness, scoped to the
workspace. No model is involved. Every item carries a verbatim excerpt (a prefix of the stored text) and its source URL;
with nothing to cite, the answer is refused ("Not established"). stdout is the JSON-RPC channel; log to stderr only.
"""

from __future__ import annotations

import logging
import re
import sys

from .agent.harness import Harness, HarnessError

SEEDS, MAX_EVIDENCE, QUOTE_LEN = 3, 12, 400
INSTRUCTIONS = (
    "Call `why` with a file path (src/pay/gateway.py), a ticket key (PAY-412), a PR number (#123) or a few words "
    "BEFORE you edit code, to learn why it looks the way it does. It returns the commits, PRs, tickets and threads "
    "that touched or discuss it, each with a verbatim excerpt and a link. `refused: true` means nothing in the "
    "history supports an answer: treat that as unknown, not as permission to simplify."
)
_PATHLIKE = re.compile(r"[/\\]|\.\w{1,6}$")


def _item(row: dict, relation: str) -> dict:
    return {"id": row["id"], "kind": row["kind"], "title": row.get("title"), "quote": (row.get("text") or "")[:QUOTE_LEN],
            "url": row.get("url"), "time": row.get("time"), "relation": relation}


def why(harness: Harness, anchor: str) -> dict:
    """Evidence for an anchor: a file path (file_history) or words/keys (find_text), expanded one chain deep."""
    anchor = (anchor or "").strip()
    try:
        tool = "file_history" if _PATHLIKE.search(anchor) else "find_text"
        hits = harness.call(tool, anchor)
        evidence = [_item(r, "direct") for r in hits]
        seen = {e["id"] for e in evidence}
        for seed in reversed(hits[-SEEDS:]):  # newest first
            for row in harness.call("evidence_chain", seed["id"]):
                if row["id"] not in seen and len(evidence) < MAX_EVIDENCE:
                    seen.add(row["id"])
                    via = row.get("via") or {}
                    evidence.append(_item(row, f"{via.get('rel', 'linked')} {seed['id']}"))
    except HarnessError as error:
        return {"anchor": anchor, "refused": True, "evidence": [], "note": f"Not established: {error}"}
    if not evidence:
        return {"anchor": anchor, "refused": True, "evidence": [],
                "note": "Not established: no commit, PR, ticket or thread in this workspace matches. Ask the team."}
    return {"anchor": anchor, "refused": False, "evidence": evidence, "note": None}


def recall(entries: list[dict], anchor: str) -> dict:
    """Approved memory only (ADRs, rules, episodes a human signed off). Drafts, staged revisions and rejects never leave."""
    from .memory import served

    items = served(entries, anchor)
    return {"anchor": anchor, "items": items, "note": None if items else "No approved memory matches. Use `why` for raw history."}


def build_server(harness: Harness, workspace: str | None = None):
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("why", instructions=INSTRUCTIONS)

    @server.tool(name="why", annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
    def why_tool(anchor: str) -> dict:
        """Why is this code the way it is? `anchor` is a file path, ticket key, PR number (#N) or a few words.
        Returns evidence (commits, PRs, tickets, threads) with verbatim quotes and links, or refused=true."""
        return why(harness, anchor)

    if workspace:
        from . import state

        @server.tool(name="memory", annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
        def memory_tool(anchor: str = "") -> dict:
            """Team-approved decisions (ADRs), rules and past incidents for this workspace, each citing its evidence ids.
            Read these before editing; they were reviewed by a senior developer. Empty `anchor` lists everything."""
            return recall(state.backend().list_memory(workspace), anchor)

    return server


def main(workspace: str) -> None:
    from . import config
    from .api.mapping import flat_scopes

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    harness = Harness(config.neo4j_driver(), scopes=flat_scopes(config.scopes(workspace)))
    build_server(harness, workspace).run()
