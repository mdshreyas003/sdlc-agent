# Landing page: proposed changes with real data

Source for every number: `docs/story.md`. Screens: `docs/story-assets/` (copy to `web/public/story/`).
Done already: new slide "Real data" (08) with screenshots 03, 04, 05, 07. Nothing else was changed.

## Changes, most useful first

1. **Replace the drawn hero art with the real incident map.** Use `04-incident-cluster-after-stage1.jpg`. Caption: "A real map of one incident. 40 records, 69 links. Simulated store, real product."
2. **Add the stage 2 catch as a text card on "The moment".** Show the real memory-tool output (story.md, section 3): the three entries (a review rule, "Try a card payment at most 3 times", "Every payment carries a unique payment ID") with "shared evidence: 2 / 4 / 4". Copy: "A coding agent wants to raise 3 attempts to 8. The memory tells it what it would undo, and which review to ask for."
3. **Make "The moment" match the story.** The slide shows "Simplify commit retry / retryOnConflict(tx, 3)". The story's PR is "raise attempts from 3 to 8" in `src/payments/charge.py`, opened by `pr-agent` on 20 Apr. Use that diff and the 214-customers incident. Remove the "Illustrative example" label once it is real.
4. **Add the retired decision to the "Live or dead" card.** Use `06-retired-decision-replaced.jpg`. Copy: "“Try a failed payment up to 10 times” is retired. Its reason is stored. It points to its replacement."
5. **Show the overview as the first look at the product.** Use `01-overview.jpg` on "Where we sit" or "The flow". Copy: "3 entries wait for your review. 5 are live for agents."
6. **Add the sync timeline and ingestion screens** (`08-sync.jpg`, `09-ingestion.jpg`) to "The flow", if they are ready. They were not in `docs/story-assets/` when this was written. Copy: "Each update adds records. Nothing is imported again."
7. **Add the blame screen** (`10-blame.jpg`) to "The graph" slide, if ready (also missing when written). Copy: "Pick a line. See the ticket, talk and person behind it."
8. **Replace the drawn graph and triage diagrams with the real screens** (`07` for who decided, `05` for triage and staged update). Keep the drawings only as a legend.

## Claims I could not verify (left unchanged)

| Where | Claim | Problem |
|---|---|---|
| Where we sit | "₹1,999 / repo / month. Agents are never seats." | No price anywhere in README or story. |
| Where we sit | "One prevented repeat incident pays for years." | No evidence. |
| What is different / Hero | "Guards the PR. A warning before the merge. Never a block." | The story shows an agent asking the memory tool before it edits. No PR comment or merge check is shown. |
| The moment | PR "Simplify commit retry", incident and "Quote" text | Invented. Not in the story. See item 3. |
| Under the hood | "Never stores source files", "No endpoint returns code", "Models never trained on your data" | Not stated in README or story. Only "GitHub read-only" is close: README says the agent tools are read-only. |
| Under the hood | "GitHub: read-only" | README says the agent's tools are read-only, not the GitHub token scope. Check. |
| The graph | "The guard is one query: diff, function, live Decision, incident, person." | The story uses the file history plus approved entries that cite those records, not one query with a function node. |
| What is different | "Vector search finds text. Only the graph knows which decision won." | No comparison in the repo. |
| Who it is for / market diagrams | Competitor positions in `MarketDiagram` | No evidence in repo. |
