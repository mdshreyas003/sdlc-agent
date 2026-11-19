"""Seam 1: graph building. Fixture history + recorded extraction responses in, graph contents out."""

from __future__ import annotations

from whycode.fixtures import fixture_graph

BACKOFF_QUOTE = (
    "We chose a capped exponential backoff rather than a fixed retry interval because a fixed interval either "
    "retries too aggressively during long outages or too slowly after short ones."
)
VALIDATION_QUOTE = (
    "Descriptor validation errors cannot be fixed by retrying, so the schema changer should stop retrying and "
    "fail the job instead of spinning until the backoff cap."
)


def test_decisions_exist_only_when_their_quote_is_verbatim_in_their_source(empty_store):
    empty_store.replace(fixture_graph())
    graph = empty_store.snapshot()

    quotes = {d.props["quote"] for d in graph.labelled("Decision")}
    assert BACKOFF_QUOTE in quotes
    assert "We picked exponential backoff since fixed intervals are bad." not in quotes
    assert "Schema changes always run synchronously inside the issuing transaction." not in quotes

    # A real quote proposed for the wrong Discussion is rejected: only #101200 yields it.
    yielders = {e.source for e in graph.edges("YIELDS") if graph.nodes[e.target].props["quote"] == VALIDATION_QUOTE}
    assert yielders == {"github:cockroachdb/cockroach#101200"}
