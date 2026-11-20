"""MCP server: the primary interface for coding agents (ADR-0001).

Run with `uv run why-mcp` (stdio). Configuration: `whycode.config`. Tool results are the structured contracts
(`whycode.contract.Answer` for `why`, `whycode.contract.ChangeCheck` for `check_change`); a refusal is an answer
(`refused: true`), not an error. stdout is the JSON-RPC channel, so all logging goes to stderr.
"""

from __future__ import annotations

import logging
import sys

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from whycode.answer.engine import AnswerEngine
from whycode.answer.fence import FenceChecker
from whycode.contract import Answer, ChangeCheck

INSTRUCTIONS = (
    "Ask why CockroachDB SQL schema-change code is the way it is before you change it. `why` takes a "
    "function (pkg/sql.(*SchemaChanger).exec, SchemaChanger.exec), a file (pkg/sql/schema_changer.go), a "
    "package or a cluster setting (schemachanger.job.max_retry_backoff) and returns the Decisions that govern "
    "it, each with a verbatim quote, its Discussion, date, Incidents and the Person to Ask. Each Decision has a "
    "status: `superseded` Decisions are dead history (do not restore what they chose), `refined` ones still hold "
    "in part, and `superseded_by` / `superseded_at` say by what and when. `refused: true` means no recorded "
    "Decision reaches that code: treat it as unknown, not as permission. Before you finish a change, call "
    "`check_change` with your diff (`git diff` output): each Fence Warning names a Live Decision your diff "
    "reverses or may contradict, with its quote and the Incidents it prevented. Change course, or say in your "
    "summary why the override is justified."
)


def build_server(engine: AnswerEngine, checker: FenceChecker | None = None) -> MCPServer:
    """`checker` defaults to a `FenceChecker` over the engine's graph reader and Supersession setting."""
    server = MCPServer("why", instructions=INSTRUCTIONS)
    checker = checker or FenceChecker(engine.reader, supersession=engine.supersession)
    read_only = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    async def why(anchor: str) -> Answer:
        """Return the Decisions that govern a Code Entity (function, file, package or cluster setting), with
        an Evidence Chain of verbatim quotes and node ids, a High/Medium/Low confidence, the Person to Ask
        (departed people have active=false), linked Incidents, or a refusal with the nearest evidence.
        Superseded Decisions come back with status=superseded and what superseded them; never treat them as live.
        A free-form question is matched to one Code Entity (anchor_matched=true) or refused."""
        return await anyio.to_thread.run_sync(engine.why, anchor)

    @server.tool(annotations=read_only)
    async def check_change(diff: str) -> ChangeCheck:
        """Check a proposed change before you commit it. Pass a unified diff of your edits (`git diff` output,
        keep the hunk headers). Returns the Code Entities it touches and a Fence Warning for each Live Decision it
        reverses (`kind: reverses`: it undoes lines the Decision's implementing Change wrote) or may contradict
        (`kind: changes`: it edits a function or setting the Decision governs), with the Decision's verbatim
        quote, the Incidents it prevented and a confidence. Superseded Decisions never warn. No warnings means no
        recorded Decision governs what you touched, not that the change is safe."""
        return await anyio.to_thread.run_sync(checker.check, diff)

    return server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from whycode.answer.patterns import GraphReader
    from whycode.config import Settings

    settings = Settings.from_env()
    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    build_server(settings.answer_engine(reader)).run()


if __name__ == "__main__":
    main()
