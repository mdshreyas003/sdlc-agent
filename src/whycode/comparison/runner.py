"""Run agent comparison tasks with and without our MCP tools, and summarise the runs.

For each task and arm (`with`: the `why` MCP server is available; `without`: no MCP server at all), the runner
checks out the task's pre-cutoff commit in a fresh git worktree of a CockroachDB clone, gives the coding agent the
same prompt (the task text), and keeps the transcript and the final diff (everything the agent changed against
the base commit, committed or not, new files included). It then grades the diff with the task's committed rule
and reads the transcript for `check_change` calls:

- `pitfall_repeated`: the grade of the final diff (None: a human must decide; see `grades.yaml` below);
- `warnings_seen`: Fence Warnings returned to the agent;
- `course_changed`: a `check_change` call returned warnings on a diff that repeated the pitfall, and the final
  diff does not.

Run directory (`eval/agent-comparison/results/<time>-<agent>/`): `manifest.json`, `runs.jsonl`, `diffs/`,
`transcripts/` (normalised events, one JSON object per line), `table.md`. A human grades the runs the rule leaves
open in `grades.yaml` (`<task id>: {with: true|false, without: true|false}`) and re-runs `whycode-agents report`.

The agent is a seam (`CodingAgent`): `ClaudeCodeAgent` runs Claude Code headless (`claude -p`, stream-json), with
`--strict-mcp-config` so only the `why` server (with) or nothing (without) is reachable; tests use a scripted
agent. Nothing here calls a model itself.
"""

from __future__ import annotations

import datetime as dt
import json
import shlex
import subprocess
import tempfile
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from whycode.comparison.tasks import COMPARISON_DIR, TaskRecord, grade

ARMS = ("with", "without")
RESULTS_DIR = COMPARISON_DIR / "results"
WHYCODE_DIR = COMPARISON_DIR.parents[1]
PROMPT = """You are working in a checkout of the CockroachDB repository at commit {commit}. Make the change the \
task below asks for by editing the code in place. Do not commit, and do not run the Go build or tests (the \
toolchain is not set up). When you are done, summarise what you changed and why.

Task:

{task}
"""
BASE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(git diff:*)", "Bash(git status:*)", "Bash(git log:*)",
              "Bash(git show:*)", "Bash(grep:*)", "Bash(ls:*)"]
WHY_TOOLS = ["mcp__why__why", "mcp__why__check_change"]
MCP_ENV = {"NEO4J_URI": "bolt://localhost:7687", "NEO4J_USERNAME": "neo4j", "NEO4J_PASSWORD": "",
           "NEO4J_DATABASE": "neo4j", "WHY_COMPOSER": "anthropic", "ANTHROPIC_API_KEY": ""}
"""The `why-mcp` server's environment and defaults, as in the repo's `.mcp.json`."""


@dataclass
class AgentTranscript:
    """Normalised events: {"type": "text", "text"}, {"type": "tool_call", "name", "input", "output", "is_error"}
    (MCP tool names without the `mcp__why__` prefix), {"type": "result", "text"}."""

    events: list[dict[str, Any]] = field(default_factory=list)
    model: str | None = None
    cost_usd: float | None = None
    turns: int | None = None


class CodingAgent(Protocol):
    name: str

    def run(self, prompt: str, workspace: Path, with_tools: bool) -> AgentTranscript: ...


# --- Claude Code ----------------------------------------------------------------------------------------------

def mcp_config(with_tools: bool, whycode_dir: Path = WHYCODE_DIR) -> dict[str, Any]:
    """The `--mcp-config` for an arm. Secrets stay in the environment: Claude Code expands `${VAR}`."""
    if not with_tools:
        return {"mcpServers": {}}
    return {"mcpServers": {"why": {
        "type": "stdio", "command": "uv", "args": ["run", "--directory", str(whycode_dir), "why-mcp"],
        "env": {name: f"${{{name}:-{default}}}" for name, default in MCP_ENV.items()},
    }}}


def claude_command(prompt: str, config: Path, with_tools: bool, model: str | None = None, max_turns: int = 60,
                   claude_bin: str = "claude") -> list[str]:
    tools = BASE_TOOLS + (WHY_TOOLS if with_tools else [])
    command = [claude_bin, "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--permission-mode", "acceptEdits", "--mcp-config", str(config), "--strict-mcp-config",
               "--allowedTools", ",".join(tools), "--max-turns", str(max_turns)]
    return command + (["--model", model] if model else [])


def _tool_name(name: str) -> str:
    return name.removeprefix("mcp__why__")


