---
status: accepted
---

# Agent-first: coding agents are the primary user, not humans in a chat

"Chat over a repo" is what most entries will build, so we treat coding agents as the primary user. They reach the system through an MCP server with two tools: `why(anchor)` returns the Live Decisions that govern a Code Entity, and `check_change(diff)` returns Fence Warnings before an edit lands. A human chat UI is a secondary view over the same graph. The bet is that the strongest value is stopping an agent with no project history from quietly breaking a reason it never knew about, and that this is measurable: we run the same coding tasks with and without the tools.

## Considered Options

- **Chat-first Q&A for new developers.** This is closest to the brief's wording, but it can only win on answer quality, and it looks like every other demo.
- **PR bot that raises Fence Warnings on new pull requests.** Compelling, but it needs a live integration and is hard to evaluate in a hackathon. Kept as the "future growth" story.

## Consequences

- Outputs must be machine-consumable first: structured Decisions, node IDs for every citation, and an explicit refusal state.
- `check_change` makes Supersession detection and Fence Warnings P1 rather than polish, because the agent comparison depends on them.
