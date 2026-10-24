"""Neo4j settings: missing ones are named in the error; NEO4J_DATABASE defaults to `neo4j`."""

import time

import pytest

from hackfront import config
from hackfront.ingest.storage.neo4j import Neo4jNotConfigured, Neo4jStore
from hackfront.ingest.storage.neo4j.writer import neo4j_database


@pytest.mark.parametrize("missing", [["NEO4J_USERNAME"], ["NEO4J_URI", "NEO4J_PASSWORD"]])
def test_missing_settings_are_named(monkeypatch, missing):
    for key in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
        monkeypatch.setenv(key, "x")
    for key in missing:
        monkeypatch.delenv(key)
    with pytest.raises(Neo4jNotConfigured) as caught:
        Neo4jStore.from_environment()
    assert str(caught.value) == f"Neo4j is not configured: set {', '.join(missing)} (see .env.example)"
    assert isinstance(caught.value, ValueError)  # callers that catch ValueError keep working


@pytest.mark.parametrize("value", [None, ""])
def test_database_defaults_to_neo4j(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("NEO4J_DATABASE", raising=False)
    else:
        monkeypatch.setenv("NEO4J_DATABASE", value)
    assert neo4j_database() == config.neo4j_database() == "neo4j"


def test_database_setting_is_used(monkeypatch):
    monkeypatch.setenv("NEO4J_DATABASE", "graph2")
    assert neo4j_database() == config.neo4j_database() == "graph2"


def test_failed_sync_status_names_the_missing_setting(tmp_path, monkeypatch):
    from hackfront.ingest import sync
    from hackfront.ingest.demo import DEMO_WORKSPACE

    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setenv("HACKFRONT_STATE", "file")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:1")
    monkeypatch.setenv("NEO4J_PASSWORD", "x")
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    config.create_workspace("Acme Demo", demo=True, slug="demo")
    config.save_workspace("demo", DEMO_WORKSPACE)
    sync.start_sync("demo", "standard")
    for _ in range(200):
        status = sync.sync_status("demo")
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status["error"] == "Sync failed: Neo4j is not configured: set NEO4J_USERNAME (see .env.example)"
