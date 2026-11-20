"""The `whycode` commands for the real slice, run against a fake GitHub and a local checkout: one command fetches
into the cache, a build from the cache makes no GitHub calls and prints the graph counts, and the citation
audit runs over a sample of 20 answers."""

from __future__ import annotations

import json
import subprocess

import pytest
from fake_github import miniature_checkout, miniature_github

from whycode.cli import main
from whycode.eval.corpus import MemoryCorpus
from whycode.graph.store import GraphStore
from whycode.history.checkout import ensure_checkout
from whycode.history.scope import SCHEMA_CHANGES

PITCH = {"Decisions", "Changes", "Discussions", "Code Entities", "Incidents", "People"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def env(tmp_path, monkeypatch, neo4j_uri_auth):
    upstream = miniature_checkout(tmp_path / "upstream")
    git(upstream, "init", "-q", "-b", "master")
    git(upstream, "add", "-A")
    git(upstream, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "cutoff")
    git(upstream, "config", "uploadpack.allowFilter", "true")
    git(upstream, "config", "uploadpack.allowAnySHA1InWant", "true")
    sha = git(upstream, "rev-parse", "HEAD")
    ensure_checkout(tmp_path / "checkout", upstream.as_uri(), sha, SCHEMA_CHANGES.checkout_paths)

    uri, (user, password) = neo4j_uri_auth
    for name, value in {
        "NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password, "NEO4J_DATABASE": "neo4j",
        "WHY_CHECKOUT": str(tmp_path / "checkout"), "WHY_CUTOFF_COMMIT": sha,
        "WHY_GITHUB_CACHE": str(tmp_path / "github-cache"), "WHY_CORPUS": str(tmp_path / "corpus.jsonl"),
        "GITHUB_TOKEN": "ghp_test", "WHY_COMPOSER": "template",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("WHY_EXTRACTOR", "WHY_CUTOFF", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_fetch_fills_the_cache_and_a_build_from_it_makes_no_github_calls(env, neo4j_driver, capsys):
    fake = miniature_github()
    assert main(["fetch"], github_transport=fake) == 0
    fetched = json.loads(capsys.readouterr().out)
    calls = len(fake.calls)
    assert fetched["github_calls"] == calls > 0
    assert fetched["pull_requests"] == 6 and fetched["rfcs"] == 3

    counts_file = env / "graph-counts.json"
    assert main(["build", "--history", "github", "--extractor", "none", "--counts-file", str(counts_file)],
                github_transport=fake) == 0
    built = json.loads(capsys.readouterr().out)
    assert len(fake.calls) == calls and built["github_calls"] == 0  # the re-run reads the cache

    assert set(built["counts"]) == PITCH
    assert built["counts"]["Decisions"] == 0  # no extractor
    assert built["counts"]["Incidents"] == 2  # #98001 and #101400, closed by ingested Changes
    assert built["latest_date"] <= "2024-06-30"
    assert json.loads(counts_file.read_text())["counts"] == built["counts"]
    graph = GraphStore(neo4j_driver).snapshot()
    assert "pr:98100" in graph.nodes and "pr:127200" not in graph.nodes
    corpus = MemoryCorpus.from_jsonl(env / "corpus.jsonl")
    assert corpus.get("pr:98100") and corpus.get("issue:98001") and corpus.get("rfc:20151014_online_schema_change")

    # Offline (no transport at all) the cache is enough.
    assert main(["build", "--history", "github", "--extractor", "none", "--offline",
                 "--counts-file", str(counts_file)]) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == built["counts"]


def test_a_held_out_window_build_ingests_window_history_while_the_code_index_stays_at_the_cutoff(
        env, neo4j_driver, capsys, monkeypatch):
    # Upstream moves on after the cutoff: a window commit adds a function to the scoped code.
    upstream = env / "upstream"
    cutoff_sha = git(upstream, "rev-parse", "HEAD")
    with (upstream / "pkg/sql/schema_changer.go").open("a") as f:
        f.write("\nfunc addedInTheWindow() {}\n")
    git(upstream, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-am", "window")
    window_sha = git(upstream, "rev-parse", "HEAD")
    fake = miniature_github()
    fake.heads = {cutoff_sha: "2024-06-29T21:36:20Z", window_sha: "2025-06-29T12:00:00Z"}
    monkeypatch.setenv("WHY_CUTOFF_COMMIT", cutoff_sha)
    build = ["build", "--history", "github", "--extractor", "none", "--cutoff", "2025-06-30",
             "--counts-file", str(env / "counts.json")]

    # Pull requests are found through the commit history, so a window build needs the window's last commit.
    assert main(build, github_transport=fake) == 2
    assert "--window-commit" in capsys.readouterr().err

    assert main([*build, "--window-commit", window_sha], github_transport=fake) == 0
    built = json.loads(capsys.readouterr().out)
    graph = GraphStore(neo4j_driver).snapshot()
    assert {"pr:127200", "pr:128000", "issue:127000"} <= set(graph.nodes)  # the window's history
    assert "function:pkg/sql.addedInTheWindow" not in graph.nodes  # the code index is still at the cutoff
    assert (built["cutoff_commit"], built["window_commit"]) == (cutoff_sha, window_sha)
    corpus = MemoryCorpus.from_jsonl(env / "corpus.jsonl")
    assert corpus.get("pr:127200").date.isoformat() == "2024-07-15"  # for the window questions


def test_check_citations_over_20_answers_on_the_fixture_graph(env, capsys):
    assert main(["build"]) == 0
    capsys.readouterr()

    assert main(["check-citations", "--sample", "20"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["answers"] == 20 and report["answered"] >= 10
    assert report["ok"] is True and report["unresolved"] == []
