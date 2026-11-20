"""`whycode-eval`: the scoreboard's one command (composition root; the only place a real client is built).

    whycode-eval labels      --corpus C            write eval/gold/automatic.yaml from history
    whycode-eval check       --corpus C            gold check and counts; non-zero exit if a verified question fails
    whycode-eval run         --corpus C --split dev|test [--systems llm-alone,vector-rag,git-agent,ours=pkg.mod:factory]
                             [--git-repo R --cutoff-rev SHA [--window-rev SHA]] [--resume DIR]
    whycode-eval judge-sheet --run DIR [--n 20]    sample answers into eval/judge_agreement/labels.yaml
    whycode-eval agreement                         judge vs hand labels, written to eval/judge_agreement/agreement.md
    whycode-eval calibration --run DIR             confidence vs correctness: DIR/calibration.md and calibration.svg

An external system (our `why`) is named `name=module:attribute`; the attribute is called with a
`SystemContext` and returns a `System` or a plain `Query -> Answer` callable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import os
import random
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from whycode.eval import assets
from whycode.eval.corpus import Corpus, LayeredCorpus, MemoryCorpus
from whycode.eval.gold import check_gold, load_gold, save_gold
from whycode.eval.judge import (
    FactJudge,
    LabelledAnswer,
    agreement,
    load_labels,
    render_answer,
    save_labels,
)
from whycode.eval.labels import generate_labels
from whycode.eval.models import (
    ANSWER_MODEL,
    EMBEDDING_MODEL,
    JUDGE_MODEL,
    StructuredModel,
    ToolLoopModel,
)
from whycode.eval.runner import AnswerRecord, System, read_records
from whycode.eval.scoreboard import CUTOFF, ScoreboardError, run_eval

CACHE_DIR = assets.DEFAULT_EVAL_DIR.parent / ".cache" / "eval"


@dataclass(frozen=True)
class SystemContext:
    """What an external system factory gets: the same corpus, cutoff and models as the baselines."""

    corpus: Corpus
    cutoff: dt.date
    eval_dir: Path
    answer_model: str = ANSWER_MODEL
    embedding_model: str = EMBEDDING_MODEL


@dataclass
class Deps:
    """Model factories; tests replace them with scripted ones."""

    structured: Callable[[str], StructuredModel]
    tool_loop: Callable[[str], ToolLoopModel]
    embedder: Callable[[str], Any]
    clock: Callable[[], float] = time.perf_counter
    now: Callable[[], dt.datetime] = dt.datetime.now
    out: Any = field(default_factory=lambda: sys.stdout)


def default_deps() -> Deps:
    @cache
    def client():
        import anthropic

        return anthropic.Anthropic()  # credentials from the environment, never at import time

    def structured(model: str) -> StructuredModel:
        from whycode.eval.models import AnthropicStructured

        return AnthropicStructured(client(), model)

    def tool_loop(model: str) -> ToolLoopModel:
        from whycode.eval.models import AnthropicToolLoop

        return AnthropicToolLoop(client(), model)

    def embedder(name: str):
        from whycode.eval.rag import FastEmbedder

        return FastEmbedder(name)

    return Deps(structured=structured, tool_loop=tool_loop, embedder=embedder)


def main(argv: Sequence[str] | None = None, deps: Deps | None = None) -> int:
    args = _parser().parse_args(argv)
    deps = deps or default_deps()
    try:
        return args.handler(args, deps)
    except ScoreboardError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="whycode-eval", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(required=True)

    def command(name: str, handler: Callable, help: str, corpus: bool = True) -> argparse.ArgumentParser:
        c = sub.add_parser(name, help=help)
        c.set_defaults(handler=handler)
        c.add_argument("--eval-dir", type=Path, default=assets.DEFAULT_EVAL_DIR)
        c.add_argument("--cutoff", type=dt.date.fromisoformat, default=CUTOFF)
        if corpus:
            env = os.environ.get("WHYCODE_EVAL_CORPUS")
            c.add_argument("--corpus", type=Path, default=Path(env) if env else None, required=env is None,
                           help="JSON-lines corpus (one CorpusRecord per line); env WHYCODE_EVAL_CORPUS")
        return c

    labels = command("labels", _labels, "generate automatic labels from history")
    labels.add_argument("--window-end", type=dt.date.fromisoformat, default=None)
    command("check", _check, "check every gold quote against the corpus")
    run = command("run", _run, "score systems on one split")
    run.add_argument("--split", choices=("dev", "test"), required=True)
    run.add_argument("--systems", default="vector-rag,git-agent")
    run.add_argument("--reference", default=None, help="system the paired differences are taken against")
    run.add_argument("--git-repo", type=Path, default=None, help="local cockroachdb clone for the git-agent")
    run.add_argument("--cutoff-rev", default="d13253527955eaa2da09394b8a2729627ab25c48")
    run.add_argument("--window-rev", default=None, help="revision at the end of the Held-out Window")
    run.add_argument("--answer-model", default=ANSWER_MODEL)
    run.add_argument("--judge-model", default=JUDGE_MODEL)
    run.add_argument("--embedding-model", default=EMBEDDING_MODEL)
    run.add_argument("--resume", type=Path, default=None)
    run.add_argument("--include-unverified", action="store_true", help="dev smoke runs only")
    run.add_argument("--limit", type=int, default=None)
    sheet = command("judge-sheet", _judge_sheet, "sample run answers for hand labelling", corpus=False)
    sheet.add_argument("--run", type=Path, required=True)
    sheet.add_argument("--n", type=int, default=20)
    sheet.add_argument("--seed", type=int, default=0)
    agree = command("agreement", _agreement, "judge agreement with hand labels", corpus=False)
    agree.add_argument("--judge-model", default=JUDGE_MODEL)
    calib = command("calibration", _calibration, "plot confidence against correctness for one run", corpus=False)
    calib.add_argument("--run", type=Path, required=True, help="a results directory written by `run`")
    calib.add_argument("--systems", default=None, help="comma-separated system names (default: every system)")
    calib.add_argument("--out", type=Path, default=None, help="where to write the files (default: the run directory)")
    return p


def _labels(args: argparse.Namespace, deps: Deps) -> int:
    corpus = MemoryCorpus.from_jsonl(args.corpus)
    path = args.eval_dir / "gold" / "automatic.yaml"
    old = {q.id: q for q in load_gold(path.parent) if q.origin == "automatic"} if path.exists() else {}
    fresh = []
    for q in generate_labels(corpus, cutoff=args.cutoff, window_end=args.window_end):
        prior = old.get(q.id)
        same = prior is not None and prior.model_dump(exclude={"human_verified", "split", "note"}) == \
            q.model_dump(exclude={"human_verified", "split", "note"})
        fresh.append(q.model_copy(update={"human_verified": prior.human_verified, "split": prior.split})
                     if same else q)  # keep a human's verification while the label is unchanged
    save_gold(path, fresh)
    print(f"wrote {len(fresh)} automatic labels to {path} "
          f"({sum(q.human_verified for q in fresh)} still human-verified)", file=deps.out)
    return 0


def _check(args: argparse.Namespace, deps: Deps) -> int:
    corpus = MemoryCorpus.from_jsonl(args.corpus)
    questions = load_gold(args.eval_dir / "gold")
    problems = check_gold(questions, corpus, cutoff=args.cutoff)
    verified = {q.id for q in questions if q.human_verified}
    print(f"{len(questions)} questions; {len(verified)} human-verified", file=deps.out)
    for label, key in (("type", "type"), ("origin", "origin"), ("split", "split")):
        counts = Counter(getattr(q, key) for q in questions)
        print(f"  by {label}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), file=deps.out)
    for p in problems:
        tag = "ERROR" if p.question_id in verified else "draft"
        print(f"{tag} {p.question_id}: {p.message}", file=deps.out)
    blocking = [p for p in problems if p.question_id in verified]
    print("gold ok" if not blocking else f"{len(blocking)} problems in human-verified questions", file=deps.out)
    return 1 if blocking else 0


def _run(args: argparse.Namespace, deps: Deps) -> int:
    corpus = MemoryCorpus.from_jsonl(args.corpus)
    citation_corpus: Corpus = corpus
    systems, names = [], [s.strip() for s in args.systems.split(",") if s.strip()]
    window_checkout = None
    for name in names:
        if name == "llm-alone":
            from whycode.eval.llm_alone import LlmAlone

            prompt = assets.load_prompt(args.eval_dir, "llm_alone.md")
            systems.append(LlmAlone(corpus, deps.structured(args.answer_model), prompt, args.answer_model).system())
        elif name == "vector-rag":
            from whycode.eval.rag import VectorIndex, VectorRag

            index = VectorIndex(corpus.records(), deps.embedder(args.embedding_model), cache_dir=CACHE_DIR)
            prompt = assets.load_prompt(args.eval_dir, "rag_answer.md")
            systems.append(VectorRag(corpus, index, deps.structured(args.answer_model), prompt,
                                     args.answer_model).system())
        elif name == "git-agent":
            from whycode.eval.git_agent import GitAgent, GitCheckout, GitCommits

            if args.git_repo is None:
                raise ScoreboardError("the git-agent needs --git-repo (a local cockroachdb clone)")
            checkouts = {args.cutoff: GitCheckout(args.git_repo, args.cutoff_rev)}
            if args.window_rev:
                window_checkout = checkouts[None] = GitCheckout(args.git_repo, args.window_rev)
            prompt = assets.load_prompt(args.eval_dir, "git_agent.md")
            systems.append(GitAgent(checkouts, corpus, deps.tool_loop(args.answer_model), prompt,
                                    args.answer_model).system())
            citation_corpus = LayeredCorpus(corpus, GitCommits(window_checkout or checkouts[args.cutoff]))
        elif "=" in name:
            label, target = name.split("=", 1)
            systems.append(_external(label, target, SystemContext(corpus, args.cutoff, args.eval_dir,
                                                                  args.answer_model, args.embedding_model)))
        else:
            raise ScoreboardError(f"unknown system {name!r}: use llm-alone, vector-rag, git-agent or "
                                 "name=module:factory")
    judge = FactJudge(deps.structured(args.judge_model), assets.load_prompt(args.eval_dir, "judge.md"))
    result = run_eval(args.split, eval_dir=args.eval_dir, corpus=citation_corpus, systems=systems, judge=judge,
                      judge_model=args.judge_model, cutoff=args.cutoff, reference=args.reference,
                      include_unverified=args.include_unverified, limit=args.limit, resume=args.resume,
                      clock=deps.clock, now=deps.now)
    print(result.report, file=deps.out)
    print(f"results in {result.run_dir}", file=deps.out)
    return 0


def _external(label: str, target: str, ctx: SystemContext) -> System:
    module, _, attr = target.partition(":")
    made = getattr(importlib.import_module(module), attr)(ctx)
    if isinstance(made, System):
        return System(label, made.run, made.models)
    return System(label, made, {"answer": ctx.answer_model, "embedding": ctx.embedding_model})


def _judge_sheet(args: argparse.Namespace, deps: Deps) -> int:
    path = args.eval_dir / "judge_agreement" / "labels.yaml"
    existing = load_labels(path) if path.exists() else []
    questions = {q.id: q for q in load_gold(args.eval_dir / "gold")}
    taken = {item.source for item in existing}
    records: list[AnswerRecord] = [r for r in read_records(args.run / "answers.jsonl")
                                   if r.answer is not None and not r.answer.refused
                                   and f"{args.run.name}/{r.case_id}/{r.system}" not in taken]
    random.Random(args.seed).shuffle(records)
    added = []
    for r in records[: args.n]:
        q = questions[r.case_id.split("@")[0]]
        after = r.case_id.endswith("@after") and q.after is not None
        added.append(LabelledAnswer(
            id=f"ja-{len(existing) + len(added) + 1:03d}", question=q.question,
            gold_facts=q.after.gold_facts if after else q.gold_facts,
            superseded_facts=q.after.superseded_facts if after else q.superseded_facts,
            answer=render_answer(r.answer), source=f"{args.run.name}/{r.case_id}/{r.system}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    save_labels(path, [*existing, *added])
    print(f"added {len(added)} answers to {path}; label them and set human_labelled: true", file=deps.out)
    return 0


def _agreement(args: argparse.Namespace, deps: Deps) -> int:
    path = args.eval_dir / "judge_agreement" / "labels.yaml"
    judge = FactJudge(deps.structured(args.judge_model), assets.load_prompt(args.eval_dir, "judge.md"))
    result = agreement(load_labels(path) if path.exists() else [], judge)
    summary = result.summary() + f" Judge `{args.judge_model}`, prompts `{assets.prompts_version(args.eval_dir)}`."
    (args.eval_dir / "judge_agreement" / "agreement.md").write_text(summary + "\n", encoding="utf-8")
    print(summary, file=deps.out)
    return 0 if result.enough else 1


def _calibration(args: argparse.Namespace, deps: Deps) -> int:
    from whycode.eval.calibration import calibration

    if not (args.run / "scores.jsonl").exists():
        raise ScoreboardError(f"{args.run} holds no scores.jsonl: point --run at a directory written by `run`")
    systems = [s.strip() for s in args.systems.split(",") if s.strip()] if args.systems else None
    result = calibration(args.run, systems)
    out = args.out or args.run
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.svg").write_text(result.svg(), encoding="utf-8")
    (out / "calibration.md").write_text(result.markdown(), encoding="utf-8")
    print(result.markdown(plot=None), file=deps.out)
    print(f"wrote {out / 'calibration.md'} and {out / 'calibration.svg'}", file=deps.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
