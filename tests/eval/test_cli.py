"""`whycode-eval` end to end on the fixture corpus: our system and both baselines in one results table."""

import datetime as dt
import io
import json
import re
import shutil

import pytest
from eval_support import (
    FIXTURE_RECORDS,
    REPO_ROOT,
    HashEmbedder,
    ScriptedModel,
    ScriptedToolLoop,
)

from whycode.eval.baselines import BaselineAnswer, CitedSentence, EvidenceQuote
from whycode.eval.cli import Deps, main
from whycode.eval.corpus import write_jsonl
from whycode.eval.gold import (
    GoldEvidence,
    GoldQuestion,
    WindowAfter,
    load_gold,
    save_gold,
)
from whycode.eval.judge import HandLabels, Verdict, load_labels, save_labels

ZONE_QUOTE = "because their descriptors may already be gone"
QUESTIONS = [
    GoldQuestion(id="L1", type="lookup", origin="human", question="Why does zone configuration skip dropped indexes?",
                 gold_facts=["Their descriptors may already be gone"], split="dev", human_verified=True,
                 gold_evidence=[GoldEvidence(node_id="pr:121026", quote=ZONE_QUOTE)]),
    GoldQuestion(id="W1", type="window", origin="human", question="Is sql.schema.force_declarative still a setting?",
                 gold_facts=["The setting forces DDL through the declarative schema changer"], split="dev",
                 human_verified=True,
                 gold_evidence=[GoldEvidence(node_id="pr:125000", quote="forces every DDL statement")],
                 after=WindowAfter(gold_facts=["The setting was reverted"],
                                   superseded_facts=["The setting forces DDL through the declarative schema changer"],
                                   gold_evidence=[GoldEvidence(node_id="pr:127500", quote="made upgrades fail")])),
    GoldQuestion(id="U1", type="unanswerable", origin="human", answerable=False, ablates="L1", split="dev",
                 question="Why does zone configuration skip dropped indexes?", human_verified=True),
]


def reply(output, system, user):
    if output is Verdict:
        return Verdict(covered=[True] * 5, presented_as_live=[False] * 5, reports_change=True)
    passage = re.search(r'<passage node_id="([^"]+)"', user)
    if passage is None:  # the LLM alone sees no records
        return BaselineAnswer(refused=True, confidence="Low", decisions=[], evidence=[], sentences=[])
    node_id = passage[1]
    return BaselineAnswer(refused=False, confidence="Medium", decisions=[],
                          evidence=[EvidenceQuote(node_id=node_id, quote="made up")],
                          sentences=[CitedSentence(text="Because of that record.", cites=[node_id])])


def cite_latest_commit(outputs):
    sha = re.search(r"commit:([0-9a-f]{40})", outputs[-1])[1]
    return BaselineAnswer(refused=False, confidence="Low", decisions=[], evidence=[],
                          sentences=[CitedSentence(text="See the latest commit.", cites=[f"commit:{sha}"])])


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "eval"
    shutil.copytree(REPO_ROOT / "eval" / "prompts", root / "prompts")
    (root / "gold").mkdir()
    (root / "results").mkdir()
    save_gold(root / "gold" / "human.yaml", QUESTIONS)
    write_jsonl(tmp_path / "corpus.jsonl", FIXTURE_RECORDS)
    return root, tmp_path / "corpus.jsonl"


def deps():
    out = io.StringIO()
    clock = iter(x * 0.25 for x in range(100_000))
    return Deps(structured=lambda model: ScriptedModel(reply, model=model),
                tool_loop=lambda model: ScriptedToolLoop([("git_log", {"max_count": 1})], cite_latest_commit, model),
                embedder=HashEmbedder, clock=lambda: next(clock), now=lambda: dt.datetime(2026, 11, 20, 12, 0, 0),
                out=out)


def run(workspace, repo, d, *extra):
    root, corpus = workspace
    _, shas = repo
    return main(["run", "--split", "dev", "--eval-dir", str(root), "--corpus", str(corpus),
                 "--systems", "vector-rag,git-agent,ours=eval_support:ours_factory", "--reference", "ours",
                 "--git-repo", str(repo[0]), "--cutoff-rev", shas["zone"], "--window-rev", shas["revert"], *extra],
                d)


