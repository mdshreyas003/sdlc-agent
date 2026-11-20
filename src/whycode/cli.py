"""`whycode` command line: ingest and build the graph, ask `why` without an MCP client, audit citations.

    uv run whycode build                          # fixture history -> Neo4j, recorded extractions (no model)
    uv run whycode build --extractor anthropic    # same, extracting Decisions with Sonnet 5.5 (cached)
    uv run whycode fetch [--limit N]              # real slice: fill the GitHub cache (resumable; re-run after a stop)
    uv run whycode build --history github         # real slice: cache -> graph -> Neo4j, corpus and counts files
    uv run whycode why pkg/sql/schema_changer.go  # prints the Answer contract as JSON
    git diff | uv run whycode check-change        # prints the Fence Warnings (ChangeCheck contract) as JSON
    uv run whycode check-citations --sample 20    # every node id in 20 answers resolves (exit 1 if not)
    uv run whycode supersession-report            # the supersession judge (Opus 5.5) vs explicit Supersession
    uv run whycode serve [--port 8765]            # the human view: one page per Answer, and /why as JSON

Configuration comes from the environment (`whycode.config`); the real slice's scope from `whycode.history.scope`.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from whycode.config import EXTRACTORS, JUDGES, ConfigError, Settings

PITCH_LABELS = {"Decisions": "Decision", "Changes": "Change", "Discussions": "Discussion",
                "Code Entities": "CodeEntity", "Incidents": "Incident", "People": "Person"}
log = logging.getLogger("whycode")


def _github_source(settings: Settings, args: argparse.Namespace, cutoff: dt.date, transport):
    from whycode.history.checkout import ensure_checkout
    from whycode.history.github import CachedTransport, GitHubClient, GitHubHistorySource, UrllibTransport
    from whycode.history.scope import SCHEMA_CHANGES

    scope = dataclasses.replace(SCHEMA_CHANGES, cutoff_commit=settings.cutoff_commit)
    ensure_checkout(settings.checkout, scope.repo_url, scope.cutoff_commit, scope.checkout_paths)
    inner = None if args.offline else (transport or UrllibTransport())
    if inner is not None and transport is None and not settings.github_token:
        log.warning("GITHUB_TOKEN is not set: requests that are not cached go unauthenticated (60 per hour)")
    cached = CachedTransport(inner, settings.github_cache)
    client = GitHubClient(cached, token=settings.github_token)
    return GitHubHistorySource(client, scope, settings.checkout, cutoff, limit=args.limit), cached, scope


def _fetch(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.history import load_history

    source, cached, _ = _github_source(settings, args, settings.cutoff, transport)
    history = load_history(source, settings.cutoff)
    print(json.dumps({
        "cutoff": settings.cutoff.isoformat(), "limit": args.limit, "rfcs": len(history.rfcs),
        "pull_requests": len(history.pull_requests), "issues": len(history.issues),
        "github_calls": cached.network_calls, "cache_hits": cached.cache_hits,
    }, indent=2))
    return 0


def _build(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.build import build_graph, latest_date
    from whycode.graph.store import GraphStore
    from whycode.history import load_history

    cutoff = dt.date.fromisoformat(args.cutoff) if args.cutoff else settings.cutoff
    default = "recorded" if args.history == "fixtures" else "anthropic"
    extractor = args.extractor or (settings.extractor if settings.extractor_set else default)
    if args.history == "github" and extractor == "recorded":
        raise ConfigError("recorded extractions exist only for the fixture history: use --extractor anthropic "
                          "(or none for a graph without Decisions)")
    judge_kind = args.judge or extractor  # recorded judgments only cover recorded Decisions
    if args.history == "github" and judge_kind == "recorded":
        raise ConfigError("recorded supersession judgments exist only for the fixture history: use --judge anthropic "
                          "(or none for explicit Supersession only)")
    proposer = settings.proposer(extractor, cutoff)  # fail fast on a missing key, before any fetching
    judge = settings.judge(judge_kind)
    store = GraphStore(settings.driver(), settings.neo4j_database)

    cached = None
    if args.history == "github":
        from whycode.codeindex.go import parse_go_tree

        source, cached, scope = _github_source(settings, args, cutoff, transport)
        history = load_history(source, cutoff)
        code = parse_go_tree(settings.checkout, scope.code_paths)
    else:
        from whycode.fixtures import FIXTURE_DIR, FIXTURE_REPO, fixture_code_index
        from whycode.history.fixture import FixtureHistorySource

        history = load_history(FixtureHistorySource(FIXTURE_DIR, repo=FIXTURE_REPO), cutoff)
        code = fixture_code_index()

    graph = build_graph(history, code, proposer, judge)
    latest = latest_date(graph)
    if latest and latest > cutoff.isoformat():
        raise RuntimeError(f"the graph holds a date after the cutoff ({latest} > {cutoff}); nothing was written")
    store.replace(graph)
    raw = store.counts()
    report = {
        "history": args.history, "cutoff": cutoff.isoformat(), "extractor": extractor, "judge": judge_kind,
        "counts": {name: raw.get(label, 0) for name, label in PITCH_LABELS.items()},
        "latest_date": latest, "graph": raw,
    }
    if cached is not None:
        from whycode.eval.corpus import write_jsonl
        from whycode.graph.corpus import corpus_records

        corpus = Path(args.corpus) if args.corpus else settings.corpus
        corpus.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(corpus, corpus_records(graph))
        report |= {"limit": args.limit, "complete": args.limit is None, "cutoff_commit": settings.cutoff_commit,
                   "github_calls": cached.network_calls, "corpus": str(corpus)}
        counts_file = Path(args.counts_file)
        counts_file.parent.mkdir(parents=True, exist_ok=True)
        counts_file.write_text(json.dumps({k: v for k, v in report.items() if k != "corpus"}, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


def _supersession_report(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.graph.store import GraphStore
    from whycode.supersession import judge_report

    graph = GraphStore(settings.driver(), settings.neo4j_database).snapshot()
    text = judge_report(graph, settings.judge(args.judge)).markdown()
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


def _why(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.answer.patterns import GraphReader

    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    answer = settings.answer_engine(reader).why(args.anchor)
    print(answer.model_dump_json(indent=2))
    return 0


def _check_change(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.answer.fence import FenceChecker
    from whycode.answer.patterns import GraphReader

    diff = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    print(FenceChecker(reader).check(diff).model_dump_json(indent=2))
    return 0


def _check_citations(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.answer.patterns import GraphReader
    from whycode.audit import GraphResolver, audit_citations, sample_anchors

    driver = settings.driver()
    reader = GraphReader(driver, settings.neo4j_database)
    reader.selfcheck()
    engine = settings.answer_engine(reader)
    anchors = sample_anchors(driver, args.sample, args.seed, settings.neo4j_database)
    audit = audit_citations(engine.why, anchors, GraphResolver(driver, settings.neo4j_database))
    print(json.dumps({**audit.report(), "anchors": anchors}, indent=2))
    return 0 if audit.ok else 1


def _serve(settings: Settings, args: argparse.Namespace, transport=None) -> int:
    from whycode.answer.patterns import GraphReader
    from whycode.view import make_server

    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    server = make_server(settings.answer_engine(reader).why, args.host, args.port)
    host, port = server.server_address[:2]
    print(f"serving http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None, *, github_transport=None) -> int:
    """`github_transport` replaces the network transport under the cache (tests serve a fake GitHub)."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="whycode", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def github_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--limit", type=int, help="bound the run: the N most recent pull requests and labelled "
                                                 "issues, at most N linked issues (default: everything)")
        p.add_argument("--offline", action="store_true", help="read only the cache; a missing response fails")

    build = sub.add_parser("build", help="build the graph into Neo4j (replaces what is there)")
    build.add_argument("--history", choices=["fixtures", "github"], default="fixtures")
    build.add_argument("--extractor", choices=EXTRACTORS,
                       help="default: WHY_EXTRACTOR, else recorded (fixtures) or anthropic (github)")
    build.add_argument("--cutoff", help="YYYY-MM-DD; default: WHY_CUTOFF or 2024-06-30")
    build.add_argument("--judge", choices=JUDGES,
                       help="supersession judge; default: the same kind as the extractor")
    build.add_argument("--corpus", help="github: where to write the scoreboard corpus (default: WHY_CORPUS)")
    build.add_argument("--counts-file", default="data/graph-counts.json",
                       help="github: where to record the graph counts (default: %(default)s)")
    github_options(build)
    fetch = sub.add_parser("fetch", help="fetch the real slice into the GitHub cache, without building")
    github_options(fetch)
    why = sub.add_parser("why", help="print the Answer for an Anchor (function, file, package or setting)")
    why.add_argument("anchor")
    change = sub.add_parser("check-change", help="print the Fence Warnings for a proposed diff (no model needed)")
    change.add_argument("diff", nargs="?", default="-", help="a unified diff file (`git diff` output); - for stdin")
    check = sub.add_parser("check-citations", help="ask why about a sample of Anchors; every node id must resolve")
    check.add_argument("--sample", type=int, default=20)
    check.add_argument("--seed", type=int, default=0)
    report = sub.add_parser("supersession-report", help="score the supersession judge against explicit Supersession "
                                                        "in the built graph (precision, recall, disagreements)")
    report.add_argument("--judge", choices=["recorded", "anthropic"], default="anthropic")
    report.add_argument("--out", type=Path, help="also write the report (markdown) here")
    serve = sub.add_parser("serve", help="serve the human view: one page per Answer, and /why?anchor= as JSON")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765, help="0 picks a free port (default: %(default)s)")
    args = parser.parse_args(argv)
    commands = {"build": _build, "fetch": _fetch, "why": _why, "check-change": _check_change,
                "check-citations": _check_citations, "supersession-report": _supersession_report, "serve": _serve}

    from whycode.history.checkout import CheckoutError
    from whycode.history.github import GitHubError

    try:
        return commands[args.command](Settings.from_env(), args, github_transport)
    except ConfigError as exc:
        print(f"whycode: {exc}", file=sys.stderr)
        return 2
    except (CheckoutError, GitHubError) as exc:
        print(f"whycode: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
