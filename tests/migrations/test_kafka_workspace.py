"""Migration kafka-workspace: a tiny synthetic Kafka corpus (the real one is not in git) lands in the 'kafka'
workspace with every node and edge tagged, re-running adds nothing, and the eval workspace never sees KIP pages."""

import json

import pytest

from hackfront import config
from hackfront.eval import corpus
from hackfront.ingest import sync
from hackfront.migrations import kafka_workspace as m

PAGE = "confluence:cwiki.apache.org%2FKAFKA:page:KIP-7"
ISSUE = "jira:KAFKA:issue:KAFKA-70"


def _corpus(root):
    d = root / "KIP-7"
    d.mkdir(parents=True)
    who = {"name": "alice", "key": "alice", "displayName": "Alice"}
    (d / "hop0.bin").write_text(json.dumps({"id": "1", "key": "KAFKA-70", "self": "https://issues.apache.org/jira/rest/api/2/issue/1",
        "fields": {"summary": "Implement KIP-7", "description": "Design is in KIP-7.", "created": "2020-01-01T00:00:00.000+0000",
                   "updated": "2020-01-02T00:00:00.000+0000", "status": {"name": "Resolved"}, "reporter": who,
                   "comment": {"comments": [{"id": "11", "author": who, "body": "done", "created": "2020-01-02T00:00:00.000+0000"}]}}}))
    (d / "commit-abc1234.json").write_text(json.dumps({"sha": "abc1234" + "0" * 33, "html_url": "https://github.com/apache/kafka/commit/x",
        "commit": {"message": "KAFKA-70: implement KIP-7", "author": {"name": "Bob", "email": "b@x", "date": "2020-01-03T00:00:00Z"},
                   "committer": {"name": "Bob", "email": "b@x", "date": "2020-01-03T00:00:00Z"}},
        "author": {"login": "bob"}, "parents": [], "files": [], "stats": {}}))
    mails = [{"id": "m1", "subject": "[DISCUSS] KIP-7: Test", "from": "Alice <a@x>", "epoch": 1577836800, "body": "Please review KIP-7."},
             {"id": "m2", "subject": "Re: [DISCUSS] KIP-7: Test", "from": "Bob <b@x>", "epoch": 1577840400, "body": "+1, see KAFKA-70 (unlike KIP-999)"}]
    (d / "dev_thread.jsonl").write_text("\n".join(json.dumps(x) for x in mails))
    (d / "threads.json").write_text(json.dumps({"threads": [{"id": "m1", "messages": ["m1", "m2"]}]}))
    (d / "page.json").write_text(json.dumps({"id": "77", "title": "KIP-7: Test", "body": {"storage": {"value": "<p>JIRA: KAFKA-70</p>"}},
        "version": {"when": "2020-01-01T00:00:00.000Z", "number": 3, "by": {"username": "alice", "displayName": "Alice"}},
        "_links": {"base": "https://cwiki.apache.org/confluence", "webui": "/display/KAFKA/KIP-7"}}))


@pytest.fixture
def env(tmp_path, monkeypatch, clean_graph):
    from tests.conftest import TEST_AUTH, TEST_URI

    for k, v in (("NEO4J_URI", TEST_URI), ("NEO4J_USERNAME", TEST_AUTH[0]), ("NEO4J_PASSWORD", TEST_AUTH[1])):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HACKFRONT_STATE", raising=False)
    monkeypatch.setattr(config, "HOME", tmp_path)
    _corpus(tmp_path / "raw")
    monkeypatch.setattr(corpus, "RAW", tmp_path / "raw")
    sync._jobs.clear()
    yield clean_graph
    sync._jobs.clear()


def _all(driver):
    nodes = driver.execute_query("MATCH (n) RETURN count(n) AS n")[0][0]["n"]
    rels = driver.execute_query("MATCH ()-[r]->() RETURN count(r) AS n")[0][0]["n"]
    return nodes, rels


def test_everything_lands_in_kafka_workspace_and_rerun_is_idempotent(env):
    first = m.run()
    assert first["by_source"] == {"confluence:page": 1, "github:commit": 1, "jira:comment": 1, "jira:issue": 1,
                                  "slack:message": 1, "slack:thread": 1}
    assert first["kip_pages"] == 1 and first["artifacts"] == 6
    assert first["tagged_artifacts"] == first["artifacts"] and first["tagged_edges"] == first["edges"]
    assert {w["slug"] for w in config.list_workspaces()} == {"kafka"}
    edges = {(r["a"], r["b"]) for r in env.execute_query(
        "MATCH (a:Artifact)-[r:REFERENCES {origin: 'text'}]->(b:Artifact) RETURN a.canonical_id AS a, b.canonical_id AS b")[0]}
    assert (PAGE, ISSUE) in edges and (ISSUE, PAGE) in edges  # KAFKA-70 on the page; "KIP-7" in the issue
    assert sum(1 for a, b in edges if b == PAGE) >= 3  # issue, commit and mail all name KIP-7
    assert not env.execute_query("MATCH (s:Artifact {provider: 'confluence', is_stub: true}) RETURN s")[0]  # no KIP-999

    before = _all(env)
    second = m.run()
    assert _all(env) == before
    assert {k: v for k, v in second.items() if k != "synced"} == {k: v for k, v in first.items() if k != "synced"}
    assert env.execute_query("MATCH (m:HfMigration {id: 'kafka-workspace'}) RETURN m.runs AS n")[0][0]["n"] == 2


def test_eval_workspace_never_sees_kip_pages(env):
    from hackfront.api.mapping import flat_scopes

    m.run()
    config.create_workspace("Kafka Eval", demo=True, slug="eval")
    config.save_workspace("eval", corpus.workspace())
    scopes = flat_scopes(config.scopes("eval"))
    rows = env.execute_query("MATCH (a:Artifact) WHERE a.scope IN $s AND NOT coalesce(a.is_stub, false) "
                             "RETURN collect(a.provider) AS p", s=scopes)[0][0]["p"]
    assert len(rows) == 5 and "confluence" not in rows


def test_investigations_export_import_roundtrip(env, tmp_path):
    from hackfront.agent.investigation import list_all, save

    m.run()
    inv = {"id": "why-q-abc123", "question": "Why?", "created_at": "2026-10-24T00:00:00Z"}
    save(inv, {"nodes": [], "edges": []}, "kafka")
    assert m.export_investigations(tmp_path / "out") == 1
    assert m.import_investigations(tmp_path / "out") == 1 and m.import_investigations(tmp_path / "out") == 1
    assert [i["id"] for i in list_all("kafka")] == ["why-q-abc123"]