def test_one_command_scores_our_system_and_both_baselines(workspace, repo):
    d = deps()
    assert run(workspace, repo, d) == 0

    report = d.out.getvalue()
    assert "| question type | vector-rag | git-agent | ours |" in report
    assert "Errors (failed calls, scored as failures): vector-rag 0, git-agent 0, ours 0" in report
    for section in ("Answer correctness", "Citation precision", "Supersession catch rate", "Refusal accuracy",
                    "Invented-answer rate", "Latency", "Cost", "Paired differences (ours minus each system"):
        assert section in report
    run_dir = workspace[0] / "results" / "dev-20261120-120000"
    answers = [json.loads(line) for line in (run_dir / "answers.jsonl").read_text().splitlines()]
    assert len(answers) == 4 * 3  # L1, W1@before, W1@after, U1 for each system
    window_git = next(a for a in answers if a["case_id"] == "W1@after" and a["system"] == "git-agent")
    assert window_git["answer"]["sentences"][0]["cites"] == [f"commit:{repo[1]['revert']}"]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["systems"]["vector-rag"] == {"answer": "claude-opus-5-5", "embedding": "BAAI/bge-small-en-v1.5"}


ALL_SYSTEMS = ("ours=eval_support:ours_factory,"
               "ours-without-supersession=eval_support:ours_without_supersession_factory,"
               "llm-alone,vector-rag,git-agent")


def test_the_results_table_has_our_system_and_all_four_baselines(workspace, repo):
    d = deps()
    assert run(workspace, repo, d, "--systems", ALL_SYSTEMS) == 0

    report = d.out.getvalue()
    assert "| question type | ours | ours-without-supersession | llm-alone | vector-rag | git-agent |" in report
    assert "llm-alone 0" in report  # no failed calls
    run_dir = workspace[0] / "results" / "dev-20261120-120000"
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["systems"]["llm-alone"] == {"answer": "claude-opus-5-5"}
    assert "llm_alone.md" in manifest["prompt_files"]


def test_labels_are_generated_and_keep_a_human_verification(workspace):
    root, corpus = workspace
    d = deps()
    assert main(["labels", "--eval-dir", str(root), "--corpus", str(corpus)], d) == 0
    path = root / "gold" / "automatic.yaml"
    labels = load_gold(root / "gold")
    auto = [q for q in labels if q.origin == "automatic"]
    assert len(auto) == 4
    save_gold(path, [q.model_copy(update={"human_verified": q.id == "auto-revert-pr-116879"}) for q in auto])

    assert main(["labels", "--eval-dir", str(root), "--corpus", str(corpus)], d) == 0
    verified = [q.id for q in load_gold(root / "gold") if q.origin == "automatic" and q.human_verified]
    assert verified == ["auto-revert-pr-116879"]


def test_check_fails_only_for_verified_questions(workspace):
    root, corpus = workspace
    draft = QUESTIONS[0].model_copy(update={"id": "D1", "human_verified": False,
                                            "gold_evidence": [GoldEvidence(node_id="pr:1", quote="x")]})
    save_gold(root / "gold" / "drafts.yaml", [draft])
    d = deps()
    assert main(["check", "--eval-dir", str(root), "--corpus", str(corpus)], d) == 0
    assert "draft D1: unknown record pr:1" in d.out.getvalue()

    save_gold(root / "gold" / "drafts.yaml", [draft.model_copy(update={"human_verified": True})])
    assert main(["check", "--eval-dir", str(root), "--corpus", str(corpus)], deps()) == 1


def test_judge_sheet_and_agreement_close_the_loop(workspace, repo):
    root, _ = workspace
    assert run(workspace, repo, deps()) == 0
    run_dir = root / "results" / "dev-20261120-120000"

    assert main(["judge-sheet", "--eval-dir", str(root), "--run", str(run_dir), "--n", "3"], deps()) == 0
    sheet = load_labels(root / "judge_agreement" / "labels.yaml")
    assert len(sheet) == 3 and not any(item.human_labelled for item in sheet)
    labelled = [item.model_copy(update={"human_labelled": True, "labels": HandLabels(
        covered=[True] * len(item.gold_facts),
        presented_as_live=[False] * len(item.superseded_facts) if item.superseded_facts else None,
        reports_change=True if item.superseded_facts else None)}) for item in sheet]
    save_labels(root / "judge_agreement" / "labels.yaml", labelled)

    d = deps()
    assert main(["agreement", "--eval-dir", str(root)], d) == 1  # 3 < 15 labelled answers
    assert "Judge agreement on 3 hand-labelled answers" in d.out.getvalue()
    assert "below the 15 required" in (root / "judge_agreement" / "agreement.md").read_text()

    d = deps()
    d.now = lambda: dt.datetime(2026, 11, 20, 13, 0, 0)
    assert run(workspace, repo, d) == 0
    assert "Judge agreement on 3 hand-labelled answers" in d.out.getvalue()  # copied into every report header