def _tool_output(content: Any) -> Any:
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if isinstance(content, str):
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content


def parse_stream_json(lines: Iterable[str]) -> AgentTranscript:
    """Claude Code's `--output-format stream-json` lines -> normalised events."""
    transcript = AgentTranscript()
    pending: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        kind = msg.get("type")
        content = (msg.get("message") or {}).get("content")
        if kind == "system" and msg.get("subtype") == "init":
            transcript.model = msg.get("model")
        elif kind == "assistant" and isinstance(content, list):
            for block in content:
                if block.get("type") == "text" and block.get("text"):
                    transcript.events.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    event = {"type": "tool_call", "name": _tool_name(block.get("name", "")),
                             "input": block.get("input") or {}, "output": None, "is_error": False}
                    pending[block.get("id", "")] = event
                    transcript.events.append(event)
        elif kind == "user" and isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result" and (event := pending.get(block.get("tool_use_id", ""))):
                    event["output"] = _tool_output(block.get("content"))
                    event["is_error"] = bool(block.get("is_error"))
        elif kind == "result":
            transcript.cost_usd = msg.get("total_cost_usd")
            transcript.turns = msg.get("num_turns")
            transcript.events.append({"type": "result", "text": msg.get("result")})
    return transcript


class ClaudeCodeAgent:
    """Claude Code in print mode. Needs `claude` (or `--claude-bin`) logged in; the `with` arm also needs the
    graph in Neo4j (NEO4J_* in the environment) for the `why-mcp` server it starts."""

    name = "claude-code"

    def __init__(self, claude_bin: str = "claude", model: str | None = None, max_turns: int = 60,
                 timeout_s: int = 3600, whycode_dir: Path = WHYCODE_DIR):
        self.claude_bin, self.model, self.max_turns = claude_bin, model, max_turns
        self.timeout_s, self.whycode_dir = timeout_s, whycode_dir

    def command(self, prompt: str, config: Path, with_tools: bool) -> list[str]:
        return claude_command(prompt, config, with_tools, self.model, self.max_turns, self.claude_bin)

    def run(self, prompt: str, workspace: Path, with_tools: bool) -> AgentTranscript:
        config = workspace.parent / f"{workspace.name}.mcp.json"
        config.write_text(json.dumps(mcp_config(with_tools, self.whycode_dir), indent=2))
        proc = subprocess.run(self.command(prompt, config, with_tools), cwd=workspace, capture_output=True,
                              text=True, timeout=self.timeout_s, check=False)
        transcript = parse_stream_json(proc.stdout.splitlines())
        if proc.returncode != 0 and not transcript.events:
            raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[-2000:]}")
        return transcript


# --- workspaces -----------------------------------------------------------------------------------------------

def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout


@contextmanager
def workspace(repo: Path, commit: str, root: Path, name: str, keep: bool = False) -> Iterator[Path]:
    """A detached git worktree of `repo` at `commit`, removed afterwards unless `keep`."""
    path = root / name
    _git(repo, "worktree", "add", "--detach", "--force", str(path), commit)
    try:
        yield path
    finally:
        if not keep:
            _git(repo, "worktree", "remove", "--force", str(path))


def final_diff(path: Path, base_commit: str) -> str:
    """Everything the agent changed against the base commit: committed or not, new files included."""
    _git(path, "add", "--all", "--intent-to-add")
    return _git(path, "-c", "core.quotepath=off", "diff", "--no-color", "--no-ext-diff", base_commit)


# --- runs -----------------------------------------------------------------------------------------------------

def _warnings(output: Any) -> list[dict[str, Any]]:
    return list(output.get("warnings") or []) if isinstance(output, dict) else []


def analyse(task: TaskRecord, transcript: AgentTranscript, diff: str) -> dict[str, Any]:
    result = grade(task.grading, diff)
    calls = [e for e in transcript.events if e["type"] == "tool_call"]
    checks = [e for e in calls if e["name"] == "check_change"]
    warned_on_pitfall = any(_warnings(e.get("output")) and
                            grade(task.grading, str((e.get("input") or {}).get("diff", ""))).repeated for e in checks)
    if result.repeated is None:
        course = None if warned_on_pitfall else False
    else:
        course = result.repeated is False and warned_on_pitfall
    return {
        "pitfall_repeated": result.repeated,
        "fired": result.fired,
        "graded_by": None if result.repeated is None else "rule",
        "check_change_calls": len(checks),
        "why_calls": sum(1 for e in calls if e["name"] == "why"),
        "warnings_seen": sum(len(_warnings(e.get("output"))) for e in checks),
        "course_changed": course,
    }


