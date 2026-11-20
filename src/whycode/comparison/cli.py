"""`whycode-agents`: the agent comparison (ticket 05). See `eval/agent-comparison/README.md`.

    uv run whycode-agents freeze                                   # hash the task records (before any run)
    uv run whycode-agents run --dry-run                            # print what would run, spend nothing
    uv run whycode-agents run --task H1-clock-errors-permanent --repo ~/src/cockroach   # both arms of one task
    uv run whycode-agents run --repo ~/src/cockroach               # every task, with and without the tools
    uv run whycode-agents report --run eval/agent-comparison/results/<run>   # re-make table.md (after grades.yaml)
    uv run whycode-agents demo --run <run> --task <id> [--arm with]          # a readable transcript for the demo
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from whycode.comparison.runner import ARMS, RESULTS_DIR, ClaudeCodeAgent, demo_transcript, dry_run_lines, report
from whycode.comparison.runner import run_comparison
from whycode.comparison.tasks import TASKS_DIR, freeze, load_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whycode-agents", description=__doc__.split("\n\n")[0])
    parser.add_argument("--tasks-dir", type=Path, default=TASKS_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze", help="record the hash of every task record (refuses changed frozen records)")
    f.add_argument("--force", action="store_true", help="re-freeze records that changed (runs keep the old hash)")
    run = sub.add_parser("run", help="run tasks with and without the MCP tools")
    run.add_argument("--task", action="append", help="task id (repeatable; default: every task)")
    run.add_argument("--arms", default=",".join(ARMS), help="comma-separated: with,without (default: both)")
    run.add_argument("--repo", type=Path, default=os.environ.get("WHY_AGENT_REPO"),
                     help="a full CockroachDB clone holding the base commits (default: WHY_AGENT_REPO)")
    run.add_argument("--out", type=Path, default=RESULTS_DIR)
    run.add_argument("--model", default=os.environ.get("WHY_AGENT_MODEL"), help="claude --model (default: its own)")
    run.add_argument("--claude-bin", default=os.environ.get("CLAUDE_BIN", "claude"))
    run.add_argument("--max-turns", type=int, default=60)
    run.add_argument("--keep-workspaces", action="store_true")
    run.add_argument("--dry-run", action="store_true", help="print the workspaces and commands; run nothing")
    rep = sub.add_parser("report", help="re-make a run's table.md (applies grades.yaml)")
    rep.add_argument("--run", type=Path, required=True)
    demo = sub.add_parser("demo", help="write a readable transcript of one run")
    demo.add_argument("--run", type=Path, required=True)
    demo.add_argument("--task", required=True)
    demo.add_argument("--arm", choices=ARMS, default="with")
    args = parser.parse_args(argv)

    try:
        if args.command == "freeze":
            frozen = freeze(args.tasks_dir, force=args.force)
            print(f"{len(frozen)} task records frozen in {args.tasks_dir / 'lock.json'}")
            return 0
        if args.command == "report":
            print(report(args.run))
            return 0
        if args.command == "demo":
            (task,) = load_tasks(args.tasks_dir, [args.task])
            path = args.run / f"demo-{task.id}-{args.arm}.md"
            path.write_text(demo_transcript(args.run, task, args.arm))
            print(path)
            return 0
        tasks = load_tasks(args.tasks_dir, args.task)
        arms = [a for a in args.arms.split(",") if a]
        if set(arms) - set(ARMS):
            raise ValueError(f"unknown arms {sorted(set(arms) - set(ARMS))}")
        agent = ClaudeCodeAgent(claude_bin=args.claude_bin, model=args.model, max_turns=args.max_turns)
        if args.dry_run:
            print("\n".join(dry_run_lines(tasks, agent, args.repo, arms)))
            return 0
        problems = _preflight(args, arms)
        if problems:
            print("whycode-agents: cannot run:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        run_dir = run_comparison(tasks, agent, args.repo, args.out, arms, keep_workspaces=args.keep_workspaces)
        print((run_dir / "table.md").read_text())
        print(run_dir)
        return 0
    except ValueError as exc:
        print(f"whycode-agents: {exc}", file=sys.stderr)
        return 2


def _preflight(args: argparse.Namespace, arms: list[str]) -> list[str]:
    problems = []
    if args.repo is None or not (Path(args.repo) / ".git").exists():
        problems.append("--repo (or WHY_AGENT_REPO) must be a CockroachDB git clone holding the base commit")
    if shutil.which(args.claude_bin) is None and not Path(args.claude_bin).exists():
        problems.append(f"Claude Code not found ({args.claude_bin}); pass --claude-bin or set CLAUDE_BIN")
    if "with" in arms and not os.environ.get("NEO4J_PASSWORD"):
        problems.append("the `with` arm starts why-mcp over the real graph: export NEO4J_URI / NEO4J_PASSWORD")
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
