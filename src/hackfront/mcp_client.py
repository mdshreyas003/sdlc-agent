"""Minimal MCP client: spawn `hackfront mcp` over stdio and call `why`.

`hackfront mcp-client --workspace kafka "clients/src/main/java/.../Sender.java"` prints the evidence. The same
`call_why` is what an agent host would do; use it to check the server end to end.
"""

from __future__ import annotations

import json
import sys

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def call_why(anchor: str, workspace: str, command: str = sys.executable) -> dict:
    params = StdioServerParameters(command=command, args=["-m", "hackfront.cli", "mcp", "--workspace", workspace])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            if "why" not in tools:
                raise RuntimeError(f"server has no 'why' tool (tools: {tools})")
            result = await session.call_tool("why", {"anchor": anchor})
            if result.is_error:
                raise RuntimeError(result.content[0].text if result.content else "tool error")
            return result.structured_content or json.loads(result.content[0].text)


def main(anchor: str, workspace: str) -> int:
    try:
        answer = anyio.run(call_why, anchor, workspace)
    except Exception as error:  # noqa: BLE001 - a server that failed to start surfaces as an exception group
        print(f"error: could not call the MCP server ({type(error).__name__}); its stderr is above", file=sys.stderr)
        return 2
    print(json.dumps(answer, indent=2))
    return 1 if answer["refused"] else 0