def prompt_for(task: TaskRecord) -> str:
    return PROMPT.format(commit=task.base_commit, task=task.task.strip())


def run_comparison(tasks: list[TaskRecord], agent: CodingAgent, repo: Path, out: Path = RESULTS_DIR,
                   arms: Iterable[str] = ARMS, keep_workspaces: bool = False,
                   workspace_root: Path | None = None) -> Path:
    """Run every task in every arm; returns the run directory (with its `table.md`)."""
    started = dt.datetime.now(dt.UTC)
    run_dir = out / f"{started:%Y%m%dT%H%M%SZ}-{agent.name}"
    (run_dir / "diffs").mkdir(parents=True)
    (run_dir / "transcripts").mkdir()
    manifest = {"agent": agent.name, "started": started.isoformat(), "repo": str(repo), "arms": list(arms),
                "tasks": {t.id: t.sha256 for t in tasks}, "whycode_commit": _whycode_commit()}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    root = workspace_root or Path(tempfile.mkdtemp(prefix="whycode-agents-"))
    with (run_dir / "runs.jsonl").open("w") as runs:
        for task in tasks:
            for arm in manifest["arms"]:
                record = _run_one(task, arm, agent, repo, run_dir, root, keep_workspaces)
                runs.write(json.dumps(record) + "\n")
                runs.flush()
    report(run_dir)
    return run_dir


def _run_one(task: TaskRecord, arm: str, agent: CodingAgent, repo: Path, run_dir: Path, root: Path,
             keep: bool) -> dict[str, Any]:
    name = f"{task.id}-{arm}"
    record: dict[str, Any] = {"task": task.id, "origin": task.origin, "task_sha256": task.sha256, "arm": arm,
                              "agent": agent.name, "base_commit": task.base_commit}
    started = time.monotonic()
    try:
        with workspace(repo, task.base_commit, root, name, keep) as path:
            transcript = agent.run(prompt_for(task), path, with_tools=arm == "with")
            diff = final_diff(path, task.base_commit)
    except Exception as exc:  # noqa: BLE001 - one failed run must not lose the others
        return {**record, "error": f"{type(exc).__name__}: {exc}", "pitfall_repeated": None,
                "seconds": round(time.monotonic() - started, 1)}
    (run_dir / "diffs" / f"{name}.diff").write_text(diff)
    with (run_dir / "transcripts" / f"{name}.jsonl").open("w") as f:
        for event in transcript.events:
            f.write(json.dumps(event) + "\n")
    return {**record, "model": transcript.model, **analyse(task, transcript, diff),
            "cost_usd": transcript.cost_usd, "turns": transcript.turns,
            "seconds": round(time.monotonic() - started, 1),
            "diff": f"diffs/{name}.diff", "transcript": f"transcripts/{name}.jsonl"}


def _whycode_commit() -> str | None:
    try:
        return _git(WHYCODE_DIR, "rev-parse", "HEAD").strip()
    except RuntimeError:
        return None


# --- report and demo ------------------------------------------------------------------------------------------

def load_runs(run_dir: Path) -> list[dict[str, Any]]:
    """The run records, with a human's grades (`grades.yaml`) filled in where the rule left the run open."""
    runs = [json.loads(line) for line in (run_dir / "runs.jsonl").read_text().splitlines() if line.strip()]
    grades_path = run_dir / "grades.yaml"
    grades = (yaml.safe_load(grades_path.read_text()) or {}) if grades_path.exists() else {}
    for r in runs:
        human = (grades.get(r["task"]) or {}).get(r["arm"])
        if r.get("pitfall_repeated") is None and isinstance(human, bool) and not r.get("error"):
            r["pitfall_repeated"], r["graded_by"] = human, "human"
            if r.get("course_changed") is None and r.get("warnings_seen"):
                r["course_changed"] = not human
    return runs


def _cell(value: Any) -> str:
    return {True: "repeated", False: "avoided", None: "needs human"}.get(value, str(value))


