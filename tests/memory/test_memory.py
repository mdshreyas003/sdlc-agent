import pytest

from hackfront import memory as m
from hackfront.mcp_server import recall


def ev(i, text):
    return {"id": i, "kind": "pull_request", "title": i, "quote": text, "url": f"https://x/{i}", "time": "2026-01-01"}


ADR = [ev("pr1", "We decided to cap retries at 3 instead of unbounded backoff. It avoids a retry storm.")]


def test_triage_picks_kind_and_explains():
    assert m.triage(ADR)["kind"] == "adr"
    assert m.triage([ev("a", "You must never log card numbers. Always mask them.")])["kind"] == "rule"
    assert m.triage([ev("a", "Root cause of the outage: a bad deploy, reverted at 3am.")])["kind"] == "episode"


def test_triage_declines_noise():
    out = m.propose([], "#9", [ev("a", "bump deps and fix typo in the readme file")])
    assert out["action"] == "nothing" and out["entry"] is None


def test_propose_is_idempotent_and_refines_on_new_evidence():
    first = m.propose([], "#1", ADR)["entry"]
    assert first["status"] == "draft" and "TODO" in first["body"] and first["version"] == 1
    assert m.propose([first], "#1", ADR)["action"] == "unchanged"
    more = ADR + [ev("pr2", "Follow-up: decided retries also need jitter.")]
    out = m.propose([first], "#2", more)
    assert out["action"] == "refined" and out["entry"]["status"] == "staged"
    assert [e["id"] for e in out["entry"]["evidence"]] == ["pr1", "pr2"] and out["entry"]["version"] == 2


def test_approve_gates_and_serving():
    e = m.propose([], "#1", ADR)["entry"]
    with pytest.raises(m.Conflict, match="TODO"):
        m.move(e, "approve", 1, "sr")
    e = m.edit(e, 1, "sr", body="## Decision\nCap retries at 3.")
    assert m.served([e]) == []  # drafts are invisible to agents
    e = m.move(e, "approve", e["version"], "sr")
    assert e["status"] == "approved" and m.served([e], "retries")[0]["approved_by"] == "sr"
    assert recall([e], "nothing-like-this")["items"] == [] and recall([e], "")["items"]


def test_editing_approved_stages_new_version_while_old_stays_served():
    e = m.edit(m.propose([], "#1", ADR)["entry"], 1, "sr", body="Cap at 3.")
    e = m.move(e, "approve", e["version"], "sr")
    e2 = m.edit(e, e["version"], "sr", body="Cap at 5.")
    assert e2["status"] == "staged" and m.served([e2])[0]["body"] == "Cap at 3."
    e3 = m.move(e2, "approve", e2["version"], "sr")
    assert m.served([e3])[0]["body"] == "Cap at 5."


def test_stale_version_conflicts():
    e = m.propose([], "#1", ADR)["entry"]
    with pytest.raises(m.Conflict, match="Reload"):
        m.edit(e, 99, "sr", title="x")


def test_reject_needs_reason_then_suppresses_reproposal_until_reopened():
    e = m.propose([], "#1", ADR)["entry"]
    with pytest.raises(m.Conflict):
        m.move(e, "reject", 1, "sr")
    r = m.move(e, "reject", 1, "sr", "too trivial")
    assert m.propose([r], "#3", ADR)["action"] == "suppressed"
    assert m.move(r, "reopen", r["version"], "sr")["status"] == "draft"


def test_rejecting_or_retiring_rules():
    e = m.edit(m.propose([], "#1", ADR)["entry"], 1, "sr", body="Cap at 3.")
    e = m.move(e, "approve", e["version"], "sr")
    with pytest.raises(m.Conflict, match="Retire"):
        m.move(e, "reject", e["version"], "sr", "x")
    gone = m.move(e, "retire", e["version"], "sr", "superseded by ADR-7")
    assert gone["status"] == "retired" and m.served([gone]) == []


def test_live_entry_with_a_staged_update_can_still_be_retired():
    e = m.edit(m.propose([], "#1", ADR)["entry"], 1, "sr", body="Cap at 3.")
    e = m.move(e, "approve", e["version"], "sr")
    staged = m.edit(e, e["version"], "sr", body="Cap at 5.")
    assert staged["status"] == "staged" and m.served([staged])
    gone = m.move(staged, "retire", staged["version"], "sr", "superseded")
    assert gone["status"] == "retired" and m.served([gone]) == []


def test_a_source_that_says_it_replaces_a_decision_creates_a_linked_entry_not_a_refinement():
    old = m.edit(m.propose([], "#1", ADR)["entry"], 1, "sr", body="Retry 10 times.")
    old = m.move(old, "approve", old["version"], "sr")
    new_ev = [dict(ADR[0], relation="direct", quote="We decided to cap retries at 3 instead of 10. Replaces the older policy because it double-charged.")]
    out = m.propose([old], "#2", new_ev)
    assert out["action"] == "created" and out["entry"]["supersedes"] == old["id"]


def test_resolved_anchor_matches_on_evidence_not_on_words():
    a = m.move(m.edit(m.propose([], "#1", ADR)["entry"], 1, "sr", body="Payments retries cap."), "approve", 2, "sr")
    b_ev = [ev("other", "Never log card numbers. Always mask them.")]
    b = m.move(m.edit(m.propose([], "#2", b_ev)["entry"], 1, "sr", body="Payments card numbers masked."), "approve", 2, "sr")
    hits = m.served([a, b], "src/payments/charge.py", evidence_ids=["pr1"])
    assert [h["id"] for h in hits] == [a["id"]] and hits[0]["matched_evidence"] == ["pr1"]
    assert {h["id"] for h in m.served([a, b], "payments")} == {a["id"], b["id"]}  # free text still matches on words


def test_a_source_naming_the_entry_anchor_refines_it_even_without_shared_evidence():
    old = m.edit(m.propose([], "#218", ADR)["entry"], 1, "sr", body="Cap at 3.")
    old = m.move(old, "approve", old["version"], "sr")
    new = [dict(ev("pr310", "We decided to queue failed orders instead of adding attempts. Keeps the limit of 3 from #218 because it protects customers."),
                relation="anchor")]
    out = m.propose([old], "#310", new)
    assert out["action"] == "refined" and out["entry"]["id"] == old["id"] and out["entry"]["status"] == "staged"
