"""Git-tools agent baseline over a real throwaway repository with commits on both sides of the cutoff."""

import re

import pytest
from eval_support import (
    CUTOFF,
    FIXTURE_RECORDS,
    ScriptedToolLoop,
    anthropic_client,
    text_reply,
    tool_use_reply,
)

from whycode.eval.baselines import BaselineAnswer, CitedSentence, EvidenceQuote
from whycode.eval.corpus import CorpusRecord, LayeredCorpus, MemoryCorpus
from whycode.eval.git_agent import (
    BlameArgs,
    GitAgent,
    GitCheckout,
    GitCommits,
    GitToolError,
    GrepArgs,
    LogArgs,
    ReadArgs,
    ShowArgs,
)
from whycode.eval.gold import Case
from whycode.eval.models import AnthropicToolLoop
from whycode.eval.runner import Query
from whycode.eval.scoring import check_citations


@pytest.fixture
def checkouts(repo):
    root, shas = repo
    return GitCheckout(root, shas["zone"]), GitCheckout(root, shas["revert"])


def test_log_lists_only_commits_before_the_cutoff(checkouts, repo):
    _, shas = repo
    cutoff, _ = checkouts

    lines = cutoff.log(LogArgs()).splitlines()

    assert [line.split()[0] for line in lines] == [f"commit:{shas['zone']}", f"commit:{shas['setting']}"]
    assert lines[0].endswith("sql: skip dropped indexes when configuring zones")
    assert "Revert" not in cutoff.log(LogArgs(grep="revert|force_declarative"))


def test_show_refuses_commits_from_the_held_out_window(checkouts, repo):
    _, shas = repo
    cutoff, window = checkouts

    assert cutoff.show(ShowArgs(commit=shas["revert"][:10])) == f"commit {shas['revert'][:10]} is not in this checkout"
    assert "made upgrades fail" in window.show(ShowArgs(commit=shas["revert"][:10]))
    assert "Fixes: #117574" in cutoff.show(ShowArgs(commit=shas["zone"]))


def test_grep_blame_and_read_work_on_the_pinned_revision(checkouts, repo):
    _, shas = repo
    cutoff, _ = checkouts

    assert cutoff.grep(GrepArgs(pattern="force_declarative")) == 'pkg/sql/exec_util.go:4:\t"sql.schema.force_declarative",'
    blame = cutoff.blame(BlameArgs(path="pkg/sql/configure_zone.go", start_line=4, end_line=4))
    assert blame.startswith(shas["zone"]) and "DROP state" in blame
    assert cutoff.read_file(ReadArgs(path="pkg/sql/exec_util.go", start_line=4, end_line=4)) == \
        '4: \t"sql.schema.force_declarative",'


def test_paths_that_escape_the_checkout_or_look_like_options_are_refused(checkouts):
    cutoff, _ = checkouts

    for bad in ("../secrets", "/etc/passwd", "--output=/tmp/x"):
        with pytest.raises(GitToolError, match="not a path inside the checkout"):
            cutoff.read_file(ReadArgs(path=bad))


def test_hidden_commits_and_files_disappear_from_every_tool(checkouts, repo):
    _, shas = repo
    cutoff, _ = checkouts
    view = cutoff.hiding(frozenset({shas["setting"]}), frozenset({"docs/RFCS/20181003_schemas.md"}))

    assert shas["setting"] not in view.log(LogArgs())
    assert view.show(ShowArgs(commit=shas["setting"])).endswith("is not in this checkout")
    assert view.grep(GrepArgs(pattern="superseded")) == "no matches"
    with pytest.raises(GitToolError, match="is not available"):
        view.read_file(ReadArgs(path="docs/RFCS/20181003_schemas.md"))


def test_commits_resolve_as_citable_records_only_when_visible(checkouts, repo):
    _, shas = repo
    cutoff, window = checkouts

    record = GitCommits(cutoff).get(f"commit:{shas['zone'][:12]}")
    assert (record.id, record.kind, record.title) == (
        f"commit:{shas['zone']}", "commit", "sql: skip dropped indexes when configuring zones")
    assert "their descriptors may already be gone" in record.text and str(record.date) == "2024-06-22"
    assert GitCommits(cutoff).get(f"commit:{shas['revert']}") is None
    assert GitCommits(window).get(f"commit:{shas['revert']}") is not None
    assert GitCommits(cutoff).get("pr:121026") is None