def report(run_dir: Path) -> str:
    runs = load_runs(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    models = sorted({r.get("model") or "?" for r in runs if not r.get("error")})
    lines = [f"# Agent comparison: {run_dir.name}", "",
             f"Agent: {manifest['agent']} ({', '.join(models) or '?'}). Tasks: {len(manifest['tasks'])}. Grading: the "
             "committed rules in `eval/agent-comparison/tasks/` (hashes in `runs.jsonl`).", "",
             "| arm | tasks graded | pitfalls repeated | warnings that changed course | needs a human | failed |",
             "|---|---|---|---|---|---|"]
    for arm in manifest["arms"]:
        mine = [r for r in runs if r["arm"] == arm]
        graded = [r for r in mine if r.get("pitfall_repeated") is not None]
        changed = sum(1 for r in mine if r.get("course_changed")) if arm == "with" else "-"
        lines.append(f"| {arm} tools | {len(graded)} | {sum(1 for r in graded if r['pitfall_repeated'])} | {changed} "
                     f"| {sum(1 for r in mine if r.get('pitfall_repeated') is None and not r.get('error'))} "
                     f"| {sum(1 for r in mine if r.get('error'))} |")
    lines += ["", "| task | origin | without tools | with tools | check_change calls | warnings seen | course changed |",
              "|---|---|---|---|---|---|---|"]
    for task_id in manifest["tasks"]:
        by_arm = {r["arm"]: r for r in runs if r["task"] == task_id}
        w, wo = by_arm.get("with", {}), by_arm.get("without", {})
        origin = (w or wo).get("origin", "")
        lines.append(f"| {task_id} | {origin} | {_cell(wo.get('pitfall_repeated')) if wo else '-'} "
                     f"| {_cell(w.get('pitfall_repeated')) if w else '-'} | {w.get('check_change_calls', '-')} "
                     f"| {w.get('warnings_seen', '-')} | {_cell_course(w.get('course_changed')) if w else '-'} |")
    text = "\n".join(lines) + "\n"
    (run_dir / "table.md").write_text(text)
    return text


def _cell_course(value: Any) -> str:
    return {True: "yes", False: "no", None: "needs human"}[value]


def demo_transcript(run_dir: Path, task: TaskRecord, arm: str = "with", max_diff_lines: int = 60) -> str:
    """A readable transcript of one run, for the demo."""
    run = next(r for r in load_runs(run_dir) if r["task"] == task.id and r["arm"] == arm)
    events = [json.loads(line) for line in (run_dir / run["transcript"]).read_text().splitlines() if line.strip()]
    out = [f"# {task.id} ({arm} tools): {_cell(run['pitfall_repeated'])}", "",
           f"Agent: {run['agent']} ({run.get('model') or '?'}), base commit `{task.base_commit[:12]}`.", "",
           "## Task", "", task.task.strip(), "", "## Real pitfall", "", task.pitfall.summary.strip(), "",
           "## Transcript", ""]
    for event in events:
        if event["type"] == "text":
            out += ["> " + line for line in event["text"].strip().splitlines()] + [""]
        elif event["type"] == "tool_call" and event["name"] == "check_change":
            diff = str((event.get("input") or {}).get("diff", "")).splitlines()
            out += ["**check_change** on:", "", "```diff", *diff[:max_diff_lines],
                    *(["..."] if len(diff) > max_diff_lines else []), "```", ""]
            for w in _warnings(event.get("output")):
                out.append(f"- Fence Warning ({w.get('kind')}, {w.get('confidence')}): {w.get('choice')}. "
                           f"\"{w.get('quote')}\" ({w.get('discussion_id')}; incidents: "
                           f"{', '.join(w.get('incident_ids') or []) or 'none'}). {w.get('reason')}")
            out.append("")
        elif event["type"] == "tool_call":
            out += [f"*{event['name']}* `{json.dumps(event.get('input'))[:200]}`", ""]
    diff = (run_dir / run["diff"]).read_text().splitlines()
    out += ["## Final diff", "", "```diff", *diff[:max_diff_lines * 2], *(["..."] if len(diff) > max_diff_lines * 2
                                                                         else []), "```", "",
            f"Grade: {_cell(run['pitfall_repeated'])} ({run.get('graded_by') or 'open'}; {', '.join(run.get('fired') or [])})."]
    return "\n".join(out) + "\n"


def dry_run_lines(tasks: list[TaskRecord], agent: ClaudeCodeAgent, repo: Path | None,
                  arms: Iterable[str] = ARMS) -> list[str]:
    lines = []
    for task in tasks:
        for arm in arms:
            config = Path(f"<workspaces>/{task.id}-{arm}.mcp.json")
            command = agent.command(prompt_for(task), config, with_tools=arm == "with")
            command[2] = f"<prompt: {len(command[2])} chars>"
            lines.append(f"[{arm}] {task.id}: git -C {repo or '<repo>'} worktree add --detach <workspace> "
                         f"{task.base_commit}\n    {shlex.join(command)}\n    mcp config: "
                         f"{json.dumps(mcp_config(arm == 'with', agent.whycode_dir))}")
    return lines
