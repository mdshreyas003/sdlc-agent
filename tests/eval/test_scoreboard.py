"""One scored run end to end with stub systems: run directory, guards, resume and reproducibility."""

import datetime as dt
import json
import subprocess

import pytest
from eval_support import CUTOFF, FIXTURE_RECORDS

from whycode.contract import Answer, EvidenceItem, Sentence
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import GoldEvidence, GoldQuestion, save_gold
from whycode.eval.judge import Verdict
from whycode.eval.models import ModelCall, Usage
from whycode.eval.runner import Answered, Query, System
from whycode.eval.scoreboard import ScoreboardError, run_eval

CORPUS = MemoryCorpus(FIXTURE_RECORDS)
NOW = dt.datetime(2026, 11, 20, 10, 15, 0)
ZONE_QUOTE = "because their descriptors may already be gone"


def gold(id, split="dev", verified=True, **kw):
    base = dict(id=id, type="lookup", origin="human", question=f"Why {id}?", split=split, human_verified=verified,
                gold_facts=["Dropped indexes may have no descriptor"],
                gold_evidence=[GoldEvidence(node_id="pr:121026", quote=ZONE_QUOTE)])
    return GoldQuestion(**(base | kw))


QUESTIONS = [
    gold("L1"),
    gold("U1", type="unanswerable", answerable=False, gold_facts=[], gold_evidence=[], ablates="L1"),
    gold("DRAFT", verified=False, gold_evidence=[GoldEvidence(node_id="pr:121026", quote="not in the record")]),
    gold("T1", split="test"),
]


def lay_out(root, questions=QUESTIONS, commit=True):
    (root / "gold").mkdir(parents=True)
    (root / "prompts").mkdir()
    (root / "results").mkdir()
    save_gold(root / "gold" / "human.yaml", questions)
    (root / "prompts" / "judge.md").write_text("Grade the answer.\n")
    if commit:
        git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "gold"], check=True)
    return root


def oracle(query: Query) -> Answered:
    refused = "pr:121026" in query.exclude
    answer = Answer(anchor=query.anchor, refused=refused, confidence="Medium",
                    evidence_chain=[] if refused else [EvidenceItem(node_id="pr:121026", kind="pr", quote=ZONE_QUOTE)],
                    sentences=[Sentence(text="Dropped indexes may have no descriptor.", cites=[])])
    return Answered(answer, Usage(calls=[ModelCall(model="claude-opus-5-5", input_tokens=1000, output_tokens=100)]))


def refuser(query: Query) -> Answer:
    return Answer(anchor=None, refused=True, confidence="Low")


def judge(item):
    return Verdict(covered=[True] * len(item.gold_facts))


def run(root, split="dev", systems=None, **kw):
    clock = iter(x * 0.5 for x in range(10_000))
    return run_eval(split, eval_dir=root, corpus=CORPUS, cutoff=CUTOFF, judge=judge, judge_model="scripted-judge",
                    systems=systems or [System("ours", oracle, {"answer": "claude-opus-5-5"}),
                                        System("refuser", refuser)],
                    reference="ours", clock=lambda: next(clock), now=lambda: NOW, **kw)


def test_a_dev_run_scores_every_system_and_writes_the_run_directory(tmp_path):
    result = run(lay_out(tmp_path))

    assert result.run_dir == tmp_path / "results" / "dev-20261120-101500"
    answers = (result.run_dir / "answers.jsonl").read_text().splitlines()
    assert len(answers) == 4  # (L1, U1) x (ours, refuser); the unverified draft is not asked
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["questions"] == ["L1", "U1"] and manifest["systems"]["ours"] == {"answer": "claude-opus-5-5"}
    assert len(manifest["prompts_version"]) == 12
    report = (result.run_dir / "report.md").read_text()
    assert report == result.report
    assert "| lookup | 100% [100-100] n=1 | 0% [0-0] n=1 |" in report  # correctness
    assert "| unanswerable | 0% [0-0] n=1 | 0% [0-0] n=1 |" in report  # invented-answer rate
    assert "2 questions (2 human-verified)" in report