def cite_the_setting_commit(outputs):
    sha = re.search(r"commit:([0-9a-f]{40})", outputs[-1])[1]
    quote = "forces every DDL statement through the declarative schema changer"
    return BaselineAnswer(refused=False, confidence="Medium", decisions=[],
                          evidence=[EvidenceQuote(node_id=f"commit:{sha}", quote=quote)],
                          sentences=[CitedSentence(text="The setting forces declarative DDL.", cites=[f"commit:{sha}"])])


CORPUS = MemoryCorpus(FIXTURE_RECORDS)


def agent(checkouts, model, corpus=CORPUS):
    cutoff, window = checkouts
    return GitAgent({CUTOFF: cutoff, None: window}, corpus, model, prompt="GIT PROMPT", answer_model="claude-opus-5-5")


def test_agent_answers_from_git_with_citations_that_check_out(checkouts, repo):
    loop = ScriptedToolLoop([("git_grep", {"pattern": "force_declarative"}),
                             ("git_log", {"path": "pkg/sql/exec_util.go"})], cite_the_setting_commit)

    result = agent(checkouts, loop)(Query(question="Why does sql.schema.force_declarative exist?", as_of=CUTOFF))

    answer = result.answer
    assert [(e.node_id, e.kind) for e in answer.evidence_chain] == [(f"commit:{repo[1]['setting']}", "commit")]
    assert result.usage.cost_usd() == pytest.approx(3 * (500 * 4 + 50 * 20) / 1e6)
    case = Case(id="c", question_id="c", type="lookup", question="q", anchor=None, as_of=CUTOFF, exclude=frozenset(),
                answerable=True, gold_facts=["f"], superseded_facts=[])
    corpus = LayeredCorpus(MemoryCorpus(FIXTURE_RECORDS), GitCommits(checkouts[1]))
    assert check_citations(answer, case, corpus) == (1, 1)


def cite_every_commit_seen(outputs):
    """A final answer that cites every commit the tools showed, so whatever reached the agent shows up in it."""
    seen = list(dict.fromkeys(f"commit:{sha}" for out in outputs for sha in re.findall(r"commit:([0-9a-f]{40})", out)))
    return BaselineAnswer(refused=False, confidence="Low", decisions=[],
                          evidence=[EvidenceQuote(node_id=c, quote="") for c in seen],
                          sentences=[CitedSentence(text="Everything the tools showed.", cites=seen)])


def cited(result) -> list[str]:
    return [e.node_id for e in result.answer.evidence_chain]


def test_window_cases_use_the_window_checkout(checkouts, repo):
    loop = ScriptedToolLoop([("git_log", {"max_count": 1})], cite_every_commit_seen)

    result = agent(checkouts, loop)(Query(question="Is the setting still there?", as_of=None))

    assert cited(result) == [f"commit:{repo[1]['revert']}"]  # the latest commit is the window's revert


def test_ablated_change_commits_are_hidden_from_the_agent(checkouts, repo):
    _, shas = repo
    corpus = MemoryCorpus([CorpusRecord(id="pr:125000", kind="pr", commits=[shas["setting"]])])
    loop = ScriptedToolLoop([("git_log", {})], cite_every_commit_seen)

    result = agent(checkouts, loop, corpus)(Query(question="Why?", as_of=CUTOFF, exclude=frozenset({"pr:125000"})))

    assert cited(result) == [f"commit:{shas['zone']}"]


def test_tool_loop_runs_through_the_anthropic_adapter_and_spends_its_budget(checkouts):
    final = BaselineAnswer(refused=True, confidence="Low", decisions=[], evidence=[], sentences=[])
    client = anthropic_client([tool_use_reply("git_log", {"grep": "zone"}),
                               tool_use_reply("rm_rf", {"path": "/"}, id="toolu_2"),  # an unknown tool
                               text_reply(final)], [])

    result = agent(checkouts, AnthropicToolLoop(client, "claude-opus-5-5"))
    result.max_turns = 2
    answered = result(Query(question="Why skip dropped indexes?", as_of=CUTOFF))

    # Two tool turns, then the answer: the unknown tool did not end the run, and the schema-valid reply parsed.
    assert answered.answer.refused and len(answered.usage.calls) == 3
