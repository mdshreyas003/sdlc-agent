"""Demo: what a coding agent sees when it asks our MCP server before editing src/payments/charge.py.

Starts `hackfront mcp --workspace brightcart` over stdio, lists the tools and calls `why` and `memory`.
Prints a short summary and writes the full JSON of every call to docs/story-assets/mcp-transcript.txt.
Config comes from the environment (NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE, HACKFRONT_HOME).

    uv run python scripts/mcp_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT = ROOT / "docs" / "story-assets" / "mcp-transcript.txt"
WORKSPACE = os.environ.get("DEMO_WORKSPACE", "brightcart")
PASS_ENV = ("PATH", "HOME", "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE", "HACKFRONT_HOME")
CALLS = [
    ("why", "src/payments/charge.py"),
    ("memory", "src/payments/charge.py"),
    ("memory", "#310"),
    ("memory", "SHOP-412"),
    ("memory", "payment"),
]


def summary(tool: str, answer: dict) -> list[str]:
    if tool == "why":
        lines = [f"  refused: {answer['refused']}, evidence items: {len(answer['evidence'])}"]
        lines += [f"  - {e['kind']:<18} {e['relation'].split(' ')[0]:<8} {e['title']}" for e in answer["evidence"]]
        return lines
    lines = [f"  approved notes: {len(answer['items'])}"]
    lines += [f"  - {i['kind']:<4} {i['title']}  (shared evidence: {len(i['matched_evidence'])})" for i in answer["items"]]
    if answer.get("note"):
        lines.append(f"  note: {answer['note']}")
    return lines


async def run() -> int:
    env = {k: os.environ[k] for k in PASS_ENV if k in os.environ}
    missing = [k for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "HACKFRONT_HOME") if k not in env]
    if missing:
        print(f"error: set {', '.join(missing)} first (see docs/mcp-demo.md)", file=sys.stderr)
        return 2
    args = ["run", "--directory", str(ROOT), "hackfront", "mcp", "--workspace", WORKSPACE]
    if os.environ.get("DEMO_SERVER_SCRIPT"):  # optional: run a different entry point instead of `hackfront mcp`
        args = ["run", "--directory", str(ROOT), "python", os.environ["DEMO_SERVER_SCRIPT"]]
    params = StdioServerParameters(command="uv", args=args, env=env)
    full: list[str] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            head = f"MCP server: hackfront mcp --workspace {WORKSPACE}\nTools: {', '.join(t.name for t in tools)}"
            print(head)
            full.append(head)
            for tool, anchor in CALLS:
                result = await session.call_tool(tool, {"anchor": anchor})
                if result.is_error:
                    raise RuntimeError(result.content[0].text if result.content else "tool error")
                answer = result.structured_content or json.loads(result.content[0].text)
                title = f'\n> {tool}("{anchor}")'
                print(title)
                print("\n".join(summary(tool, answer)))
                full.append(f"{title}\n{json.dumps(answer, indent=2)}")
    TRANSCRIPT.write_text("\n".join(full) + "\n")
    print(f"\nFull transcript: {TRANSCRIPT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(run))
