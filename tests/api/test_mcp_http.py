"""The MCP endpoint on the API: bearer-token gate, workspace taken from the token, redaction, token lifecycle."""

import json

import pytest
from fastapi.testclient import TestClient

from hackfront import config, mcp_http, mcp_tokens
from hackfront.agent import llm
from hackfront.api import app
from hackfront.redact import redact

HEAD = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
ROW = {"id": "github:acme:pull_request:1", "kind": "pull_request", "title": "Cap retries", "url": "https://x/1",
       "time": "2024-02-02T00:00:00Z", "text": "Cap at 3 because of PAY-412. password=hunter2secret ghp_" + "a" * 30}


class FakeHarness:
    def __init__(self, slug):
        self.slug = slug

    def call(self, tool, arg):
        return [ROW] if tool in ("file_history", "find_text") else []


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(mcp_http, "_harness", lambda: FakeHarness(mcp_http._workspace.get()))
    mcp_http._hits.clear()


@pytest.fixture(scope="module")
def client():  # the MCP session manager can run once per process, so the app starts once per module
    with TestClient(app) as c:
        yield c


def make(client, name="Acme"):
    return client.post("/api/workspaces", json={"name": name}).json()["slug"]


def rpc(client, token, method, params=None, id_=1):
    headers = {**HEAD, **({"authorization": f"Bearer {token}"} if token else {})}
    return client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


def test_redact_masks_credentials_but_keeps_prose():
    text = "retry cap 3. token: abc123def456 and ghp_" + "b" * 30 + " AKIA" + "A" * 16
    out = redact(text)
    assert out.startswith("retry cap 3.") and "abc123def456" not in out and "ghp_" not in out and "AKIA" not in out
    assert redact(None) is None and redact("plain words") == "plain words"


def test_token_lifecycle(client):
    slug = make(client)
    token = mcp_tokens.issue(slug)
    assert mcp_tokens.verify(token) == slug
    assert "hfm_" not in json.dumps(config.state.backend().read_secrets(slug))  # only the hash is stored
    new = mcp_tokens.issue(slug)  # rotate
    assert mcp_tokens.verify(token) is None and mcp_tokens.verify(new) == slug
    assert mcp_tokens.revoke(slug) is True and mcp_tokens.verify(new) is None and mcp_tokens.revoke(slug) is False
    for bad in (None, "", "hfm_", "hfm_nope.x", f"hfm_{slug}.wrong", "x" * 500):
        assert mcp_tokens.verify(bad) is None
    with pytest.raises(LookupError):
        mcp_tokens.issue("ghost")


def test_token_api_issues_once_and_revokes(client):
    slug = make(client)
    body = client.post(f"/api/w/{slug}/mcp-token").json()
    assert body["token"].startswith(f"hfm_{slug}.") and body["url"].endswith("/mcp")
    page = json.dumps(client.get(f"/api/w/{slug}/workbench").json())
    assert body["token"] not in page and mcp_tokens.KEY not in page  # never read back through the workbench
    assert client.post("/api/w/ghost/mcp-token").status_code == 404
    assert client.delete(f"/api/w/{slug}/mcp-token").json() == {"ok": True, "revoked": True}
    assert mcp_tokens.verify(body["token"]) is None


def test_endpoint_requires_a_valid_token(client):
    slug = make(client)
    assert rpc(client, None, "tools/list").status_code == 401
    assert rpc(client, "hfm_acme.bogus", "tools/list").status_code == 401
    assert rpc(client, "hfm_acme.bogus", "tools/list").headers["www-authenticate"] == "Bearer"
    token = mcp_tokens.issue(slug)
    mcp_tokens.revoke(slug)
    assert rpc(client, token, "tools/list").status_code == 401  # revoked
    assert client.get("/nope").status_code == 404 and client.post("/mcp/extra", headers=HEAD).status_code == 404


def test_endpoint_serves_why_scoped_to_the_token_workspace(client):
    slug = make(client)
    token = mcp_tokens.issue(slug)
    init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}
    assert rpc(client, token, "initialize", init).status_code == 200
    tools = rpc(client, token, "tools/list").json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["why"]
    r = rpc(client, token, "tools/call", {"name": "why", "arguments": {"anchor": "src/pay/gateway.py"}})
    out = json.loads(r.json()["result"]["content"][0]["text"])
    assert out["refused"] is False and out["evidence"][0]["id"] == ROW["id"]
    quote = out["evidence"][0]["quote"]
    assert "PAY-412" in quote and "hunter2secret" not in quote and "ghp_" not in quote  # redacted


def test_rate_limit_per_workspace(client, monkeypatch):
    slug = make(client)
    token = mcp_tokens.issue(slug)
    monkeypatch.setattr(mcp_http, "LIMIT", 2)
    codes = [rpc(client, token, "tools/list").status_code for _ in range(3)]
    assert codes[-1] == 429 and 401 not in codes
