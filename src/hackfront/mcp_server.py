"""Minimal MCP server: `why(anchor)` over a workspace's evidence graph, for coding agents.

Run: `hackfront mcp --workspace kafka` (stdio). Read-only: it reuses the agent's fixed Cypher harness, scoped to the
workspace. No model is involved. Every item carries a verbatim excerpt (a prefix of the stored text) and its source URL;
with nothing to cite, the answer is refused ("Not established"). stdout is the JSON-RPC channel; log to stderr only.
"""

from __future__ import annotations

import json
import logging
import re
import sys

from .agent.harness import Harness, HarnessError
from .redact import redact

log = logging.getLogger("hackfront.mcp")

SEEDS, MAX_EVIDENCE, QUOTE_LEN = 3, 12, 400
INSTRUCTIONS = (
    "Call `why` with a file path (src/pay/gateway.py), a ticket key (PAY-412), a PR number (#123) or a few words "
    "BEFORE you edit code, to learn why it looks the way it does. It returns the commits, PRs, tickets and threads "
    "that touched or discuss it, each with a verbatim excerpt and a link. `refused: true` means nothing in the "
    "history supports an answer: treat that as unknown, not as permission to simplify."
)
_PATHLIKE = re.compile(r"[/\\]|\.\w{1,6}$")


def _item(row: dict, relation: str) -> dict:
    return {"id": row["id"], "kind": row["kind"], "title": redact(row.get("title")),
            "quote": redact((row.get("text") or "")[:QUOTE_LEN]),
            "url": row.get("url"), "time": row.get("time"), "relation": relation}


def why(harness: Harness, anchor: str, workspace: str | None = None) -> dict:
    """Evidence for an anchor: a file path (file_history) or words/keys (find_text), expanded one chain deep.
    Excerpts are redacted for credentials; every call is audit-logged (workspace, anchor, outcome; never the excerpts)."""
    out = _why(harness, anchor)
    log.info(json.dumps({"event": "why", "workspace": workspace, "anchor": (anchor or "")[:200],
                         "refused": out["refused"], "items": len(out["evidence"])}))
    return out


def _why(harness: Harness, anchor: str) -> dict:
    anchor = (anchor or "").strip()
    try:
        tool = "file_history" if _PATHLIKE.search(anchor) else "find_text"
        hits = harness.call(tool, anchor)
        evidence = [_item(r, "direct") for r in hits]
        own = [r for r in hits if (re.fullmatch(r"#\d+", anchor) and r["id"].endswith(f":pull_request:{anchor[1:]}"))
               or (re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", anchor) and r["id"].endswith(f":issue:{anchor}"))]  # the record the anchor names
        for e in evidence:
            if any(e["id"] == r["id"] for r in own):
                e["relation"] = "anchor"
        evidence.sort(key=lambda e: e["relation"] != "anchor")
        seen = {e["id"] for e in evidence}
        for seed in own + list(reversed(hits[-SEEDS:])):  # the PR the anchor names first, then newest first
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


def recall(entries: list[dict], anchor: str, evidence_ids=()) -> dict:
    """Approved memory only (ADRs, rules, episodes a human signed off). Drafts, staged revisions and rejects never leave."""
    from .memory import served

    items = served(entries, anchor, evidence_ids)
    return {"anchor": anchor, "items": items, "note": None if items else "No approved memory matches. Use `why` for raw history."}


def build_server(harness: Harness | None = None, harness_for=None, workspace_for=None, workspace: str | None = None):
    """stdio: pass one `harness`. HTTP: pass `harness_for()` / `workspace_for()` resolving the caller's workspace. `workspace` names it for the stdio `memory` tool."""
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("why", instructions=INSTRUCTIONS)

    @server.tool(name="why", annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
    def why_tool(anchor: str) -> dict:
        """Why is this code the way it is? `anchor` is a file path, ticket key, PR number (#N) or a few words.
        Returns evidence (commits, PRs, tickets, threads) with verbatim quotes and links, or refused=true."""
        return why(harness_for() if harness_for else harness, anchor, workspace_for() if workspace_for else None)

    @server.tool(name="memory", annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
    def memory_tool(anchor: str = "") -> dict:
        """Team-approved decisions (ADRs), rules and past incidents for this workspace, each citing its evidence ids.
        Read these before editing; a senior developer reviewed them. Empty `anchor` lists everything."""
        from . import state

        ws = workspace_for() if workspace_for else workspace
        if not ws:
            return {"anchor": anchor, "items": [], "note": "No workspace is bound to this server."}
        ids = ()
        if _PATHLIKE.search(anchor) or re.fullmatch(r"#\d+|[A-Z][A-Z0-9]+-\d+", anchor.strip()):
            h = harness_for() if harness_for else harness  # resolve the file/ticket/PR through the evidence graph, then match
            if h is not None:
                ids = [e["id"] for e in why(h, anchor.strip(), ws if workspace_for else None).get("evidence", [])]
        return recall(state.backend().list_memory(ws), anchor, ids)

    return server


def main(workspace: str) -> None:
    from . import config
    from .api.mapping import flat_scopes

    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    harness = Harness(config.neo4j_driver(), scopes=flat_scopes(config.scopes(workspace)))
    build_server(harness, workspace=workspace).run()
