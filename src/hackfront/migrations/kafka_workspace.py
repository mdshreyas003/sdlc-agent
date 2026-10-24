"""Migration kafka-workspace v1: file every piece of local Apache Kafka data under one 'kafka' demo workspace.

1. ensure the workspace (same Kafka corpus as the 'eval' benchmark, plus the KIP wiki space);
2. replay the corpus (Jira issues + comments, GitHub PRs + commits, dev@ mail) through the normal sync;
3. write the 10 KIP pages as `document` artifacts (the eval workspace never sees them: they are its answer key);
   "KIP-N" in any text and KAFKA-N / PR links on a page become explicit `origin=text` edges, as for every source;
4. tag every node and edge in the workspace's scopes with `in_workspaces` += 'kafka'; report counts.
Everything is MERGE/SET on canonical ids, so a re-run creates nothing new. The raw data is read from
HACKFRONT_EVAL_RAW (default data/raw, filled by data/tools/fetch_kip_raw.py); it is never committed.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from ..eval import corpus

ID, VERSION = "kafka-workspace", 1
SLUG, NAME = "kafka", "Apache Kafka"
WIKI = "https://cwiki.apache.org/confluence"
SPACE = "cwiki.apache.org/KAFKA"  # scope of KIP pages; deliberately not "KAFKA" (the Jira project scope eval sees)
QUESTIONS = Path(__file__).resolve().parents[3] / "data" / "kafka_demo_questions.json"
ADAPTER_VERSION = "confluence-kip/0.1"


def workspace_config() -> dict:
    pages = sorted(p.parent.name for p in corpus.RAW.glob("KIP-*/page.json"))
    return {**corpus.workspace(), "name": NAME, "demo": True, "docs": {"site": WIKI, "spaces": [SPACE], "pages": pages}}


def _plain(storage_html: str) -> str:
    text = re.sub(r"<(br|/p|/h\d|/li|/tr)\b[^>]*>", "\n", storage_html)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"[ \t\xa0]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()


def kip_pages(raw: Path | None = None) -> list:
    """One `document` Artifact per data/raw/KIP-*/page.json (Confluence REST content)."""
    from ..ingest.contracts import Actor, Artifact, Provenance, RecordKind, SourceIdentity

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    out = []
    for path in sorted((raw or corpus.RAW).glob("KIP-*/page.json")):
        page = json.loads(path.read_bytes())
        kip = path.parent.name  # "KIP-405"
        links, version = page.get("_links") or {}, page.get("version") or {}
        url = (links.get("base") or WIKI) + (links.get("webui") or "")
        by = version.get("by") or {}
        out.append(Artifact(
            source=SourceIdentity("confluence", SPACE, "page", kip, url),
            kind=RecordKind.DOCUMENT, observed_at=now, event_time=version.get("when"), updated_at=version.get("when"),
            provenance=Provenance(links.get("self") or url, "$", now, ADAPTER_VERSION),
            actor=Actor("confluence", by.get("userKey") or by.get("username") or "unknown", by.get("displayName"),
                        by.get("username")) if by else None,
            title=page.get("title") or kip, text=_plain(page["body"]["storage"]["value"]),
            context={"page_id": page.get("id"), "version": version.get("number")}, raw_payload=page))
    return out


def _counts(driver, scopes: list[str]) -> dict:
    db = config.neo4j_database()
    q = lambda query: driver.execute_query(query, scopes=scopes, slug=SLUG, database_=db, routing_="r")[0]  # noqa: E731
    by_source = {f"{r['p']}:{r['t']}": r["n"] for r in q(
        "MATCH (a:Artifact) WHERE a.scope IN $scopes AND NOT coalesce(a.is_stub, false) "
        "RETURN a.provider AS p, a.source_record_type AS t, count(*) AS n ORDER BY p, t")}
    edges = {r["k"]: r["n"] for r in q(
        "MATCH (a:Artifact)-[r]->(:Artifact) WHERE a.scope IN $scopes RETURN type(r) AS k, count(*) AS n ORDER BY k")}
    tagged = q("MATCH (a:Artifact) WHERE $slug IN coalesce(a.in_workspaces, []) RETURN count(a) AS n")[0]["n"]
    tagged_edges = q("MATCH ()-[r]->() WHERE $slug IN coalesce(r.in_workspaces, []) RETURN count(r) AS n")[0]["n"]
    stubs = q("MATCH (a:Artifact)-->(s:Artifact) WHERE a.scope IN $scopes AND s.is_stub RETURN count(DISTINCT s) AS n")
    return {"artifacts": sum(by_source.values()), "edges": sum(edges.values()), "stubs": stubs[0]["n"],
            "by_source": by_source, "edges_by_type": edges, "tagged_artifacts": tagged, "tagged_edges": tagged_edges}


TAG_NODES = ("MATCH (a:Artifact) WHERE a.scope IN $scopes AND NOT coalesce(a.is_stub, false) "
             "SET a.in_workspaces = [w IN coalesce(a.in_workspaces, []) WHERE w <> $slug] + $slug")
TAG_EDGES = ("MATCH (a:Artifact)-[r]->(:Artifact) WHERE a.scope IN $scopes "
             "SET r.in_workspaces = [w IN coalesce(r.in_workspaces, []) WHERE w <> $slug] + $slug")
RECORD = ("MERGE (m:HfMigration {id: $id}) SET m.version = $version, m.applied_at = $now, m.counts = $counts, "
          "m.runs = coalesce(m.runs, 0) + 1")


def run(raw: Path | None = None) -> dict:
    """Apply the migration (safe to repeat) and return the workspace's counts."""
    from ..api.mapping import flat_scopes
    from ..ingest import sync
    from ..ingest.extraction.links import LinkConfig, add_text_references
    from ..ingest.storage.neo4j import Neo4jStore

    if raw is not None:
        corpus.RAW = Path(raw)
    if not any(corpus.RAW.glob("KIP-*/page.json")):
        raise ValueError(f"no Kafka corpus under {corpus.RAW}; run data/tools/fetch_kip_raw.py or set HACKFRONT_EVAL_RAW")
    ws = workspace_config()
    if not any(w["slug"] == SLUG for w in config.list_workspaces()):
        config.create_workspace(NAME, demo=True, slug=SLUG)
    config.save_workspace(SLUG, ws)

    status = sync.run_sync_inline(SLUG, "deep", budget=float("inf"))
    if not status["complete"]:
        raise RuntimeError(f"corpus sync incomplete: {status.get('error') or status['totals']}")
    driver = config.neo4j_driver()
    store = Neo4jStore(driver, config.neo4j_database())
    store.initialize_schema()
    links = LinkConfig.from_workspace(config.load_workspace(SLUG))
    pages = store.write_many(add_text_references(a, links) for a in kip_pages())

    scopes, db = flat_scopes(config.scopes(SLUG)), config.neo4j_database()
    for query in (TAG_NODES, TAG_EDGES):
        driver.execute_query(query, scopes=scopes, slug=SLUG, database_=db)
    counts = _counts(driver, scopes)
    driver.execute_query(RECORD, id=ID, version=VERSION, counts=json.dumps(counts), database_=db,
                         now=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return {"migration": f"{ID} v{VERSION}", "workspace": SLUG, "raw": str(corpus.RAW),
            "synced": status["totals"], "kip_pages": len(pages), **counts}


# ------------------------------------------------------------- demo questions (stored agent investigations)
def questions(path: Path = QUESTIONS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def ask(provider: str | None = None, path: Path = QUESTIONS) -> list[dict]:
    """Run the real agent for every demo question that has no stored investigation yet; saves each answer."""
    from ..agent.investigation import investigate, list_all, save
    from ..api.mapping import flat_scopes

    have = {i["question"] for i in list_all(SLUG)}
    scopes, driver, done = flat_scopes(config.scopes(SLUG)), config.neo4j_driver(), []
    for q in questions(path):
        if q["question"] in have:
            done.append({"id": q["id"], "status": "exists"})
            continue
        result = {"id": q["id"], "status": "error"}
        for ev in investigate(q["question"], q.get("mode", "why"), provider, None, driver, None, scopes, SLUG):
            if ev["event"] == "investigation":
                save(ev["investigation"], ev["graph"], SLUG)
                result = {"id": q["id"], "status": "saved", "investigation": ev["investigation"]["id"]}
            elif ev["event"] == "error":
                result["message"] = str(ev.get("message"))[:200]
        done.append(result)
    return done


def export_investigations(out: Path) -> int:
    """Write each stored kafka investigation as <id>.json ({investigation, graph}), for `import_investigations`."""
    from .. import state

    out.mkdir(parents=True, exist_ok=True)
    rows = state.backend().list_investigations(SLUG)
    for row in rows:
        doc = state.backend().get_investigation(SLUG, row["id"])
        (out / f"{row['id']}.json").write_text(json.dumps(doc), encoding="utf-8")
    return len(rows)


def import_investigations(src: Path) -> int:
    """Store exported investigations under the kafka workspace (same id: re-importing overwrites, never duplicates)."""
    from ..agent.investigation import save

    n = 0
    for path in sorted(Path(src).glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        save(doc["investigation"], doc["graph"], SLUG)
        n += 1
    return n
