"""What a system under test is, and how answers are collected from it.

A system is any callable from `Query` to the answer contract (`Answer`), optionally wrapped in
`Answered` to report model usage for the cost column. Our system plugs in through
`whycode.answer.systems.scoreboard_system`; the baselines live in `whycode.eval.rag`, `whycode.eval.llm_alone`
and `whycode.eval.git_agent`.

Every system must honour the whole query: answer as of `as_of` (None = all history, including
the Held-out Window) and treat every node id in `exclude` as absent (ablation).
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from whycode.contract import Anchor, Answer
from whycode.eval.gold import Case
from whycode.eval.models import Usage


class Query(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    anchor: Anchor | None = None
    as_of: dt.date | None = None
    exclude: frozenset[str] = frozenset()

    @classmethod
    def for_case(cls, case: Case) -> Query:
        return cls(question=case.question, anchor=case.anchor, as_of=case.as_of, exclude=case.exclude)


@dataclass(frozen=True)
class Answered:
    answer: Answer
    usage: Usage | None = None


@dataclass(frozen=True)
class System:
    name: str
    run: Callable[[Query], Answer | Answered]
    models: Mapping[str, str] = field(default_factory=dict)  # role -> model id, printed in the report header


class AnswerRecord(BaseModel):
    case_id: str
    system: str
    answer: Answer | None
    seconds: float
    usage: Usage | None = None
    error: str | None = None


def read_records(path: Path) -> list[AnswerRecord]:
    if not path.exists():
        return []
    return [AnswerRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def collect(cases: Sequence[Case], systems: Sequence[System], path: Path,
            clock: Callable[[], float] = time.perf_counter) -> list[AnswerRecord]:
    """Ask every system every case, appending one line per answer; pairs already in `path` are skipped (resume).

    A failing call becomes an error record, so one failure never loses the run.
    """
    done = {(r.case_id, r.system) for r in read_records(path)}
    with path.open("a", encoding="utf-8") as out:
        for case in cases:
            query = Query.for_case(case)
            for system in systems:
                if (case.id, system.name) in done:
                    continue
                start = clock()
                try:
                    result = system.run(query)
                    answered = result if isinstance(result, Answered) else Answered(result)
                    rec = AnswerRecord(case_id=case.id, system=system.name, answer=answered.answer,
                                       seconds=round(clock() - start, 3), usage=answered.usage)
                except Exception as error:  # noqa: BLE001  counted in the report as an error
                    rec = AnswerRecord(case_id=case.id, system=system.name, answer=None,
                                       seconds=round(clock() - start, 3),
                                       error=f"{type(error).__name__}: {str(error)[:300]}")
                out.write(rec.model_dump_json() + "\n")
                out.flush()
    return read_records(path)


def to_jsonl(rows: Sequence[BaseModel]) -> str:
    return "".join(r.model_dump_json() + "\n" for r in rows)


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
