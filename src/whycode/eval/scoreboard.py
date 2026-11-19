"""One scored run: gate the gold set, ask every system every case, judge, score, write the report.

Output: `eval/results/<split>-<YYYYmmdd-HHMMSS>/` with `manifest.json`, `answers.jsonl`,
`verdicts.jsonl`, `scores.jsonl` and `report.md`. Discipline carried over from the legacy runner:

- only human-verified questions that pass the gold check count (unverified ones only in a dev smoke run);
- the test split is scored once: a second test run is refused while any `results/test-*` exists,
  and a test run needs the prompts committed;
- `resume` finishes a stopped run (same prompts) without asking any system twice.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from whycode.eval import assets
from whycode.eval.corpus import Corpus
from whycode.eval.gold import GoldSetError, Split, build_cases, check_gold, load_gold, select
from whycode.eval.judge import Judge, JudgeInput, Verdict
from whycode.eval.runner import AnswerRecord, System, collect, to_jsonl, write_json
from whycode.eval.scoring import report, score

CUTOFF = dt.date(2024, 6, 30)  # ADR-0002: history after this date is the Held-out Window


class ScoreboardError(RuntimeError):
    """The run was refused; the message says why."""


@dataclass(frozen=True)
class RunResult:
    run_dir: Path
    report: str


def run_eval(split: Split, *, eval_dir: Path, corpus: Corpus, systems: Sequence[System], judge: Judge,
             judge_model: str, cutoff: dt.date = CUTOFF, reference: str | None = None,
             include_unverified: bool = False, limit: int | None = None, resume: Path | None = None,
             clock: Callable[[], float] = time.perf_counter,
             now: Callable[[], dt.datetime] = dt.datetime.now) -> RunResult:
    every = load_gold(eval_dir / "gold")
    try:
        chosen = select(every, split, include_unverified)[:limit]
    except GoldSetError as error:
        raise ScoreboardError(str(error)) from error
    if not chosen:
        raise ScoreboardError(f"no human-verified questions in the {split} split (see eval/README.md)")
    problems = check_gold(chosen, corpus, cutoff=cutoff, every=every)
    if problems:
        raise ScoreboardError("gold check failed:\n" + "\n".join(f"  {p.question_id}: {p.message}" for p in problems))

    version = assets.prompts_version(eval_dir)
    results = eval_dir / "results"
    if resume is None:
        if split == "test":
            if done := sorted(p.name for p in results.glob("test-*")):
                raise ScoreboardError(f"the test split was already scored ({', '.join(done)}); it is scored once")
            if dirty := assets.uncommitted(eval_dir, "prompts"):
                raise ScoreboardError(f"prompts have uncommitted changes: {', '.join(dirty)}; commit them first")
        run_dir = results / f"{split}-{now().strftime('%Y%m%d-%H%M%S')}"
        run_dir.mkdir(parents=True)
        cases = build_cases(chosen, every, cutoff=cutoff)
        manifest = {"split": split, "created": now().isoformat(timespec="seconds"), "cutoff": cutoff,
                    "questions": [q.id for q in chosen], "human_verified": sum(q.human_verified for q in chosen),
                    "cases": len(cases), "include_unverified": include_unverified,
                    "systems": {s.name: dict(s.models) for s in systems}, "judge_model": judge_model,
                    "prompts_version": version, "prompt_files": assets.prompt_hashes(eval_dir),
                    "git_commit": assets.git_commit(eval_dir)}
        write_json(run_dir / "manifest.json", manifest)
    else:
        run_dir = resume
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if manifest["split"] != split:
            raise ScoreboardError(f"{run_dir.name} is a {manifest['split']} run, not {split}")
        if manifest["prompts_version"] != version:
            raise ScoreboardError("prompts changed since this run started; start a new run instead of resuming")
        chosen = [q for q in every if q.id in set(manifest["questions"])]
        cases = build_cases(chosen, every, cutoff=cutoff)

    records = collect(cases, systems, run_dir / "answers.jsonl", clock=clock)
    by_case = {c.id: c for c in cases}
    verdicts = _VerdictCache(run_dir / "verdicts.jsonl", judge)
    names = [s.name for s in systems]
    scores = [score(by_case[r.case_id], r, corpus, verdicts.judge_for(r))
              for r in records if r.case_id in by_case and r.system in names]
    (run_dir / "scores.jsonl").write_text(to_jsonl(scores), encoding="utf-8")
    text = report(scores, names, header=_header(run_dir, manifest, systems, eval_dir), reference=reference)
    (run_dir / "report.md").write_text(text, encoding="utf-8")
    return RunResult(run_dir, text)


class _VerdictCache:
    """Judge each (case, system) answer once, even across resumed runs."""

    def __init__(self, path: Path, judge: Judge):
        self.path, self.judge = path, judge
        self.done: dict[tuple[str, str], Verdict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.done[(row["case_id"], row["system"])] = Verdict.model_validate(row["verdict"])

    def judge_for(self, record: AnswerRecord) -> Judge:
        key = (record.case_id, record.system)

        def cached(item: JudgeInput) -> Verdict:
            if key not in self.done:
                self.done[key] = self.judge(item)
                with self.path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps({"case_id": key[0], "system": key[1],
                                          "verdict": self.done[key].model_dump()}) + "\n")
            return self.done[key]

        return cached


def _header(run_dir: Path, manifest: dict, systems: Sequence[System], eval_dir: Path) -> str:
    def models(s: System) -> str:
        return ", ".join(f"{role} {m}" for role, m in s.models.items()) or "models not declared"

    lines = [f"# Scoreboard: `{manifest['split']}` split", "",
             f"Run `{run_dir.name}`; {len(manifest['questions'])} questions ({manifest['human_verified']} "
             f"human-verified), {manifest['cases']} cases; cutoff {manifest['cutoff']}; judge "
             f"`{manifest['judge_model']}`; prompts `{manifest['prompts_version']}`.", "",
             "Systems: " + "; ".join(f"`{s.name}` ({models(s)})" for s in systems) + "."]
    for role, verb in (("answer", "answer with"), ("embedding", "embed with")):
        used = {s.models[role] for s in systems if s.models.get(role)}
        if len(used) > 1:
            lines += ["", f"WARNING: systems {verb} different models ({', '.join(sorted(used))}); "
                          "differences then mix method and model."]
    agreement = eval_dir / "judge_agreement" / "agreement.md"
    lines += ["", agreement.read_text(encoding="utf-8").strip().splitlines()[0] if agreement.exists()
              else "Judge agreement: not measured yet (see eval/README.md)."]
    return "\n".join(lines) + "\n"
