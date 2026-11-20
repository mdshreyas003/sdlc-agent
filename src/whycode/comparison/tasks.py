"""Agent comparison task records and their grading.

A record (`eval/agent-comparison/tasks/<id>.yaml`) holds everything decided before any run:

- `task`: the text the coding agent gets, verbatim (for a real task, the issue or PR motivation that led to the
  real post-cutoff Change; nothing that names the pitfall);
- `base_commit`: the pre-cutoff commit the agent works on (the commit the graph's code index was built from);
- `real_change` (real tasks): the post-cutoff Change and what reverted it or which Incident it caused;
- `pitfall`: what the real Change (or, for a hand-built task, the naive edit) got wrong, with the history that
  shows it (`evidence`: node ids in the graph's convention, `pr:<n>`, `issue:<n>`, `commit:<sha>`);
- `grading`: the rule a human reads, and the mechanical `checks` on the agent's final diff. A check fires when, in
  a file matching `file`, a removed line matches `removes`, an added line matches `adds`, and no added line
  matches `unless_adds` (each optional). The pitfall is repeated when any check fires. When no check fires, the
  result is "not repeated", or "needs a human" for a record with `human` instructions (the checks are then only
  a proxy, e.g. for a performance regression);
- `examples`: paths (relative to the tasks directory) of diffs that repeat (`repeats`) or avoid (`avoids`) the
  pitfall; the tests hold the checks to them.

`freeze` records a sha256 of each record and its example diffs in `lock.json`; `load_tasks` refuses a record that
is not frozen or that changed after it was frozen, and every run record carries the hash, so a record cannot be
tuned after a run.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from whycode.answer.fence import parse_diff

COMPARISON_DIR = Path(__file__).resolve().parents[3] / "eval" / "agent-comparison"
TASKS_DIR = COMPARISON_DIR / "tasks"
LOCK_FILE = "lock.json"


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Check(_Record):
    file: str = "*"
    removes: str | None = None
    adds: str | None = None
    unless_adds: str | None = None


class Grading(_Record):
    rule: str
    checks: list[Check] = []
    human: str | None = None
    """How a human decides when no check fires (the checks are then a proxy, not the whole rule)."""


class Pitfall(_Record):
    summary: str
    evidence: list[str]
    details: str = ""


class TaskRecord(_Record):
    id: str
    origin: Literal["real", "hand-built"]
    task: str
    base_commit: str
    pitfall: Pitfall
    grading: Grading
    real_change: dict[str, str] | None = None
    examples: dict[Literal["repeats", "avoids"], list[str]] = {}
    notes: str = ""
    sha256: str = ""
    """Of the record and its examples as frozen; set by `load_tasks`, never written."""
    example_diffs: dict[str, list[str]] = {}
    """The example diffs' text; set by `load_tasks`, never written."""

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.id}.yaml"
        data = self.model_dump(exclude={"sha256", "example_diffs"}, exclude_defaults=True)
        path.write_text(yaml.dump(data, Dumper=_BlockDumper, sort_keys=False, allow_unicode=True, width=110),
                        encoding="utf-8")
        return path


class _BlockDumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, value: str):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|" if "\n" in value else None)


_BlockDumper.add_representer(str, _str)


def _examples(path: Path) -> list[Path]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [path.parent / p for kind in sorted(data.get("examples") or {}) for p in data["examples"][kind]]


def _digest(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes())
    for example in _examples(path):
        h.update(b"\0" + example.read_bytes())
    return h.hexdigest()


def freeze(directory: Path = TASKS_DIR, force: bool = False) -> dict[str, str]:
    """Record the hash of every task record not frozen yet. A frozen record that changed is refused unless
    `force` (then every run made before carries the old hash)."""
    lock_path = directory / LOCK_FILE
    lock = json.loads(lock_path.read_text()) if lock_path.exists() else {"frozen": {}}
    for path in sorted(directory.glob("*.yaml")):
        task_id, digest = path.stem, _digest(path)
        old = lock["frozen"].get(task_id)
        if old and old["sha256"] != digest and not force:
            raise ValueError(f"task {task_id} changed after it was frozen on {old['at']}; pass force to re-freeze")
        if not old or old["sha256"] != digest:
            lock["frozen"][task_id] = {"sha256": digest, "at": dt.date.today().isoformat()}
    lock_path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return {k: v["sha256"] for k, v in lock["frozen"].items()}


def load_tasks(directory: Path = TASKS_DIR, ids: list[str] | None = None) -> list[TaskRecord]:
    lock_path = directory / LOCK_FILE
    frozen = json.loads(lock_path.read_text())["frozen"] if lock_path.exists() else {}
    out = []
    for path in sorted(directory.glob("*.yaml")):
        if ids and path.stem not in ids:
            continue
        digest = _digest(path)
        if path.stem not in frozen:
            raise ValueError(f"task {path.stem} is not frozen: run `whycode-agents freeze` before any run")
        if frozen[path.stem]["sha256"] != digest:
            raise ValueError(f"task {path.stem} changed after it was frozen on {frozen[path.stem]['at']}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        diffs = {kind: [(directory / p).read_text(encoding="utf-8") for p in paths]
                 for kind, paths in (data.get("examples") or {}).items()}
        record = TaskRecord.model_validate({**data, "sha256": digest, "example_diffs": diffs})
        if record.id != path.stem:
            raise ValueError(f"{path.name}: id {record.id} does not match the file name")
        out.append(record)
    if ids and {t.id for t in out} != set(ids):
        raise ValueError(f"unknown task ids: {sorted(set(ids) - {t.id for t in out})}")
    return out


@dataclass(frozen=True, slots=True)
class Grade:
    repeated: bool | None
    """True: the pitfall is repeated; False: it is not; None: no check fired and a human must decide."""
    fired: list[str] = field(default_factory=list)


def grade(grading: Grading, diff: str) -> Grade:
    fired = []
    for i, check in enumerate(grading.checks, 1):
        for change in parse_diff(diff):
            if not fnmatch.fnmatch(change.path, check.file):
                continue
            lines = (change.patch or "").splitlines()
            added = [line[1:] for line in lines if line.startswith("+")]
            removed = [line[1:] for line in lines if line.startswith("-")]
            if check.removes and not any(re.search(check.removes, line) for line in removed):
                continue
            if check.adds and not any(re.search(check.adds, line) for line in added):
                continue
            if check.unless_adds and any(re.search(check.unless_adds, line) for line in added):
                continue
            fired.append(f"check {i} in {change.path}")
    if fired:
        return Grade(True, fired)
    return Grade(None if grading.human else False)
