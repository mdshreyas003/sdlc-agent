"""Bundle path of the kafka-workspace migration: export without Neo4j, push over HTTP, same graph as `run`."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient

from hackfront.api import app
from hackfront.migrations import bundle
from hackfront.migrations import kafka_workspace as m
from tests.migrations.test_kafka_workspace import _all, _corpus, env  # noqa: F401  (fixture)

client = TestClient(app)
ADMIN = "adm-1f2e3d4c5b6a"


@pytest.fixture
def corpus_only(tmp_path, monkeypatch):
    from hackfront import config
    from hackfront.eval import corpus

    monkeypatch.setattr(config, "HOME", tmp_path)
    _corpus(tmp_path / "raw")
    monkeypatch.setattr(corpus, "RAW", tmp_path / "raw")
    return tmp_path


def test_export_needs_no_database_and_roundtrips(corpus_only, tmp_path):
    inv = tmp_path / "inv"
    inv.mkdir()
    (inv / "why-q-abc123.json").write_text(json.dumps({"investigation": {"id": "why-q-abc123"}, "graph": {}}))
    out = bundle.export(tmp_path / "b.json.gz", investigations=inv)
    assert out["distinct_artifacts"] == 6 and out["investigations"] == 1
    assert not (tmp_path / ".hackfront").exists()  # no workspace or sync status written locally
    doc = bundle.load(tmp_path / "b.json.gz")
    assert doc["workspace"]["slug"] == "kafka" and doc["workspace"]["config"]["docs"]["pages"] == ["KIP-7"]
    page = next(a for a in doc["artifacts"] if a["source"]["provider"] == "confluence")
    assert bundle.to_dict(bundle.from_dict(page)) == page
    assert any(r["origin"] == "text" for r in page["references"])  # links resolved at export time


def test_chunks_respect_size_and_end_with_finalize(corpus_only, tmp_path):
    bundle.export(tmp_path / "b.json.gz")
    doc = bundle.load(tmp_path / "b.json.gz")
    parts = list(bundle.chunks(doc, size=2, max_body=10_000))
    assert [p[0] for p in parts][-1] == "finalize"
    sent = [a for _, body in parts for a in json.loads(gzip.decompress(body))["artifacts"]]
    assert sent == doc["artifacts"] and all(len(b) <= 10_000 for _, b in parts)
    with pytest.raises(ValueError):
        list(bundle.chunks(doc, max_body=100))


def test_inflate_caps_decompressed_size(monkeypatch):
    monkeypatch.setattr(bundle, "MAX_INFLATED", 1000)
    with pytest.raises(ValueError, match="too large"):
        bundle.inflate(gzip.compress(json.dumps({"x": "a" * 5000}).encode()))
    assert bundle.inflate(gzip.compress(b'{"a": 1}')) == {"a": 1}


def test_endpoint_is_hidden_without_admin_token_and_guarded_with_it(monkeypatch):
    monkeypatch.delenv("HACKFRONT_ADMIN_TOKEN", raising=False)
    assert client.post(bundle.PATH, content=b"{}").status_code == 404
    monkeypatch.setenv("HACKFRONT_ADMIN_TOKEN", ADMIN)
    assert client.post(bundle.PATH, content=b"{}").status_code == 403
    assert client.post(bundle.PATH, content=b"{}", headers={bundle.ADMIN_HEADER: "nope"}).status_code == 403
    r = client.post(bundle.PATH, content=b'{"format": "x"}', headers={bundle.ADMIN_HEADER: ADMIN})
    assert r.status_code == 422 and ADMIN not in r.text
    wrong = {"format": bundle.FORMAT, "version": bundle.VERSION, "workspace": {"slug": "demo", "config": {}}}
    assert client.post(bundle.PATH, json=wrong, headers={bundle.ADMIN_HEADER: ADMIN}).status_code == 422
    monkeypatch.setenv("HACKFRONT_ACCESS_TOKEN", "acc-123")  # the global bearer check still applies first
    assert client.post(bundle.PATH, content=b"{}", headers={bundle.ADMIN_HEADER: ADMIN}).status_code == 401
    assert bundle.PATH not in client.get("/openapi.json", headers={"authorization": "Bearer acc-123"}).text


def test_push_over_http_matches_run_and_is_idempotent(env, tmp_path, monkeypatch):  # noqa: F811
    expected = m.run()
    graph = _all(env)
    env.execute_query("MATCH (n) DETACH DELETE n")
    bundle.export(tmp_path / "b.json.gz")
    monkeypatch.setenv("HACKFRONT_ADMIN_TOKEN", ADMIN)
    monkeypatch.setattr(bundle, "_post", lambda url, body, headers, timeout: (
        (r := client.post(bundle.PATH, content=body, headers=headers)).status_code, r.text))
    keys = ("artifacts", "edges", "stubs", "by_source", "edges_by_type", "tagged_artifacts", "tagged_edges")
    for _ in range(2):
        got = bundle.push(tmp_path / "b.json.gz", "http://test", ADMIN, size=2, log=lambda *_: None)
        assert {k: got[k] for k in keys} == {k: expected[k] for k in keys}
        assert _all(env) == graph
