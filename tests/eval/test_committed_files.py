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

    assert {"judge.md", "rag_answer.md", "git_agent.md", "llm_alone.md"} <= names
    assert len(prompts_version(DEFAULT_EVAL_DIR)) == 12


def test_committed_judge_labels_load():
    load_labels(DEFAULT_EVAL_DIR / "judge_agreement" / "labels.yaml")


def test_every_gold_anchor_lies_inside_the_real_slice_code_scope():
    from whycode.history.scope import SCHEMA_CHANGES

    def inside(kind: str, key: str) -> bool:
        if kind == "function":  # `pkg/sql.(*SchemaChanger).exec`: a scoped directory, or a package with scoped files
            directory, _, name = key.rpartition("/")
            package = f"{directory}/{name.split('.', 1)[0]}"
            return any(package == p or package.startswith(p + "/") or p.rsplit("/", 1)[0] == package
                       for p in SCHEMA_CHANGES.code_paths)
        return any(key == p or key.startswith(p + "/") for p in SCHEMA_CHANGES.code_paths)

    outside = [(q.id, q.anchor.id) for q in load_gold(DEFAULT_EVAL_DIR / "gold")
               if q.anchor is not None and q.anchor.kind != "setting" and not inside(q.anchor.kind, q.anchor.id)]
    assert outside == []  # an anchor outside the code index can only ever be refused as unresolved
