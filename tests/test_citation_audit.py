"""The citation audit: every node id in a sample of `why` answers resolves to a real (non-stub) graph record."""

from __future__ import annotations

import pytest
from doubles import FABRICATED_ID, FaithfulComposer

from whycode.answer.engine import AnswerEngine
from whycode.answer.patterns import GraphReader
from whycode.audit import GraphResolver, audit_citations, sample_anchors
from whycode.contract import Anchor, Answer, EvidenceItem, Sentence
from whycode.fixtures import fixture_graph
from whycode.graph.store import GraphStore


@pytest.fixture(scope="module")
def fixture_driver(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(fixture_graph())
    return neo4j_driver


def test_every_node_id_in_a_sample_of_20_answers_resolves_to_a_graph_record(fixture_driver):
    engine = AnswerEngine(GraphReader(fixture_driver), FaithfulComposer())
    anchors = sample_anchors(fixture_driver, 20)

    audit = audit_citations(engine.why, anchors, GraphResolver(fixture_driver))

    assert audit.answers == 20 and len(set(anchors)) == 20
    assert audit.answered >= 10  # every governed Code Entity is in the sample, not only refusals
    assert audit.ids_checked > audit.answers
    assert audit.unresolved == [] and audit.ok


def test_an_answer_citing_a_node_the_graph_does_not_hold_fails_the_audit(fixture_driver):
    def fabricating_why(anchor: str) -> Answer:
        return Answer(anchor=Anchor(kind="file", id=anchor), refused=False, confidence="High",
                      evidence_chain=[EvidenceItem(node_id="pr:98100", kind="pr"),
                                      EvidenceItem(node_id=FABRICATED_ID, kind="pr")],
                      sentences=[Sentence(text="Made up.", cites=[FABRICATED_ID])])

    audit = audit_citations(fabricating_why, ["pkg/sql/schema_changer.go"], GraphResolver(fixture_driver))

    assert not audit.ok
    assert [(u.anchor, u.node_id) for u in audit.unresolved] == [("pkg/sql/schema_changer.go", FABRICATED_ID)]
