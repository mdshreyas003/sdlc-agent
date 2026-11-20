"""The model adapters over an OpenAI-compatible server (Sarvam, vLLM), driven through the real OpenAI SDK over a
fake HTTP transport. No network and no key."""

from __future__ import annotations

from fake_openai import FakeChat, ToolCalls, client_for, sdk_for
from pydantic import BaseModel
from test_model_adapters import CANDIDATE, DISCUSSION

from whycode.answer.compose import AnthropicComposer, ComposeRequest
from whycode.answer.resolve import AnthropicEntityMatcher, EntityCandidate
from whycode.contract import Anchor
from whycode.decisions import AnthropicDecisionProposer
from whycode.eval.models import OpenAIStructured, OpenAIToolLoop, Tool
from whycode.llm import metered
from whycode.supersession.judge import AnthropicSupersessionJudge, CandidatePair, DecisionSummary

MODEL = "sarvam-105b"


def test_the_extraction_adapter_returns_candidates_over_an_openai_compatible_server_and_replays_them(tmp_path):
    api = FakeChat({"decisions": [CANDIDATE]})
    proposer = AnthropicDecisionProposer(client_for(api, tmp_path), MODEL)

    with metered() as calls:
        first = proposer.propose(DISCUSSION)
    second = proposer.propose(DISCUSSION)

    assert [c.quote for c in first] == [CANDIDATE["quote"]]
    assert second == first
    assert len(api.requests) == 1  # the rebuild came from the cache
    request = api.requests[0]
    assert (request["model"], request["messages"][0]["role"]) == (MODEL, "system")
    assert request["response_format"]["type"] == "json_schema"
    assert [(c.model, c.input_tokens, c.output_tokens) for c in calls] == [(MODEL, 10, 5)]
    assert calls[0].cost_usd() is None  # no known price: the cost column says unknown


def test_a_truncated_extraction_proposes_nothing_instead_of_failing_the_build(tmp_path):
    api = FakeChat({"decisions": [CANDIDATE]}, finish_reason="length")

    assert AnthropicDecisionProposer(client_for(api, tmp_path), MODEL).propose(DISCUSSION) == []


def test_the_composer_and_entity_matching_adapters_work_over_an_openai_compatible_server():
    api = FakeChat({"sentences": [{"text": "Backoff is capped.", "cites": [{"node_id": "pr:1", "quote": ""}]}]})
    request = ComposeRequest(anchor=Anchor(kind="setting", id="x"), decisions=[], evidence=[], people=[])
    candidates = [EntityCandidate(id="function:pkg/sql.(*SchemaChanger).exec", kind="function",
                                  key="pkg/sql.(*SchemaChanger).exec")]
    pick = FakeChat({"entity_id": candidates[0].id, "sure": True, "reason": "It asks about the retry loop."})

    drafts = AnthropicComposer(client_for(api), MODEL).compose(request)
    choice = AnthropicEntityMatcher(client_for(pick), MODEL).match("Why the retry loop?", candidates)

    assert [d.text for d in drafts] == ["Backoff is capped."]
    assert (choice.entity_id, choice.sure) == (candidates[0].id, True)


def test_the_supersession_judge_works_over_an_openai_compatible_server():
    a = DecisionSummary("d:a", "pr:1", "fixed retry", "Retry every second", "Simple.", "retry every second",
                        "2022-01-01")
    b = DecisionSummary("d:b", "pr:2", "backoff", "Use capped backoff", "Load.", "replace the fixed retry",
                        "2023-01-01")
    verdict = {"label": "supersedes", "quote": "we replace the fixed retry with backoff", "reason": "B replaces A."}

    judgment = AnthropicSupersessionJudge(client_for(FakeChat(verdict)), MODEL).judge(
        CandidatePair(a, b, ("function:x",), "we replace the fixed retry with backoff"))

    assert (judgment.label, judgment.quote) == ("supersedes", verdict["quote"])


class Grep(BaseModel):
    pattern: str


class Finding(BaseModel):
    answer: str


def test_the_scoreboards_tool_loop_runs_tools_then_answers_once_its_budget_is_spent():
    seen: list[str] = []
    grep = Tool("git_grep", "Search the code.", Grep, lambda args: seen.append(args.pattern) or "found: backoff.go")
    api = FakeChat(ToolCalls([("git_grep", {"pattern": "backoff"}), ("rm_rf", {"path": "/"})]),
                   {"answer": "Backoff is capped."})

    result = OpenAIToolLoop(sdk_for(api), MODEL).run(system="You answer.", user="Why backoff?", tools=[grep],
                                                     output=Finding, max_turns=1)

    assert result.value == Finding(answer="Backoff is capped.")
    assert seen == ["backoff"]
    first, last = api.requests
    assert [t["function"]["name"] for t in first["tools"]] == ["git_grep"]
    results = {m["tool_call_id"]: m["content"] for m in last["messages"] if m["role"] == "tool"}
    assert results["call_0"] == "found: backoff.go"
    assert "unknown tool rm_rf" in results["call_1"]  # a bad call goes back to the model, never ends the run
    assert last["tool_choice"] == "none"  # the budget is spent: answer now
    assert [c.model for c in result.usage.calls] == [MODEL, MODEL]


def test_tool_arguments_that_do_not_fit_go_back_to_the_model_instead_of_ending_the_run():
    grep = Tool("git_grep", "Search the code.", Grep, lambda args: "found")
    api = FakeChat(ToolCalls([("git_grep", {"wrong": 1})]), {"answer": "Backoff is capped."})

    result = OpenAIToolLoop(sdk_for(api), MODEL).run(system="You answer.", user="Why backoff?", tools=[grep],
                                                     output=Finding, max_turns=2)

    assert result.value == Finding(answer="Backoff is capped.")
    error = next(m["content"] for m in api.requests[1]["messages"] if m["role"] == "tool")
    assert error.startswith("ValidationError")


def test_the_scoreboards_structured_model_parses_over_an_openai_compatible_server():
    result = OpenAIStructured(sdk_for(FakeChat({"answer": "Backoff is capped."})), MODEL).parse(
        system="You answer.", user="Why backoff?", output=Finding)

    assert result.value == Finding(answer="Backoff is capped.")
    assert len(result.usage.calls) == 1
