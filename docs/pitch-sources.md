> The deck is now 10 slides: title, the problem, who buys, where we sit, architecture and design choices, a real use case end to end, the data as a connected map, evolution stage by stage, how triage decides, built / next / proof. The data slides use numbers measured on the live story graph after stage 4 (92 records, 206 links) and the clean stage-by-stage replay (82/182, 87/191, 89/195, 92/206). Rows below for removed slides no longer apply.

# Brightcart pitch deck: sources

Deck: `docs/Brightcart-Pitch.pptx` (14 slides, speaker notes on every slide). Every number and claim below was checked against the file named.

| Slide | Claim in the deck | Source |
|---|---|---|
| 1 | "Your team forgets why. Your agents never knew." | `web/components/Landing.tsx` (hero) |
| 1 | "We catch the change that undoes a decision. We show the quote." | Landing.tsx hero text (reworded) |
| 2 | `MAX_PAYMENT_ATTEMPTS = 3`; the reason hides in pull requests, tickets, team chat | `docs/story-assets/10-blame.jpg`; `docs/story.md` (idea paragraph); `README.md` (problem) |
| 3 | Four users: tech leads (approve, own the gate), coding agents (Claude Code, Cursor and other MCP tools), new engineers, IT services firms | `web/components/StageDiagrams.tsx` `WhoDiagram` |
| 3 | Pain: "An agent simplifies code and re-opens a past outage" | Landing.tsx market slide |
| 3 | Price: 1,999 rupees per repo per month; agents are never seats | Landing.tsx market slide (price claim as written there; not validated elsewhere) |
| 4 | Brightcart is simulated | `docs/story.md` |
| 4 | 214 customers charged twice; limit of 3; old limit 10 | `docs/story.md` timeline, 2 Mar 2026 |
| 5 | Sources, connected map, agent with read-only tools, quote check, workbench; memory to MCP to coding agents | `docs/architecture.md`; `README.md` diagram; `docs/memory.md` (Agents) |
| 5 | Agents can read notes, never write | `docs/memory.md` (MCP has no write path) |
| 6 | Sync logged per run; ingestion page; The GitHub client only reads (GET requests only, `src/hackfront/ingest/sources/github/client.py`); sync keeps commit diffs for line blame | screenshots 08, 09; the client code, not the landing chips |
| 7 | Quote "Try a card payment at most 3 times instead of 10 ... SHOP-412: repeated attempts charged customers twice" | `docs/story-assets/mcp-transcript.txt` (commit fceb89d) |
| 7 | "Not established" when no quote; max order $2,000 thread is unanswered | `docs/story.md` (Bloom table, `unanswered`); `docs/architecture.md` |
| 8 | Draft, approved, staged, retired; person approves; agents read approved only | `docs/memory.md`; `docs/story.md` lifecycle |
| 9 | Three-line guard output | `docs/story.md` section 3 (copied exactly) |
| 9 | Agent PR "raise attempts from 3 to 8" | `docs/story.md` timeline, 20 Apr |
| 10 | 36 records to 40 records | `docs/story.md` section 2 (36 nodes, 63 links to 40 nodes, 69 links) |
| 10 | Ticket edited, entries flagged "source changed" | `docs/story.md` section 5; `docs/memory.md` |
| 11 | Loop: agents write, we guard and remember, memory feeds the next agent; reviewing keeps memory fresh | Landing.tsx flow slide; `docs/story.md` |
| 12 | Plain vector search finds text, cannot tell which decision won | Landing.tsx ("Vector search finds text. Only the graph knows which decision won.") |
| 12 | Hand-written notes go stale | Landing.tsx market diagram ("Skill file: hand-written, rots") |
| 12 | Connected map follows links people wrote; quotes checked in code; knows what still stands | `README.md`, `docs/architecture.md`, Landing.tsx |
| 13 | Kafka demo 1,201 items, 2,194 links | `README.md` figures table |
| 13 | Fully reachable questions 1 of 18 to 9 of 18, no model | `README.md` figures table |
| 13 | Real-model first check 5 of 7 | `README.md` figures table |
| 13 | 75 gold questions, none human-checked, no accuracy number | `README.md` figures table; `data/EVAL_PLAN.md` |
| 13 | 367 tests pass | Run on this branch: `uv run pytest -q` gave 367 passed, 6 skipped |
| 14 | Failure modes: no signal drafts nothing, same PR twice no duplicate, concurrent edit refused (409), source edit flagged, wrong kind re-kinded or rejected | `docs/memory.md` edge cases; `docs/story.md` |
| 14 | Next: model-assisted drafting, decision status on answers, change check on the diff, human-checked benchmark | `docs/memory.md` Not built; `README.md` MCP section and eval notes |

## Claims I could not verify (left out of the deck)

- Anything about an "LLM wiki". No file in the repo describes or tests one. Slide 12 says so openly and uses "hand-written notes" (the Landing "skill file") instead.
- Market size or revenue. None exists in the repo; none used.
- The brief said 366 tests. The run on this branch gave 367 passed (6 skipped). The deck uses 367. Re-check before presenting if code changes.
- Time saved ("hours down to minutes") is a goal in `video/script.md`, not measured. Not used.
- The 1,999 rupee price appears only in Landing.tsx. It is used because the brief allowed it, but no pricing doc backs it.
- Mem0 / Zep / GraphRAG comparison claims from the older deck were not reused.
