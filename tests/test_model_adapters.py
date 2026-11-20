"""The production model adapters, driven through the real Anthropic SDK over a fake HTTP transport.

No network and no key: this checks the adapters turn schema-valid model responses into domain objects, cache them
for reproducible rebuilds, and degrade to "nothing proposed" on truncation instead of failing the build.
"""

from __future__ import annotations

import datetime as dt

from fake_anthropic import FakeApi, client_for

from whycode.answer.compose import AnthropicComposer, ComposeRequest
from whycode.answer.resolve import AnthropicEntityMatcher, EntityCandidate
from whycode.contract import Anchor
from whycode.decisions import AnthropicDecisionProposer
from whycode.discussions import Discussion, Segment
from whycode.llm import COMPOSER_MODEL, EXTRACTION_MODEL, MATCHER_MODEL

DISCUSSION = Discussion(
    id="pr:1", kind="pr", title="sql: add backoff", url="https://github.com/o/r/pull/1", date=dt.date(2023, 3, 20),
    authors=("fqazi",), segments=(Segment("body", "We chose capped exponential backoff over a fixed interval.",
                                          "fqazi", dt.date(2023, 3, 14)),),
)


CANDIDATE = {"choice": "Use capped exponential backoff", "rationale": "A fixed interval misbehaves.",
             "alternatives_rejected": ["fixed interval"],
             "quote": "We chose capped exponential backoff over a fixed interval."}


def test_the_extraction_adapter_returns_candidates_and_replays_them_from_its_cache(tmp_path):
    api = FakeApi({"decisions": [CANDIDATE]})
    proposer = AnthropicDecisionProposer(client_for(api, tmp_path), EXTRACTION_MODEL)

    first = proposer.propose(DISCUSSION)
    second = proposer.propose(DISCUSSION)

    assert [c.quote for c in first] == [CANDIDATE["quote"]]
    assert second == first
    assert len(api.requests) == 1  # the rebuild came from the cache


def test_a_truncated_extraction_proposes_nothing_instead_of_failing_the_build(tmp_path):
    api = FakeApi({"decisions": [CANDIDATE]}, stop_reason="max_tokens")

    assert AnthropicDecisionProposer(client_for(api, tmp_path), EXTRACTION_MODEL).propose(DISCUSSION) == []


def test_the_composer_adapter_returns_draft_sentences():
    api = FakeApi({"sentences": [{"text": "Backoff is capped.", "cites": [{"node_id": "pr:1", "quote": ""}]}]})
    request = ComposeRequest(anchor=Anchor(kind="setting", id="x"), decisions=[], evidence=[], people=[])

    drafts = AnthropicComposer(client_for(api), COMPOSER_MODEL).compose(request)

    assert [d.text for d in drafts] == ["Backoff is capped."]


def test_the_entity_matching_adapter_returns_its_pick_and_is_unsure_when_the_model_fails():
    candidates = [EntityCandidate(id="function:pkg/sql.(*SchemaChanger).exec", kind="function",
                                  key="pkg/sql.(*SchemaChanger).exec")]
    api = FakeApi({"entity_id": candidates[0].id, "sure": True, "reason": "It asks about the retry loop."})

    choice = AnthropicEntityMatcher(client_for(api), MATCHER_MODEL).match("Why the retry loop?", candidates)
    truncated = AnthropicEntityMatcher(client_for(FakeApi({"entity_id": None, "sure": False}, "max_tokens")),
                                       MATCHER_MODEL).match("Why the retry loop?", candidates)

    assert (choice.entity_id, choice.sure) == (candidates[0].id, True)
    assert (truncated.entity_id, truncated.sure) == (None, False)
