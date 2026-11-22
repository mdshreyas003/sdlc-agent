"""Seed a throwaway workspace `memo` with memory entries in every state, for demos. No Neo4j needed.

    HACKFRONT_HOME=/tmp/hf-demo uv run python data/tools/seed_memory_demo.py
    HACKFRONT_HOME=/tmp/hf-demo uv run hackfront serve      # then: cd web && npm run dev -> /w/memo/overview
"""

from hackfront import config, memory as m, state


def ev(i, kind, title, quote):
    return {"id": i, "kind": kind, "title": title, "quote": quote, "url": "https://example.com/" + i, "time": "2026-11-01"}


config.create_workspace("Memory Demo", slug="memo")
config.save_workspace("memo", {"name": "Memory Demo", "github": {"owner": "", "repos": ["acme/shop"]}})
store = state.backend()

adr = m.propose([], "#18720", [
    ev("pr18720", "pull_request", "Cap gateway retries at 3", "We decided to cap retries at 3 instead of unbounded backoff. It avoids a retry storm when the gateway degrades."),
    ev("t1", "discussion_thread", "Retry storm thread", "Rather than tune jitter we chose a hard cap because it is easy to reason about.")])["entry"]
adr = m.edit(adr, 1, "local", body="## Context\nUnbounded backoff caused a retry storm.\n\n## Decision\nCap gateway retries at 3.\n\n## Consequences\nSlow dependencies fail faster.")
adr = m.move(adr, "approve", adr["version"], "local")  # live ...
adr = m.propose([adr], "#18801", [  # ... and a later PR stages an update while v3 stays served
    ev("pr18720", "pull_request", "Cap gateway retries at 3", "We decided to cap retries at 3 instead of unbounded backoff."),
    ev("pr18801", "pull_request", "Retry cap for batch jobs", "We decided batch jobs also need a cap, rather than a separate policy.")])["entry"]
rule = m.propose([], "KAFKA-18654", [ev("jira1", "issue", "Idempotence default", "Producers must never enable idempotence without acks=all. Always verify the config.")])["entry"]
episode = m.propose([], "#9001", [ev("pr9001", "pull_request", "Revert deploy", "Root cause of the outage was a bad deploy; we reverted it and added a workaround.")])["entry"]
for e in (adr, rule, episode):
    store.put_memory("memo", e["id"], e)
print("seeded workspace memo:", [(e["kind"], e["status"]) for e in (adr, rule, episode)])
