from hackfront.agent.harness import Harness
from hackfront.mcp_server import why

from .conftest import cid


def test_why_file_returns_direct_and_linked_evidence(graph):
    out = why(Harness(graph), "src/pay/gateway.py")
    ids = [e["id"] for e in out["evidence"]]
    assert out["refused"] is False
    assert ids[:2] == [cid("commit", "c2"), cid("commit", "c1")]  # direct hits first
    assert cid("pull_request", "pr1") in ids and cid("issue", "issue1") in ids  # one chain deep
    pr = next(e for e in out["evidence"] if e["id"] == cid("pull_request", "pr1"))
    assert pr["quote"].startswith("Fixes PAY-412 retry storm.") and len(pr["quote"]) <= 400
    assert pr["relation"].startswith(("CONTAINS", "REFERENCES")) and pr["url"]


def test_why_words_and_key(graph):
    assert why(Harness(graph), "PAY-412")["refused"] is False


def test_why_refuses_without_evidence(graph):
    out = why(Harness(graph), "no/such/file.py")
    assert out == {"anchor": "no/such/file.py", "refused": True, "evidence": [],
                   "note": out["note"]} and out["note"].startswith("Not established")


def test_why_respects_workspace_scopes(graph):
    assert why(Harness(graph, scopes=["other"]), "src/pay/gateway.py")["refused"] is True


def test_why_refuses_bad_input(graph):
    assert why(Harness(graph), "   ")["refused"] is True


def test_server_exposes_read_only_why_over_mcp(graph):
    import anyio
    from mcp import Client

    from hackfront.mcp_server import build_server

    async def run():
        async with Client(build_server(Harness(graph))) as client:
            tools = (await client.list_tools()).tools
            result = await client.call_tool("why", {"anchor": "src/pay/gateway.py"})
            return tools, result

    tools, result = anyio.run(run)
    assert [t.name for t in tools] == ["why", "memory"] and all(t.annotations.read_only_hint for t in tools)
    import json

    assert not result.is_error and json.loads(result.content[0].text)["refused"] is False


def test_lone_pr_number_finds_the_pr_itself_even_when_nothing_mentions_it(graph):
    rows = Harness(graph).call("find_text", "#pr1")  # no record contains the text "#pr1"; the PR with that native id is named
    assert rows and rows[0]["id"] == cid("pull_request", "pr1")


def test_memory_tool_over_mcp_resolves_a_file_through_the_graph_and_is_registered_once(graph, tmp_path, monkeypatch, caplog):
    """Regression: the workspace-bound `memory` tool was registered twice, the simple copy won, and a file anchor matched on words."""
    import json
    import logging

    import anyio
    from mcp import Client

    from hackfront import config, memory as m, state
    from hackfront.mcp_server import build_server

    monkeypatch.setattr(config, "HOME", tmp_path)
    config.create_workspace("alpha", slug="alpha")
    ev = [{"id": cid("pull_request", "pr1"), "kind": "pull_request", "title": "Cap retries", "quote": "We decided to cap retries at 3 instead of 10.",
           "url": "https://x/1", "time": None}]
    entry = m.edit(m.propose([], "#1", ev)["entry"], 1, "sr", body="Cap retries at 3.")
    state.backend().put_memory("alpha", entry["id"], m.move(entry, "approve", entry["version"], "sr"))
    other = [{"id": "unrelated", "kind": "issue", "title": "Gateway notes", "quote": "Never log gateway card numbers. Always mask.", "url": None, "time": None}]
    e2 = m.edit(m.propose([], "#2", other)["entry"], 1, "sr", body="Gateway: never log card numbers.")
    state.backend().put_memory("alpha", e2["id"], m.move(e2, "approve", e2["version"], "sr"))

    async def run():
        async with Client(build_server(Harness(graph), workspace="alpha")) as client:
            names = [t.name for t in (await client.list_tools()).tools]
            res = await client.call_tool("memory", {"anchor": "src/pay/gateway.py"})
            return names, json.loads(res.content[0].text)

    with caplog.at_level(logging.WARNING):
        names, out = anyio.run(run)
    assert names == ["why", "memory"] and "already exists" not in caplog.text
    assert [i["id"] for i in out["items"]] == [entry["id"]]  # matched on shared evidence, not on the word "gateway"
    assert out["items"][0]["matched_evidence"] == [cid("pull_request", "pr1")]
