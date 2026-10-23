"""`hackfront eval`: run every system over the gold questions, then score (FR-23, AC-16..18).

uv run hackfront eval --workspace eval --split dev [--systems b0,b1,s-,s] [--provider azure] [--judge-provider sarvam]
Output: data/eval/results/<split>-<time>/{answers.jsonl, scores.jsonl, report.md}. Resume a stopped run with --resume DIR.
Only human_verified questions count (AC-17); --include-unverified is for dev smoke runs only.
The test split is scored once for the final report (AC-18): a second run needs --force.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..agent import llm, prompts as P
from . import score as S, systems as X

ROOT = Path(__file__).resolve().parents[3] / "data"
GOLD = ROOT / "gold" / "questions.jsonl"
RESULTS = ROOT / "eval" / "results"
NAMES = {"b0": "B0", "b1": "B1", "s-": "S-", "s": "S"}


def load_questions(split: str, include_unverified: bool, limit: int | None, path: Path = GOLD) -> list[dict]:
    qs = [json.loads(l) for l in path.read_text(encoding="utf8").splitlines() if l.strip()]
    qs = [q for q in qs if q["split"] == split and (include_unverified or q.get("human_verified"))]
    return qs[:limit] if limit else qs


def collect(questions: list[dict], runners: dict[str, callable], path: Path) -> None:
    """Append one answer per (question, system) to path; pairs already in the file are skipped (resume)."""
    done = {(a["qid"], a["system"]) for a in map(json.loads, path.read_text(encoding="utf8").splitlines())} \
        if path.exists() else set()
    with path.open("a", encoding="utf8") as f:
        for q in questions:
            exclude = {e["url"] for e in q["gold_evidence"]} if q["tier"] == "C" else set()  # ablation: gold is absent
            for name, run in runners.items():
                if (q["id"], name) in done:
                    continue
                try:
                    a = run(q["question"], exclude)
                except Exception as error:  # noqa: BLE001  one failed call must not lose the run; counted in the report
                    a = {"system": name, "claims": [], "abstained": True, "answer": "", "seconds": 0, "tokens": 0,
                         "error": f"{type(error).__name__}: {str(error)[:150]}"}
                f.write(json.dumps({"qid": q["id"], "tier": q["tier"], **a}, ensure_ascii=False) + "\n")
                f.flush()


def score_rows(questions: list[dict], answers: list[dict], texts: dict[str, str], judge_fn) -> list[dict]:
    by_id = {q["id"]: q for q in questions}
    return [{"qid": a["qid"], "tier": a["tier"], "system": a["system"],
             **S.per_answer(by_id[a["qid"]], a, texts, judge_fn)} for a in answers if a["qid"] in by_id]


def main_eval(args) -> int:
    from .. import config
    from ..api.mapping import flat_scopes

    config.load_env()
    wanted = [NAMES[s] for s in args.systems.split(",")]
    provider = args.provider or llm.default_provider()
    judge_provider = args.judge_provider or provider
    if args.split == "test":
        if args.include_unverified:
            raise SystemExit("the test split counts only human-verified questions")
        if list(RESULTS.glob("test-*")) and not (args.force or args.resume):
            raise SystemExit("test split already scored once (AC-18); pass --force to run it again")
    qs = load_questions(args.split, args.include_unverified, args.limit)
    if not qs:
        raise SystemExit(f"no questions for split={args.split}; are any marked human_verified?")
    out = Path(args.resume) if args.resume else RESULTS / f"{args.split}-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)

    driver, scopes = config.neo4j_driver(), flat_scopes(config.scopes(args.workspace))
    try:
        arts = X.graph_artifacts(driver, scopes)
        index = X.BM25({u: f"{a['title'] or ''} {a['text'] or ''}" for u, a in arts.items()})

        def make(name):
            def run(question, exclude):
                llm.set_workspace(args.workspace)  # agent.stream clears it after each run
                if name == "B0":
                    return X.b0(question, provider)
                if name == "B1":
                    return X.b1(question, provider, arts=arts, index=index, exclude=exclude)
                return X.agent(question, provider, driver, scopes, exclude, name == "S", args.workspace)
            return run

        collect(qs, {n: make(n) for n in wanted}, out / "answers.jsonl")
        answers = [json.loads(l) for l in (out / "answers.jsonl").read_text(encoding="utf8").splitlines()]
        texts = {u: f"{a['title'] or ''} {a['text'] or ''}" for u, a in arts.items()}
        llm.set_workspace(args.workspace)
        rows = score_rows(qs, answers, texts, lambda q, facts, ans: S.judge(judge_provider, q, facts, ans))
    finally:
        driver.close()
    (out / "scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf8")
    head = (f"split `{args.split}` · {len(qs)} questions ({sum(bool(q.get('human_verified')) for q in qs)} human-verified) · "
            f"answers by `{provider}` · judge `{judge_provider}` · prompt {P.PROMPT_VERSION} · workspace `{args.workspace}`\n\n")
    (out / "report.md").write_text(head + S.report(rows, wanted), encoding="utf8")
    print(f"results in {out}")
    print((out / "report.md").read_text(encoding="utf8"))
    return 0
