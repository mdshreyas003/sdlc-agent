"""The committed gold set, prompts and judge labels load and are well formed."""

from eval_support import CUTOFF, REPO_ROOT

from whycode.eval.assets import DEFAULT_EVAL_DIR, prompts_version
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import check_gold, load_gold
from whycode.eval.judge import load_labels


def test_default_eval_dir_is_the_repo_eval_directory():
    assert DEFAULT_EVAL_DIR == REPO_ROOT / "eval"


def test_committed_gold_questions_are_well_formed():
    questions = load_gold(DEFAULT_EVAL_DIR / "gold")

    assert questions, "eval/gold holds the draft questions"
    # With no corpus every quote is an unknown record; anything else is a structural mistake.
    problems = [p for p in check_gold(questions, MemoryCorpus([]), cutoff=CUTOFF)
                if not p.message.startswith("unknown record")]
    assert problems == []


def test_committed_prompts_exist():
    names = {p.name for p in (DEFAULT_EVAL_DIR / "prompts").iterdir()}

    assert {"judge.md", "rag_answer.md", "git_agent.md"} <= names
    assert len(prompts_version(DEFAULT_EVAL_DIR)) == 12


def test_committed_judge_labels_load():
    load_labels(DEFAULT_EVAL_DIR / "judge_agreement" / "labels.yaml")
