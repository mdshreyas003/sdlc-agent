"""hackfront CLI: demo | sync | workspaces | status | ask | migrate-kafka | push-bundle | serve."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import config


def _print(obj) -> None:
    print(json.dumps(obj, indent=2))


def _sync(slug: str, mode: str) -> int:
    """Run a sync job to completion, printing a line whenever a stream changes."""
    from .ingest import sync

    status, seen = sync.start_sync(slug, mode), {}
    while True:
        status = sync.sync_status(slug)
        for s in status["streams"]:
            line = f"{s['stream']}: {s['status']} pages={s['pages']} fetched={s['fetched']} persisted={s['persisted']}"
            if seen.get(s["stream"]) != line:
                seen[s["stream"]] = line
                print(line + "".join(f"  ! {e['message']}" for e in s["errors"][:1]))
        if status["state"] != "running":
            break
        time.sleep(0.2)
    if status.get("error"):
        print(f"error: {status['error']}", file=sys.stderr)
    _print({"totals": status["totals"], "graph": status.get("graph"), "complete": status["complete"]})
    return 0 if status["complete"] else 1


def main(argv: list[str] | None = None) -> int:
    config.load_env()
    from .agent.llm import PROVIDERS

    provider_names = sorted(PROVIDERS)
    cli = argparse.ArgumentParser(prog="hackfront", description=__doc__)
    sub = cli.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="create the 'demo' workspace if missing and sync it (needs only Neo4j)")
    sub.add_parser("eval-load", help="create the 'eval' workspace (Kafka benchmark corpus from data/raw) and sync it")
    sync = sub.add_parser("sync", help="ingest a workspace's sources (credentials from the workspace store or env)")
    sync.add_argument("--workspace", required=True)
    sync.add_argument("--deep", action="store_true", help="100 pages per stream instead of 20")
    ev = sub.add_parser("eval", help="run the benchmark systems over the gold questions and score them")
    ev.add_argument("--workspace", default="eval")
    ev.add_argument("--split", choices=["dev", "test"], default="dev")
    ev.add_argument("--systems", default="b0,b1,s-,s", help="comma list of b0,b1,s-,s")
    ev.add_argument("--provider", choices=provider_names)
    ev.add_argument("--judge-provider", choices=provider_names)
    ev.add_argument("--limit", type=int)
    ev.add_argument("--include-unverified", action="store_true", help="dev smoke runs only")
    ev.add_argument("--resume", help="results directory of a stopped run")
    ev.add_argument("--force", action="store_true", help="score the test split again")
    sub.add_parser("workspaces", help="list workspaces")
    sub.add_parser("status", help="workspaces and global graph counts")
    ask = sub.add_parser("ask", help="ask the agent from the terminal")
    ask.add_argument("question")
    ask.add_argument("--workspace", required=True)
    ask.add_argument("--mode", default="why", choices=["why", "debug", "change"])
    ask.add_argument("--provider", choices=provider_names)
    migrate = sub.add_parser("migrate-state", help="copy local workspaces, saved keys and investigations into Neo4j")
    migrate.add_argument("--overwrite", action="store_true", help="replace workspaces that already exist in Neo4j")
    kafka = sub.add_parser("migrate-kafka", help="file all local Kafka data (mail, Jira, PRs, commits, KIPs) under the "
                           "'kafka' workspace; idempotent")
    kafka.add_argument("--raw", help="Kafka corpus directory (default HACKFRONT_EVAL_RAW or data/raw)")
    kafka.add_argument("--ask", action="store_true", help="also run the agent on data/kafka_demo_questions.json "
                       "(only questions without a stored answer; uses the LLM)")
    kafka.add_argument("--provider", choices=provider_names)
    kafka.add_argument("--export-investigations", metavar="DIR", help="write the stored kafka investigations to DIR")
    kafka.add_argument("--import-investigations", metavar="DIR", help="store investigations exported to DIR")
    kafka.add_argument("--export-bundle", metavar="FILE", help="write the migration as a gzip bundle for push-bundle "
                       "instead of applying it (no Neo4j needed)")
    kafka.add_argument("--investigations", metavar="DIR", help="with --export-bundle: include investigations exported "
                       "to DIR")
    push = sub.add_parser("push-bundle", help="send a bundle to a deployed API (POST /api/admin/import-bundle); tokens "
                          "from HACKFRONT_ADMIN_TOKEN and HACKFRONT_ACCESS_TOKEN")
    push.add_argument("bundle")
    push.add_argument("--api", required=True, help="API base URL, e.g. https://<api>.vercel.app")
    push.add_argument("--chunk", type=int, default=100, help="artifacts per request (default 100)")
    push.add_argument("--max-bytes", type=int, default=3_500_000, help="max gzip bytes per request")
    serve = sub.add_parser("serve", help="start the API and web UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = cli.parse_args(argv)

    try:
        if args.cmd == "demo":
            from .ingest.demo import DEMO_WORKSPACE

            if not any(w["slug"] == "demo" for w in config.list_workspaces()):
                config.create_workspace("Acme Demo", demo=True, slug="demo")
            config.save_workspace("demo", DEMO_WORKSPACE)
            return _sync("demo", "standard")
        if args.cmd == "eval":
            from .eval.run import main_eval

            return main_eval(args)
        if args.cmd == "eval-load":
            from .eval.corpus import workspace

            if not any(w["slug"] == "eval" for w in config.list_workspaces()):
                config.create_workspace("Kafka Eval", demo=True, slug="eval")
            config.save_workspace("eval", workspace())
            return _sync("eval", "deep")
        if args.cmd == "sync":
            return _sync(args.workspace, "deep" if args.deep else "standard")
        if args.cmd == "migrate-state":
            from . import state

            result = state.migrate(state.FileState(), state.Neo4jState(), overwrite=args.overwrite)
            _print(result)
            if result["secrets_skipped"]:
                print("note: saved keys were NOT copied; set HACKFRONT_SECRET_KEY and run again with --overwrite", file=sys.stderr)
            return 0
        if args.cmd == "migrate-kafka":
            from pathlib import Path

            from .migrations import kafka_workspace as m

            if args.export_bundle:
                from .migrations import bundle

                _print(bundle.export(Path(args.export_bundle), Path(args.raw) if args.raw else None,
                                     Path(args.investigations) if args.investigations else None))
                return 0
            _print(m.run(Path(args.raw) if args.raw else None))
            if args.import_investigations:
                _print({"imported_investigations": m.import_investigations(Path(args.import_investigations))})
            if args.ask:
                _print({"questions": m.ask(args.provider)})
            if args.export_investigations:
                _print({"exported_investigations": m.export_investigations(Path(args.export_investigations))})
            return 0
        if args.cmd == "push-bundle":
            from .migrations import bundle

            return bundle.main_push(args)
        if args.cmd == "workspaces":
            for w in config.list_workspaces():
                print(f"{w['slug']}\t{w['name']}{'\t(demo)' if w['demo'] else ''}")
        elif args.cmd == "status":
            from .ingest.sync import graph_counts

            _print({"workspaces": config.list_workspaces(), "graph": graph_counts()})
        elif args.cmd == "ask":
            from . import agent
            from .api.mapping import flat_scopes

            events = agent.run(args.question, mode=args.mode, provider=args.provider,
                               scopes=flat_scopes(config.scopes(args.workspace)), workspace=args.workspace)
            for event in events:
                if event["event"] == "trace":
                    print(f"[{event['node']}] {json.dumps(event['data'], default=str)[:300]}", file=sys.stderr)
                elif event["event"] == "answer":
                    a = event["answer"]
                    print(f"\n{a['answer']}\n\nconfidence: {a['confidence']}\nuncertainty: {a['uncertainty'] or '-'}")
                    print("sources:\n" + "\n".join(f"  {c}" for c in a["citations"]))
                    print(f"(attempts={a['attempts']}, {a['provider']}/{a['model']}, prompts={a['prompt_version']})")
                else:
                    print(f"error: {event['message']}", file=sys.stderr)
                    return 1
        elif args.cmd == "serve":
            import uvicorn

            uvicorn.run("hackfront.api:app", host=args.host, port=args.port)
    except (LookupError, ValueError, RuntimeError) as error:  # unknown workspace, no sources, already running, Neo4j env
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
