import pytest
from fastapi.testclient import TestClient

from hackfront import config, memory, state
from hackfront.api import app

client = TestClient(app)
EV = [{"id": "pr1", "kind": "pull_request", "title": "PR 1", "quote": "We decided to cap retries at 3 instead of unbounded backoff.", "url": "https://x/1", "time": None}]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    config.create_workspace("alpha", slug="alpha")
    config.save_workspace("alpha", {"name": "alpha", "github": {"owner": "", "repos": ["o/r"]}})
    entry = memory.propose([], "#1", EV)["entry"]
    state.backend().put_memory("alpha", entry["id"], entry)
    return entry


def test_review_flow_over_http(ws):
    base = f"/api/w/alpha/memory"
    listed = client.get(base).json()
    assert listed["counts"]["draft"] == 1
    mid = ws["id"]
    assert client.post(f"{base}/{mid}/approve", json={"version": 1}).status_code == 409  # TODO still in the body
    edited = client.put(f"{base}/{mid}", json={"version": 1, "body": "Cap retries at 3."})
    assert edited.status_code == 200 and edited.json()["version"] == 2
    assert client.put(f"{base}/{mid}", json={"version": 1, "title": "stale"}).status_code == 409  # lost update refused
    ok = client.post(f"{base}/{mid}/approve", json={"version": 2}).json()
    assert ok["status"] == "approved" and ok["served"]["approved_by"] == "local"
    assert client.get(f"{base}?status=approved").json()["items"][0]["id"] == mid


def test_unknown_workspace_and_entry(ws):
    assert client.get("/api/w/nope/memory").status_code == 404
    assert client.post("/api/w/alpha/memory/zzz/approve", json={"version": 1}).status_code == 404
    assert client.post(f"/api/w/alpha/memory/{ws['id']}/explode", json={"version": 1}).status_code == 422


def test_approver_is_the_signed_in_login_not_a_placeholder(ws):
    from hackfront import auth
    from hackfront.api import memory as api

    token = auth.set_current(auth.User(id="42", login="sr-dev", name="S R"))
    try:
        assert api._who() == "sr-dev"
    finally:
        auth.reset_current(token)


def test_concurrent_save_is_refused_not_silently_overwritten(ws, monkeypatch):
    """A second reviewer saves between this request's read and write: the write must lose with 409."""
    real = memory.edit

    def edit_after_rival_saved(entry, *a, **kw):
        rival = real(entry, entry["version"], "rival", title="rival title")
        state.backend().put_memory("alpha", entry["id"], rival)
        return real(entry, *a, **kw)

    monkeypatch.setattr(memory, "edit", edit_after_rival_saved)
    r = client.put(f"/api/w/alpha/memory/{ws['id']}", json={"version": 1, "body": "mine"})
    assert r.status_code == 409
    assert state.backend().list_memory("alpha")[0]["title"] == "rival title"


def test_shared_demo_memory_is_read_only_when_accounts_are_on(ws, monkeypatch):
    from fastapi import HTTPException

    from hackfront import auth
    from hackfront.api import memory as api

    monkeypatch.setattr(auth, "enabled", lambda: True)
    config.save_workspace("alpha", {**config.load_workspace("alpha"), "demo": True})  # demo, no owner = shared
    with pytest.raises(HTTPException) as shared:
        api._writable("alpha")
    assert shared.value.status_code == 403
    raw = state.backend().read_workspace("alpha")
    state.backend().write_workspace("alpha", {**raw, "owner": "42"})  # owned: the owner's boundary, writable
    api._writable("alpha")
