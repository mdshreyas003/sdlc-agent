"""The human view: a thin HTTP endpoint (`/why`, the Answer contract as JSON) and one page rendering it, served
offline over the fixture graph with the model-free template composer. Assertions are on what a browser receives."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import pytest

from whycode.answer.compose import TemplateComposer
from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.contract import Answer
from whycode.fixtures import fixture_graph
from whycode.graph.store import GraphStore
from whycode.view import make_server

EXEC = "pkg/sql.(*SchemaChanger).exec"
PERMANENT = "pkg/sql.isPermanentSchemaChangeError"
BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)
VALIDATION_QUOTE = (
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)


@pytest.fixture(scope="module")
def engine(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(fixture_graph())
    reader = GraphReader(neo4j_driver)
    reader.selfcheck()
    return AnswerEngine(reader, TemplateComposer())


@pytest.fixture(scope="module")
def base_url(engine):
    server = make_server(engine.why, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


class Page(HTMLParser):
    """What a reader sees (text, unescaped) and where the page links to."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.html, self.chunks, self.links, self.assets, self.tags = html, [], [], [], set()
        self.feed(html)
        self.text = " ".join("".join(self.chunks).split())

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        for key in ("src", "href"):
            if tag in ("script", "img", "link", "iframe", "object", "embed") and attrs.get(key):
                self.assets.append(attrs[key])

    def handle_data(self, data):
        self.chunks.append(data)


def get(base_url, path) -> tuple[int, str, str]:
    try:
        with urllib.request.urlopen(base_url + path, timeout=30) as response:
            return response.status, response.headers.get_content_type(), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get_content_type(), error.read().decode()


def page(base_url, anchor) -> Page:
    status, kind, body = get(base_url, "/?" + urllib.parse.urlencode({"anchor": anchor}))
    assert (status, kind) == (200, "text/html")
    return Page(body)


def test_the_endpoint_returns_the_answer_contract_as_json(base_url, engine):
    status, kind, body = get(base_url, "/why?" + urllib.parse.urlencode({"anchor": EXEC}))

    assert (status, kind) == (200, "application/json")
    assert Answer.model_validate_json(body) == engine.why(EXEC)


def test_the_page_shows_the_decision_its_evidence_chain_people_and_incidents(base_url, engine):
    answer = engine.why(EXEC)
    shown = page(base_url, EXEC)

    assert EXEC in shown.text and "High confidence" in shown.text
    backoff = next(d for d in answer.decisions if d.quote == BACKOFF_QUOTE)
    assert backoff.choice in shown.text and BACKOFF_QUOTE in shown.text and backoff.rationale in shown.text
    assert "2023-03-20" in shown.text and "hard link" in shown.text
    for item in answer.evidence_chain:  # every link of the Evidence Chain, with its source
        assert item.node_id in shown.text
        if item.url:
            assert item.url in shown.links
    for sentence in answer.sentences:
        assert sentence.text in shown.text
    assert {"@fqazi", "@rafiss"} <= set(shown.text.split())
    assert "issue:98001" in shown.text
    assert f"/why?{urllib.parse.urlencode({'anchor': EXEC})}" in shown.links  # the same answer as JSON


def test_superseded_history_is_shown_apart_from_what_is_live(base_url, engine):
    answer = engine.why(PERMANENT)
    reverted = next(d for d in answer.decisions if d.quote == VALIDATION_QUOTE)
    shown = page(base_url, PERMANENT)

    live, history = shown.text.split("Superseded history", 1)
    assert VALIDATION_QUOTE in history and VALIDATION_QUOTE not in live
    assert f"Superseded on 2023-05-10 by {reverted.superseded_by}" in history
    assert "stated in history" in history and reverted.supersession_quote in history
    assert "Partly live (refined)" in live and "inferred" in live


def test_a_departed_person_points_to_the_next_best_active_person(base_url):
    shown = page(base_url, "sql.schemachanger.strict_planning_sanity_check.enabled")

    assert "@postamar author, departed: ask @annrpom instead" in shown.text
    assert "@annrpom author of pr:122400, active in this area" in shown.text


def test_a_refusal_says_so_and_still_shows_the_nearest_evidence_and_person_to_ask(base_url):
    shown = page(base_url, "scbuild.Build")

    assert "Refused: no recorded Decision reaches this code" in shown.text
    assert "Nearest evidence" in shown.text and "pr:122400" in shown.text
    assert "@annrpom" in shown.text
    assert "Superseded history" not in shown.text


def test_an_anchor_that_names_no_code_entity_is_refused_clearly(base_url):
    shown = page(base_url, "pkg/sql/no_such_file.go")

    assert "Refused: no Code Entity matched" in shown.text
    assert "pkg/sql/no_such_file.go" in shown.text  # kept in the form, to edit and ask again


def test_the_page_works_offline_and_escapes_what_it_is_given(base_url):
    status, _, empty = get(base_url, "/")
    hostile = page(base_url, '<script>alert("x")</script>')
    full = page(base_url, EXEC)

    assert status == 200 and "<form" in empty
    assert "script" not in hostile.tags  # escaped, never executed; and the page needs no scripts at all
    assert '<script>alert("x")</script>' in hostile.text
    assert full.assets == [] and "script" not in full.tags  # styles inline, nothing fetched from anywhere
    assert get(base_url, "/nothing-here")[0] == 404


def test_whycode_serve_renders_the_fixture_graph_from_the_environment(engine, neo4j_uri_auth):
    """The one command a presenter runs, configured from the environment, offline composer."""
    uri, (user, password) = neo4j_uri_auth
    env = {**os.environ, "NEO4J_URI": uri, "NEO4J_USERNAME": user, "NEO4J_PASSWORD": password,
           "WHY_COMPOSER": "template"}
    proc = subprocess.Popen([sys.executable, "-m", "whycode.cli", "serve", "--port", "0"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        line = proc.stdout.readline()
        assert line.startswith("serving http://127.0.0.1:"), line
        url = line.split()[1].rstrip("/")
        status, _, body = get(url, "/why?" + urllib.parse.urlencode({"anchor": "schemachanger.job.max_retry_backoff"}))
        assert status == 200 and json.loads(body)["refused"] is False
    finally:
        proc.terminate()
        proc.wait(timeout=10)
