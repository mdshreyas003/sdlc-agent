"""MCP server: the primary interface for coding agents (ADR-0001).

Run with `uv run why-mcp` (stdio). Configuration: `whycode.config`. Tool results are the structured Answer
contract (`whycode.contract.Answer`); a refusal is an answer (`refused: true`), not an error.
stdout is the JSON-RPC channel, so all logging goes to stderr.
"""

from __future__ import annotations

import logging
import sys

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from whycode.answer.engine import AnswerEngine
from whycode.contract import Answer

INSTRUCTIONS = (
    "Ask why CockroachDB SQL schema-change code is the way it is before you change it. `why` takes a "
    "function (pkg/sql.(*SchemaChanger).exec, SchemaChanger.exec), a file (pkg/sql/schema_changer.go), a "
    "package or a cluster setting (schemachanger.job.max_retry_backoff) and returns the Decisions that govern "
    "it, each with a verbatim quote, its Discussion, date, Incidents and the Person to Ask. Each Decision has a "
    "status: `superseded` Decisions are dead history (do not restore what they chose), `refined` ones still hold "
    "in part, and `superseded_by` / `superseded_at` say by what and when. `refused: true` means no recorded "
    "Decision reaches that code: treat it as unknown, not as permission."
)


def build_server(engine: AnswerEngine) -> MCPServer:
    server = MCPServer("why", instructions=INSTRUCTIONS)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False))
    async def why(anchor: str) -> Answer:
        """Return the Decisions that govern a Code Entity (function, file, package or cluster setting), with
        an Evidence Chain of verbatim quotes and node ids, a High/Medium/Low confidence, the Person to Ask
        (departed people have active=false), linked Incidents, or a refusal with the nearest evidence.
        Superseded Decisions come back with status=superseded and what superseded them; never treat them as live.
        A free-form question works if it names exactly one Code Entity."""
        return await anyio.to_thread.run_sync(engine.why, anchor)

    return server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from whycode.answer.patterns import GraphReader
    from whycode.config import Settings

    settings = Settings.from_env()
    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    build_server(AnswerEngine(reader, settings.composer_impl())).run()


if __name__ == "__main__":
    main()