def test_the_ablated_question_hides_its_evidence_from_every_system(tmp_path):
    seen = []
    run(lay_out(tmp_path), systems=[System("spy", lambda q: seen.append(q) or refuser(q))])

    assert [(q.question, q.exclude, q.as_of) for q in seen] == [
        ("Why L1?", frozenset(), CUTOFF), ("Why U1?", frozenset({"pr:121026"}), CUTOFF)]


def test_a_verified_question_that_fails_the_gold_check_blocks_the_run(tmp_path):
    bad = gold("BAD", gold_evidence=[GoldEvidence(node_id="pr:121026", quote="paraphrased words")])

    with pytest.raises(ScoreboardError, match="BAD: quote not verbatim in pr:121026"):
        run(lay_out(tmp_path, [*QUESTIONS, bad]))


def test_no_verified_questions_means_no_run(tmp_path):
    with pytest.raises(ScoreboardError, match="no human-verified questions"):
        run(lay_out(tmp_path, [gold("D", verified=False)]))


def test_dev_smoke_run_may_include_unverified_questions_that_pass_the_check(tmp_path):
    result = run(lay_out(tmp_path, [gold("D", verified=False)]), include_unverified=True)

    assert "1 questions (0 human-verified)" in result.report


def test_the_test_split_is_scored_once(tmp_path):
    root = lay_out(tmp_path)
    first = run(root, split="test")

    with pytest.raises(ScoreboardError, match="test split was already scored"):
        run(root, split="test")
    assert run(root, split="test", resume=first.run_dir).run_dir == first.run_dir  # finishing a stopped run is fine


def test_the_test_split_needs_committed_prompts_and_gold(tmp_path):
    root = lay_out(tmp_path)
    (root / "prompts" / "judge.md").write_text("Grade the answer, but tuned.\n")
    (root / "gold" / "late.yaml").write_text("[]\n")

    with pytest.raises(ScoreboardError, match="uncommitted changes in prompts or gold: gold/late.yaml, prompts/judge.md"):
        run(root, split="test")


def test_resume_finishes_a_stopped_run_without_asking_again(tmp_path):
    root = lay_out(tmp_path)
    calls = []

    def flaky(query):
        calls.append(query.question)
        if len(calls) == 1:
            raise RuntimeError("rate limited")
        return refuser(query)

    first = run(root, systems=[System("flaky", flaky)])
    assert "Errors (failed calls, scored as failures): flaky 1" in first.report
    run(root, systems=[System("flaky", flaky)], resume=first.run_dir)
    assert calls == ["Why L1?", "Why U1?"]  # nothing is asked twice, the error record stays


def test_resume_refuses_changed_prompts(tmp_path):
    root = lay_out(tmp_path)
    first = run(root)
    (root / "prompts" / "judge.md").write_text("Different instructions.\n")

    with pytest.raises(ScoreboardError, match="prompts changed since this run started"):
        run(root, resume=first.run_dir)


def test_same_inputs_give_the_same_report(tmp_path):
    root = lay_out(tmp_path)
    a = run(root).report
    b = run_eval("dev", eval_dir=root, corpus=CORPUS, cutoff=CUTOFF, judge=judge, judge_model="scripted-judge",
                 systems=[System("ours", oracle, {"answer": "claude-opus-5-5"}), System("refuser", refuser)],
                 reference="ours", clock=iter(x * 0.5 for x in range(100)).__next__,
                 now=lambda: NOW + dt.timedelta(minutes=1)).report

    assert a.replace("101500", "101600") == b


def test_report_warns_when_systems_answer_with_different_models(tmp_path):
    result = run(lay_out(tmp_path), systems=[System("ours", oracle, {"answer": "claude-opus-5-5"}),
                                             System("other", refuser, {"answer": "claude-sonnet-5-5"})])

    assert "WARNING: systems answer with different models" in result.report
