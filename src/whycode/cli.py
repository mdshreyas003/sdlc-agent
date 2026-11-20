"""`whycode` command line: build the graph, ask `why` without an MCP client.

    uv run whycode build                     # fixture history -> Neo4j, recorded extractions (no model)
    uv run whycode build --extractor anthropic   # same, extracting Decisions with Sonnet 5.5 (cached)
    uv run whycode why pkg/sql/schema_changer.go # prints the Answer contract as JSON
    uv run whycode supersession-report           # the supersession judge (Opus 5.5) vs explicit Supersession

Configuration comes from the environment (`whycode.config`). Ticket 02 adds `--history github`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from whycode.config import ConfigError, Settings


def _build(settings: Settings, args: argparse.Namespace) -> int:
    from whycode.build import build_graph
    from whycode.decisions import AnthropicDecisionProposer
    from whycode.fixtures import FIXTURE_DIR, FIXTURE_REPO, fixture_code_index, recorded_proposer
    from whycode.graph.store import GraphStore
    from whycode.history import load_history
    from whycode.history.fixture import FixtureHistorySource
    from whycode.llm import EXTRACTION_MODEL

    cutoff = dt.date.fromisoformat(args.cutoff) if args.cutoff else settings.cutoff
    extractor = args.extractor or settings.extractor
    proposer = (AnthropicDecisionProposer(settings.llm(), EXTRACTION_MODEL) if extractor == "anthropic"
                else recorded_proposer(cutoff))
    judge_kind = args.judge or extractor  # recorded judgments only cover recorded Decisions
    history = load_history(FixtureHistorySource(FIXTURE_DIR, repo=FIXTURE_REPO), cutoff)
    graph = build_graph(history, fixture_code_index(), proposer, _judge(settings, judge_kind))
    store = GraphStore(settings.driver(), settings.neo4j_database)
    store.replace(graph)
    print(json.dumps({"history": args.history, "cutoff": cutoff.isoformat(), "extractor": extractor,
                      "judge": judge_kind, "counts": store.counts()}, indent=2))
    return 0


def _judge(settings: Settings, kind: str):
    """The supersession judge: recorded fixture judgments, Opus 5.5, or none (explicit Supersession only)."""
    from whycode.fixtures import recorded_judge
    from whycode.llm import JUDGE_MODEL
    from whycode.supersession import AnthropicSupersessionJudge

    if kind == "anthropic":
        return AnthropicSupersessionJudge(settings.llm(), JUDGE_MODEL)
    return recorded_judge() if kind == "recorded" else None


def _supersession_report(settings: Settings, args: argparse.Namespace) -> int:
    from whycode.graph.store import GraphStore
    from whycode.supersession import judge_report

    graph = GraphStore(settings.driver(), settings.neo4j_database).snapshot()
    text = judge_report(graph, _judge(settings, args.judge)).markdown()
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


def _why(settings: Settings, args: argparse.Namespace) -> int:
    from whycode.answer.engine import AnswerEngine
    from whycode.answer.patterns import GraphReader

    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    answer = AnswerEngine(reader, settings.composer_impl()).why(args.anchor)
    print(answer.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="whycode", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build the graph into Neo4j (replaces what is there)")
    build.add_argument("--history", choices=["fixtures"], default="fixtures")
    build.add_argument("--extractor", choices=["recorded", "anthropic"], help="default: WHY_EXTRACTOR or recorded")
    build.add_argument("--cutoff", help="YYYY-MM-DD; default: WHY_CUTOFF or 2024-06-30")
    build.add_argument("--judge", choices=["recorded", "anthropic", "none"],
                       help="supersession judge; default: the same kind as the extractor")
    why = sub.add_parser("why", help="print the Answer for an Anchor (function, file, package or setting)")
    why.add_argument("anchor")
    report = sub.add_parser("supersession-report", help="score the supersession judge against explicit Supersession "
                                                        "in the built graph (precision, recall, disagreements)")
    report.add_argument("--judge", choices=["recorded", "anthropic"], default="anthropic")
    report.add_argument("--out", type=Path, help="also write the report (markdown) here")
    args = parser.parse_args(argv)
    commands = {"build": _build, "why": _why, "supersession-report": _supersession_report}
    try:
        return commands[args.command](Settings.from_env(), args)
    except ConfigError as exc:
        print(f"whycode: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
