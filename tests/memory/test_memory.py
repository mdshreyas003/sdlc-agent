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
