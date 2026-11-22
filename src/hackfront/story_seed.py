"""Replay the Brightcart story's memory lifecycle on a synced `brightcart` workspace (docs/story.md).

Triage runs for real on the loaded graph, in the order the PRs arrived. The reviewer steps (edit, re-kind, approve, reject,
retire) are scripted with named reviewers so the dashboard shows every state: approved, staged (a later PR refined it),
draft (waiting), rejected (with a reason) and retired (superseded). Safe to run again: it resets the workspace's memory.
"""

from __future__ import annotations

from . import config, memory as m, state
from .agent.harness import Harness
from .api.mapping import flat_scopes
from .ingest.demo import story
from .mcp_server import why

BODIES = {
    "old": ("Try a failed payment up to 10 times",
            "## Context\nCustomers saw an error whenever the payment provider hiccuped (SHOP-101).\n\n## Decision\nTry a failed payment up to 10 times so fewer customers see an error.\n\n"
            "## Consequences\nNo limit and no unique payment ID: during a long outage the same customer can be charged many times."),
    "ttl": ("Customers are signed out after 15 idle minutes (compliance)",
            "## Context\nAn external security test (SHOP-377) rated 24 hour sign-ins high risk, for example on a shared computer.\n\n## Decision\n"
            "Customers are signed out after 15 minutes of inactivity. Customers who are actively shopping stay signed in (#201), so the limit only applies to idle time.\n\n"
            "## Consequences\nSupport saw customers lose their cart (SHOP-441). Reverting is not an option: this is a compliance requirement, not a preference."),
    "retry": ("Try a card payment at most 3 times",
              "## Context\nOn 2 March 2026 a payment-provider outage made us charge 214 customers two to six times for the same order (SHOP-412).\n\n## Decision\n"
              "Try a card payment at most 3 times, and give every payment a unique payment ID so the provider recognises a repeat and never charges twice (#218). "
              "We rejected a setting that lets teams raise the limit: checkout must finish within 8 seconds (SHOP-455), so more than 3 attempts would not help the customer anyway.\n\n"
              "## Consequences\nA few customers see 'payment failed' sooner and their order is retried later. Raising the limit needs new data and a reliability review."),
    "key": ("Every payment carries a unique payment ID",
            "## Rule\nEvery payment must carry a unique payment ID. Never try a payment again without the same ID; reuse it for every attempt of one order.\n\n"
            "## Applies to\npayments service: src/payments/charge.py, src/payments/api.py\n\n## Why\nWithout it, a repeat after an error charges the customer twice (SHOP-412, SHOP-430, #233)."),
    "pan": ("Never show full card numbers in our records",
            "## Rule\nFull card numbers must never appear in our records. Show only the last 4 digits.\n\n## Applies to\npayments service: src/payments/logging.py\n\n"
            "## Why\nSecurity review, enforced in #229."),
    "sre": ("Changes to payment attempts or checkout wait time need a reliability review",
            "## Rule\nAny change to how many times we try a payment, or how long checkout waits, must be reviewed by the reliability team and checked against the 8 second limit (SHOP-455).\n\n"
            "## Applies to\nsrc/payments/charge.py and src/checkout/ (the review is enforced by CODEOWNERS)\n\n"
            "## Why\nThe SHOP-415 review traced the SHOP-412 double charges to an unreviewed change to payment attempts (#240)."),
}


