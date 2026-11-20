"""Shared test fixtures: one disposable Neo4j per test session (see notes: neo4j.md).

Set NEO4J_TEST_URI (and NEO4J_TEST_PASSWORD) to use an existing instance instead of Docker.
The container gets a random host port, so concurrent sessions in other worktrees never clash.
"""

from __future__ import annotations

import os

os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")

import pytest
from neo4j import GraphDatabase


@pytest.fixture(scope="session")
def neo4j_uri_auth():
    if uri := os.environ.get("NEO4J_TEST_URI"):
        yield uri, (os.environ.get("NEO4J_TEST_USER", "neo4j"), os.environ.get("NEO4J_TEST_PASSWORD", "testpassword"))
        return
    import docker
    from testcontainers.community.neo4j import Neo4jContainer

    try:
        docker.from_env().ping()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Docker is unavailable and NEO4J_TEST_URI is unset: {exc}")
    container = (
        Neo4jContainer(os.environ.get("TEST_NEO4J_IMAGE", "neo4j:5"), password="testpassword")
        .with_env("NEO4J_server_memory_heap_initial__size", "256m")
        .with_env("NEO4J_server_memory_heap_max__size", "256m")
        .with_env("NEO4J_server_memory_pagecache_size", "32m")
        .with_kwargs(mem_limit="768m")
    )
    with container:
        yield container.get_connection_url(), (container.username, container.password)


@pytest.fixture(scope="session")
def neo4j_driver(neo4j_uri_auth):
    uri, auth = neo4j_uri_auth
    with GraphDatabase.driver(uri, auth=auth, notifications_min_severity="OFF") as driver:
        driver.verify_connectivity()
        yield driver


@pytest.fixture
def empty_store(neo4j_driver):
    """A GraphStore over a wiped database."""
    from whycode.graph.store import GraphStore

    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    return GraphStore(neo4j_driver)


@pytest.fixture
def whycode_env(neo4j_uri_auth, neo4j_driver, monkeypatch):
    """The `whycode` command pointed at the test database (wiped), offline."""
    uri, (user, password) = neo4j_uri_auth
    for name, value in {"NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password}.items():
        monkeypatch.setenv(name, value)
    for name in ("WHY_EXTRACTOR", "WHY_CUTOFF"):
        monkeypatch.delenv(name, raising=False)
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
