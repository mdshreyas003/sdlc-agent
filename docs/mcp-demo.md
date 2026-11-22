# Demo: a coding agent asks before it edits

This demo shows a coding agent using our MCP server on the simulated Brightcart story. The agent asks the memory tool what applies to `src/payments/charge.py` before it changes it. Everything is simulated and runs on your machine.

## What was verified, and what was not

- **Verified:** the server starts over stdio for workspace `brightcart` and lists two tools, `why` and `memory`. The Python MCP client (`scripts/mcp_demo.py`) called both against a real Neo4j holding the story at stage 4. The excerpt below is real output.
- **Not run:** a real Claude Code session. The `claude` CLI is not installed on the machine where this was written, and a session needs a login. The Claude Code steps below are the exact commands for you to run in your own session. Treat them as untested.
- **Two server bugs were found while running it, and are fixed:** `hackfront mcp` crashed on its first call (the workspace was passed in the wrong position), and the `memory` tool was registered twice so the simpler copy won and never used the graph. Both are fixed in `src/hackfront/mcp_server.py`, with a test that calls the tool over real MCP (`test_memory_tool_over_mcp_resolves_a_file_through_the_graph_and_is_registered_once`). The output below is from the plain `hackfront mcp` command, with no workaround.

## Steps

1. Start Neo4j. Use a throwaway database, never one with real data.

   ```sh
   docker compose up -d
   ```

2. Set the environment. Use your own values.

   ```sh
   export NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=<password> NEO4J_DATABASE=neo4j
   export HACKFRONT_HOME=$PWD/.hackfront-demo
   ```

3. Load the story. It replays the simulated GitHub, Jira and Slack data and builds the memory.

   ```sh
   uv run hackfront story
   ```

4. Run the script. It starts the server, lists the tools and makes five calls.

   ```sh
   uv run python scripts/mcp_demo.py
   ```

   It prints a short summary and writes the full run to `docs/story-assets/mcp-transcript.txt`.

5. Register the server in Claude Code. Pick one way.

   - Command line:

     ```sh
     claude mcp add why -e NEO4J_URI=$NEO4J_URI -e NEO4J_USERNAME=$NEO4J_USERNAME -e NEO4J_PASSWORD=$NEO4J_PASSWORD \
       -e NEO4J_DATABASE=$NEO4J_DATABASE -e HACKFRONT_HOME=$HACKFRONT_HOME \
       -- uv run --directory /path/to/sdlc-agent hackfront mcp --workspace brightcart
     ```

   - Project file: copy `.mcp.json.example` to `.mcp.json` in the project you want to edit, then fill in the placeholders. Do not commit it, because it holds your password.

   Start `claude` and run `/mcp`. You should see `why` connected with two tools.

6. Paste this prompt:

   > Before you change src/payments/charge.py, ask the memory tool what applies. Then raise MAX_PAYMENT_ATTEMPTS from 3 to 8.

   For a one-shot run, pass the same text to `claude -p "..."`. You may need `--allowedTools "mcp__why__memory"`.

## What a good session looks like

1. The agent calls `memory("src/payments/charge.py")` before it opens the file.
2. It reads the approved notes: the decision to try a payment at most 3 times, the rule that every payment needs a unique payment ID, and the rule that changes to payment attempts need a reliability review.
3. It does not edit. It tells you the change undoes a decision made after 214 customers were charged twice, and it asks for a reliability review.
4. It may call `why` for the history behind the decision.

A bad session edits the constant straight away.

## Real output (Python MCP client, stage 4)

From `uv run python scripts/mcp_demo.py`. The full JSON, with quotes and links, is in `docs/story-assets/mcp-transcript.txt`.

```
MCP server: hackfront mcp --workspace brightcart
Tools: why, memory

> why("src/payments/charge.py")
  refused: False, evidence items: 12
  - pull_request       direct   Add card payments with automatic retries
  - git_commit         direct   Try a card payment at most 3 times instead of 10
  - pull_request       direct   Raise payment attempts from 3 to 8 to reduce failed checkouts
  - pull_request       direct   Retry failed payments later from a queue
  ...

> memory("src/payments/charge.py")
  approved notes: 3
  - rule Every payment carries a unique payment ID  (shared evidence: 4)
  - rule Changes to payment attempts or checkout wait time need a reliability review  (shared evidence: 2)
  - adr  Try a card payment at most 3 times  (shared evidence: 4)

> memory("#310")
  approved notes: 3
  - rule Every payment carries a unique payment ID  (shared evidence: 4)
  - rule Changes to payment attempts or checkout wait time need a reliability review  (shared evidence: 2)
  - adr  Try a card payment at most 3 times  (shared evidence: 5)
```

A file, ticket or PR anchor is looked up in the graph first, and only notes that share evidence with it come back. A plain-words anchor such as `payment` falls back to word matching, so it can return more notes.
