"""The agent comparison runner, driven with a scripted coding agent over a git repo of the fixture code and the
fixture graph. Assertions are on what a human reads: the run records, the with/without table and the committed
task records."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from whycode.answer.fence import FenceChecker
from whycode.answer.patterns import GraphReader
from whycode.comparison import cli
from whycode.comparison.runner import AgentTranscript, claude_command, parse_stream_json, run_comparison
from whycode.comparison.tasks import TASKS_DIR, Check, Grading, Pitfall, TaskRecord, freeze, grade, load_tasks
from whycode.fixtures import FIXTURE_DIR, fixture_graph, proposed_diff
from whycode.graph.store import GraphStore

CUTOFF_COMMIT = "d13253527955eaa2da09394b8a2729627ab25c48"
OLD_LOOP = """		opts.MaxBackoff = schemaChangeJobMaxRetryBackoff.Get(sc.settings)
		err := sc.step(ctx)
		if err == nil || isPermanentSchemaChangeError(err) {
			return err
		}
		log.Warningf(ctx, "schema change job will retry with backoff: %v", err)
"""
HOT_LOOP = """		if err := sc.step(ctx); err != nil && !isPermanentSchemaChangeError(err) {
			continue
		}
		return nil
"""
FASTER_START = "InitialBackoff: 20 * time.Millisecond"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path) -> tuple[Path, str]:
    root = tmp_path / "cockroach"
    shutil.copytree(FIXTURE_DIR / "code", root)
    git(root, "init", "-q")
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")
    return root, git(root, "rev-parse", "HEAD").strip()


def backoff_task(base: str) -> TaskRecord:
    return TaskRecord(
        id="T-retry-backoff", origin="hand-built",
        task="Schema change jobs take up to 20 seconds to notice that a transient error is gone. Make "
             "SchemaChanger.exec retry immediately instead of backing off.",
        base_commit=base,
        pitfall=Pitfall(summary="Retrying immediately hot-loops while a descriptor is offline (#98001).",
                        evidence=["issue:98001", "pr:98100"]),
        grading=Grading(rule="Repeats the pitfall when the diff stops reading the backoff cap in exec.",
                        checks=[Check(file="pkg/sql/schema_changer.go", removes=r"schemaChangeJobMaxRetryBackoff\.Get",
                                      unless_adds=r"schemaChangeJobMaxRetryBackoff\.Get")]),
    )


class ScriptedAgent:
    """Removes the backoff (the pitfall). With tools, it checks its diff and, when warned, restores the loop
    and only shortens the initial backoff instead."""

    name = "scripted"

    def __init__(self, check_change):
        self.check_change = check_change

    def run(self, prompt: str, workspace: Path, with_tools: bool) -> AgentTranscript:
        path = workspace / "pkg/sql/schema_changer.go"
        original = path.read_text()
        path.write_text(original.replace(OLD_LOOP, HOT_LOOP))
        events = [{"type": "text", "text": "Removing the backoff so failed steps retry immediately."}]
        if with_tools:
            diff = git(workspace, "diff")
            result = self.check_change(diff)
            events.append({"type": "tool_call", "name": "check_change", "input": {"diff": diff}, "output": result})
            if result["warnings"]:
                path.write_text(original.replace(FASTER_START, "InitialBackoff: 5 * time.Millisecond"))
                events.append({"type": "text", "text": "A Fence Warning cites #98001: keeping the capped backoff."})
        return AgentTranscript(events=events, model="scripted-1")


@pytest.fixture(scope="module")
def checker(neo4j_driver):
    neo4j_driver.execute_query("MATCH (n) DETACH DELETE n")
    GraphStore(neo4j_driver).replace(fixture_graph())
    return FenceChecker(GraphReader(neo4j_driver))


def test_a_scripted_agent_repeats_the_pitfall_without_the_tools_and_changes_course_with_them(tmp_path, repo, checker):
    root, base = repo
    task = backoff_task(base)
    tasks_dir = tmp_path / "tasks"
    task.write(tasks_dir)
    freeze(tasks_dir)

    run_dir = run_comparison(load_tasks(tasks_dir), ScriptedAgent(lambda d: checker.check(d).model_dump(mode="json")),
                             repo=root, out=tmp_path / "results")

    runs = {r["arm"]: r for r in map(json.loads, (run_dir / "runs.jsonl").read_text().splitlines())}
    assert set(runs) == {"with", "without"}
    assert runs["without"]["pitfall_repeated"] is True
    assert runs["with"]["pitfall_repeated"] is False
    assert runs["with"]["check_change_calls"] == 1
    assert runs["with"]["warnings_seen"] >= 1
    assert runs["with"]["course_changed"] is True
    assert runs["without"]["course_changed"] is False
    assert runs["with"]["task_sha256"] == runs["without"]["task_sha256"]
    final = (run_dir / runs["with"]["diff"]).read_text()
    assert "+\topts := retry.Options{InitialBackoff: 5 * time.Millisecond, Multiplier: 1.5}" in final.splitlines()
    assert not [line for line in final.splitlines() if line.startswith("-") and "MaxRetryBackoff.Get" in line]
    table = (run_dir / "table.md").read_text()
    assert "| with tools | 1 | 0 | 1 |" in table
    assert "| without tools | 1 | 1 | - |" in table
    # The workspaces were removed from the repo afterwards.
    assert git(root, "worktree", "list").count("\n") == 1
    # The demo transcript shows the warning that changed course.
    assert cli.main(["--tasks-dir", str(tasks_dir), "demo", "--run", str(run_dir), "--task", task.id]) == 0
    demo = (run_dir / f"demo-{task.id}-with.md").read_text()
    assert "Fence Warning (reverses, High)" in demo and "issue:98001" in demo and "avoided" in demo


def test_a_run_the_rule_leaves_open_is_counted_once_a_human_grades_it(tmp_path, repo):
    root, base = repo
    task = backoff_task(base).model_copy(update={"id": "T-human", "grading": Grading(rule="judge it", human="read it")})
    tasks_dir = tmp_path / "tasks"
    task.write(tasks_dir)
    freeze(tasks_dir)

    run_dir = run_comparison(load_tasks(tasks_dir), ScriptedAgent(None), repo=root, out=tmp_path / "results",
                             arms=["without"])
    assert "| without tools | 0 | 0 | - | 1 | 0 |" in (run_dir / "table.md").read_text()

    (run_dir / "grades.yaml").write_text("T-human: {without: true}\n")
    assert cli.main(["report", "--run", str(run_dir)]) == 0
    assert "| without tools | 1 | 1 | - | 0 | 0 |" in (run_dir / "table.md").read_text()


def test_a_task_record_changed_after_it_was_frozen_is_refused(tmp_path, repo):
    root, base = repo
    tasks_dir = tmp_path / "tasks"
    backoff_task(base).write(tasks_dir)
    freeze(tasks_dir)
    record = tasks_dir / "T-retry-backoff.yaml"
    record.write_text(record.read_text().replace("hot-loops", "may hot-loop"))

    with pytest.raises(ValueError, match="changed after it was frozen"):
        load_tasks(tasks_dir)


def test_grading_recognises_the_pitfall_in_a_diff_and_not_in_a_safe_one():
    grading = backoff_task(CUTOFF_COMMIT).grading

    assert grade(grading, proposed_diff("remove-retry-backoff")).repeated is True
    assert grade(grading, proposed_diff("raise-backoff-cap-default")).repeated is False
    assert grade(Grading(rule="only a human can tell", human="run the benchmark"), "").repeated is None


def test_the_committed_task_records_are_complete_frozen_and_graded_by_their_own_examples():
    tasks = load_tasks(TASKS_DIR)  # refuses records changed after freezing

    assert len(tasks) >= 7
    assert {t.origin for t in tasks} == {"real", "hand-built"}
    for t in tasks:
        assert t.task.strip() and t.pitfall.summary.strip() and t.pitfall.evidence, t.id
        assert t.base_commit == CUTOFF_COMMIT, t.id  # every agent starts from the pre-cutoff code
        assert t.grading.rule.strip() and (t.grading.checks or t.grading.human), t.id
        if t.origin == "real":
            assert t.real_change and t.real_change["merged"] > "2024-06-30", t.id
        for example in t.example_diffs.get("repeats", []):
            assert grade(t.grading, example).repeated is True, t.id
        for example in t.example_diffs.get("avoids", []):
            assert grade(t.grading, example).repeated is False, t.id


def test_claude_code_gets_the_why_server_only_in_the_with_arm(tmp_path):
    with_tools = claude_command("Do the task", tmp_path / "with.json", with_tools=True, model="claude-opus-5-5")
    without = claude_command("Do the task", tmp_path / "without.json", with_tools=False, model="claude-opus-5-5")

    assert "--strict-mcp-config" in with_tools and "--strict-mcp-config" in without
    assert with_tools[with_tools.index("--mcp-config") + 1] == str(tmp_path / "with.json")
    assert "mcp__why__check_change" in with_tools[with_tools.index("--allowedTools") + 1]
    assert "mcp__why__check_change" not in " ".join(without)
    assert without[without.index("--model") + 1] == "claude-opus-5-5"


def test_a_claude_code_stream_becomes_tool_calls_with_their_results():
    lines = [
        {"type": "system", "subtype": "init", "model": "claude-opus-5-5", "tools": ["Edit", "mcp__why__check_change"]},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Checking my diff."},
            {"type": "tool_use", "id": "t1", "name": "mcp__why__check_change", "input": {"diff": "--- a/x"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [
            {"type": "text", "text": json.dumps({"touched": [], "warnings": [{"decision_id": "decision:1"}]})}]}]}},
        {"type": "result", "subtype": "success", "total_cost_usd": 0.42, "num_turns": 3, "result": "Done."},
    ]

    transcript = parse_stream_json(json.dumps(line) for line in lines)

    call = next(e for e in transcript.events if e["type"] == "tool_call")
    assert (call["name"], call["input"], call["output"]["warnings"]) == ("check_change", {"diff": "--- a/x"},
                                                                         [{"decision_id": "decision:1"}])
    assert (transcript.model, transcript.cost_usd, transcript.turns) == ("claude-opus-5-5", 0.42, 3)


def test_a_dry_run_prints_both_arms_for_a_task_without_running_an_agent(capsys):
    assert cli.main(["run", "--task", "H1-clock-errors-permanent", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert out.count("H1-clock-errors-permanent") >= 2
    assert "[with]" in out and "[without]" in out
    assert "--mcp-config" in out