def run(slug: str = "brightcart", project: bool = True) -> dict:
    store = state.backend()
    store.clear_memory(slug)
    driver = config.neo4j_driver()
    harness = Harness(driver, scopes=flat_scopes(config.scopes(slug)))
    entries: dict[str, dict] = {}
    log: list[str] = []

    def put(e):
        entries[e["id"]] = e
        store.put_memory(slug, e["id"], e)
        return e

    def triage(anchor: str, who: str = "triage"):
        found = why(harness, anchor)
        out = m.propose(list(entries.values()), anchor, found["evidence"], who) if not found["refused"] else {"action": "nothing", "entry": None}
        if out["action"] in ("created", "refined"):
            put(out["entry"])
        log.append(f"triage {anchor:8} -> {out['action']:10} {(out['entry'] or {}).get('kind', '-')}")
        return out["entry"]

    def review(e, who, key=None, kind=None, approve=False):
        if key:
            title, body = BODIES[key]
            e = put(m.edit(e, e["version"], who, title=title, body=body, kind=kind))
        if approve:
            e = put(m.move(e, "approve", e["version"], who))
        return e

    # 1. the old decision from Nov 2025, approved at the time
    old = review(triage("SHOP-101"), "sam-r", "old", approve=True)
    # 2. compliance TTL: triage reads it as a Rule; the reviewer re-kinds it to a Decision
    ttl = review(triage("#190"), "mei-s", "ttl", kind="adr", approve=True)
    # 3. the incident and its decision; then the follow-up PR refines the decision while v1 stays live
    retry = review(triage("#218"), "daniel-p", "retry", approve=True)
    triage("SHOP-412")  # episode draft, waiting for a reviewer
    # 4. rules from the post-incident review
    review(triage("#233"), "daniel-p", "key", approve=True)
    review(triage("#229"), "mei-s", "pan", approve=True)
    review(triage("#240"), "daniel-p", "sre", approve=True)
    triage("#96")  # a rule left as an untouched draft: TODO markers keep Approve off
    triage("#247")  # next PR on the same decision: refined, staged, v1 still served
    # 5. support's request to revert the TTL is proposed, then rejected with a reason
    ask = triage("SHOP-441")
    if ask and ask["status"] == "draft":
        put(m.move(ask, "reject", ask["version"], "mei-s", "Compliance item SHOP-377: the 15 minute limit stays. Keeping active customers signed in (#201) is the agreed answer."))
    # 6. the incident killed the old decision: retire it and link the new one
    retry = entries[retry["id"]]
    old = put(m.move(entries[old["id"]], "retire", entries[old["id"]]["version"], "daniel-p", "Superseded by 'Try a card payment at most 3 times' (#218): repeated attempts charged customers twice (SHOP-412)."))
    assert retry.get("supersedes") == old["id"], "triage should have linked the new decision to the one it replaces"

    summary = {"entries": len(entries), "by_status": {}, "log": log}
    for e in entries.values():
        summary["by_status"][e["status"]] = summary["by_status"].get(e["status"], 0) + 1
    if project:
        from .memory_graph import project as to_graph

        summary["graph"] = to_graph(driver, config.neo4j_database(), slug, list(entries.values()), story.PEOPLE, story.USERS,
                                    flat_scopes(config.scopes(slug)))
    return summary


def advance(slug: str, stage: int, project: bool = True) -> dict:
    """After `hackfront story --stage N` loaded more of the story: do what a PR webhook and a reviewer's dashboard would do next.

    stage 3: a PR that resolves the ticket arrives and triage runs on it (it refines the live decision: staged).
    every stage >= 2: ask the memory tool what applies to the file the agent PR touches (the pre-edit guard).
    every stage >= 4: report which approved or open entries now cite sources that changed after they were written."""
    from .api.memory import _current
    from .mcp_server import recall

    store = state.backend()
    driver = config.neo4j_driver()
    scopes = flat_scopes(config.scopes(slug))
    harness = Harness(driver, scopes=scopes)
    entries = {e["id"]: e for e in store.list_memory(slug)}
    out: dict = {"stage": stage}
    if stage == 3:
        found = why(harness, "#310")
        res = m.propose(list(entries.values()), "#310", found["evidence"], "triage")
        if res["action"] in ("created", "refined"):
            store.put_memory(slug, res["entry"]["id"], res["entry"])
            entries[res["entry"]["id"]] = res["entry"]
        out["triage"] = {"anchor": "#310", "action": res["action"], "entry": (res["entry"] or {}).get("title"),
                         "status": (res["entry"] or {}).get("status"), "note": res.get("note")}
    if stage >= 2:
        ids = [e["id"] for e in why(harness, "src/payments/charge.py")["evidence"]]
        out["guard"] = [{"title": i["title"], "kind": i["kind"], "matched": len(i["matched_evidence"])}
                        for i in recall(list(entries.values()), "src/payments/charge.py", ids)["items"]]
    if stage >= 4:
        current = _current(store, slug, list(entries.values())) or {}
        out["drift"] = {e["title"]: [d["id"].split(":", 2)[-1] for d in m.drift(e, current)] for e in entries.values() if m.drift(e, current)}
    if project:
        from .memory_graph import project as to_graph

        out["graph"] = to_graph(driver, config.neo4j_database(), slug, list(entries.values()), story.PEOPLE, story.USERS, scopes)
    return out
