"""Ship the kafka-workspace migration to a deployed API over HTTPS (for hosts whose Neo4j is unreachable from here).

    hackfront migrate-kafka --export-bundle kafka.bundle.json.gz [--investigations DIR]   # local, no Neo4j needed
    HACKFRONT_ADMIN_TOKEN=... [HACKFRONT_ACCESS_TOKEN=...] hackfront push-bundle kafka.bundle.json.gz --api https://<api>

The bundle holds the workspace config, every linked Artifact the migration would store (corpus replay + KIP pages, in
write order) and exported investigations. `push-bundle` sends it in gzip chunks to POST /api/admin/import-bundle
(api/admin.py), which writes them with the same Neo4jStore, then a final request tags the workspace and records the
migration exactly like `migrate-kafka`. Everything is MERGE on canonical ids, so pushing twice changes nothing.
"""

from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

from ..ingest.contracts import (Actor, Artifact, Change, Provenance, RecordKind, RelationshipKind, SourceIdentity,
                                SourceReference)
from . import kafka_workspace as kw

FORMAT, VERSION = "hackfront-bundle", 1
PATH = "/api/admin/import-bundle"
ADMIN_HEADER = "X-Hackfront-Admin-Token"
MAX_BODY = 3_500_000  # gzip bytes per request; Vercel rejects request bodies above 4.5 MB
MAX_INFLATED = 64_000_000  # server-side cap on one decompressed request
CHUNK = 100  # artifacts per request: each is one write transaction, so this bounds the function's run time


# ------------------------------------------------------------------ Artifact <-> JSON
def _identity(s: SourceIdentity) -> dict:
    return {"provider": s.provider, "workspace": s.workspace, "record_type": s.record_type, "source_id": s.source_id,
            "uri": s.uri}


def to_dict(a: Artifact) -> dict:
    p, c = a.provenance, a.change
    return {
        "source": _identity(a.source), "kind": a.kind.value, "observed_at": a.observed_at,
        "event_time": a.event_time, "updated_at": a.updated_at,
        "provenance": {"source_uri": p.source_uri, "locator": p.locator, "observed_at": p.observed_at,
                       "adapter_version": p.adapter_version, "payload_uri": p.payload_uri,
                       "payload_sha256": p.payload_sha256},
        "actor": {"provider": a.actor.provider, "source_id": a.actor.source_id, "display_name": a.actor.display_name,
                  "handle": a.actor.handle} if a.actor else None,
        "title": a.title, "text": a.text, "context": dict(a.context),
        "references": [{"target": _identity(r.target), "relationship": r.relationship.value, "locator": r.locator,
                        "origin": r.origin} for r in a.references],
        "change": {"paths": list(c.paths), "additions": c.additions, "deletions": c.deletions, "before": c.before,
                   "after": c.after} if c else None,
        "raw_payload": dict(a.raw_payload) if a.raw_payload is not None else None,
        "schema_version": a.schema_version,
    }


def from_dict(d: dict) -> Artifact:
    """Rebuild (and so re-validate) an Artifact; bad input raises ValueError/TypeError/KeyError."""
    change = d.get("change")
    return Artifact(
        source=SourceIdentity(**d["source"]), kind=RecordKind(d["kind"]), observed_at=d["observed_at"],
        event_time=d.get("event_time"), updated_at=d.get("updated_at"), provenance=Provenance(**d["provenance"]),
        actor=Actor(**d["actor"]) if d.get("actor") else None, title=d.get("title"), text=d.get("text"),
        context=dict(d.get("context") or {}),
        references=tuple(SourceReference(SourceIdentity(**r["target"]), RelationshipKind(r["relationship"]),
                                          r["locator"], r.get("origin", "structural")) for r in d.get("references") or ()),
        change=Change(**{**change, "paths": tuple(change.get("paths") or ())}) if change else None,
        raw_payload=d.get("raw_payload"), schema_version=d["schema_version"])


# ------------------------------------------------------------------ export (local)
def export(out: Path, raw: Path | None = None, investigations: Path | None = None) -> dict:
    from ..ingest.storage.neo4j.writer import _node_properties

    ws, artifacts = kw.collect(raw)
    rows = [to_dict(a) for a in artifacts]
    for a, row in zip(artifacts, rows):  # the round trip must store exactly what the migration stores
        back = from_dict(json.loads(json.dumps(row)))
        if _node_properties(back) != _node_properties(a) or back.references != a.references:
            raise RuntimeError(f"artifact does not survive serialization: {a.canonical_id}")
    invs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(investigations).glob("*.json"))] \
        if investigations else []
    doc = {"format": FORMAT, "version": VERSION, "migration": f"{kw.ID} v{kw.VERSION}",
           "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
           "workspace": {"slug": kw.SLUG, "config": ws}, "artifacts": rows, "investigations": invs}
    out = Path(out)
    out.write_bytes(gzip.compress(json.dumps(doc, ensure_ascii=False).encode("utf-8")))
    return {"bundle": str(out), "bytes": out.stat().st_size, "artifacts": len(rows),
            "distinct_artifacts": len({a.canonical_id for a in artifacts}), "investigations": len(invs)}


def load(path: Path) -> dict:
    data = Path(path).read_bytes()
    return json.loads(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


# ------------------------------------------------------------------ import (server side, api/admin.py)
def inflate(body: bytes) -> dict:
    """Request body -> JSON; gzip is detected by its magic bytes (no reliance on proxies keeping Content-Encoding)."""
    if body[:2] == b"\x1f\x8b":
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        body = d.decompress(body, MAX_INFLATED)
        if d.unconsumed_tail:
            raise ValueError("bundle chunk too large")
    try:
        doc = json.loads(body)
    except ValueError:
        raise ValueError("body is not JSON") from None
    if not isinstance(doc, dict):
        raise ValueError("body must be a JSON object")
    return doc


def apply(doc: dict) -> dict:
    """One chunk: ensure the workspace, write its artifacts and investigations; `finalize` tags and counts.
    Only the kafka-workspace bundle is accepted, and only artifacts inside that workspace's scopes."""
    from .. import config
    from ..agent.investigation import list_all, save
    from ..api.mapping import flat_scopes
    from ..ingest.storage.neo4j import Neo4jStore
    from ..ingest.storage.neo4j.writer import scope_of

    if doc.get("format") != FORMAT or doc.get("version") != VERSION:
        raise ValueError(f"expected {FORMAT} v{VERSION}")
    ws = doc.get("workspace") or {}
    if ws.get("slug") != kw.SLUG or not isinstance(ws.get("config"), dict):
        raise ValueError(f"only the '{kw.SLUG}' workspace bundle can be imported")
    cfg = config.validate_workspace(ws["config"])
    if not cfg.get("demo"):
        raise ValueError("bundle workspace must be a demo workspace")
    rows, invs = doc.get("artifacts") or [], doc.get("investigations") or []
    if not isinstance(rows, list) or not isinstance(invs, list):
        raise ValueError("artifacts and investigations must be lists")
    try:
        artifacts = [from_dict(r) for r in rows]
    except (TypeError, KeyError, ValueError, AttributeError):
        raise ValueError("invalid artifact in bundle") from None
    kw.ensure_workspace(cfg)
    scopes = set(flat_scopes(config.scopes(kw.SLUG)))
    if any(scope_of(a) not in scopes for a in artifacts):
        raise ValueError("artifact outside the workspace's scopes")
    for inv in invs:
        if not (isinstance(inv, dict) and isinstance(inv.get("investigation"), dict) and "graph" in inv):
            raise ValueError("invalid investigation in bundle")

    driver = config.neo4j_driver()
    out: dict = {"workspace": kw.SLUG}
    if artifacts:
        store = Neo4jStore(driver, config.neo4j_database())
        store.initialize_schema()
        out["written"] = len(store.write_many(artifacts))
    for inv in invs:
        save(inv["investigation"], inv["graph"], kw.SLUG)  # same id -> overwritten, never duplicated
    if invs:
        out["saved_investigations"] = len(invs)
    if doc.get("finalize"):
        out.update(kw.finalize(driver), investigations=len(list_all(kw.SLUG)), migration=f"{kw.ID} v{kw.VERSION}")
    return out


# ------------------------------------------------------------------ push (client side)
def chunks(doc: dict, size: int = CHUNK, max_body: int = MAX_BODY):
    """Gzipped request bodies: artifacts in order (<= size each and <= max_body bytes), one per investigation, then
    an empty finalize request."""
    head = {"format": doc["format"], "version": doc["version"], "workspace": doc["workspace"]}
    pack = lambda **kw_: gzip.compress(json.dumps({**head, "artifacts": [], "investigations": [], **kw_},  # noqa: E731
                                                  ensure_ascii=False).encode("utf-8"))
    rows, i = doc["artifacts"], 0
    while i < len(rows):
        n = min(size, len(rows) - i)
        while True:
            body = pack(artifacts=rows[i:i + n])
            if len(body) <= max_body:
                break
            if n == 1:
                raise ValueError(f"artifact {i} alone exceeds {max_body} bytes compressed")
            n = max(1, n // 2)
        yield f"artifacts {i + 1}-{i + n}/{len(rows)}", body
        i += n
    for k, inv in enumerate(doc["investigations"], 1):
        body = pack(investigations=[inv])
        if len(body) > max_body:
            raise ValueError(f"investigation {k} exceeds {max_body} bytes compressed")
        yield f"investigation {k}/{len(doc['investigations'])}", body
    yield "finalize", pack(finalize=True)


def _post(url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def push(path: Path, api: str, admin_token: str, access_token: str | None = None, size: int = CHUNK,
         max_body: int = MAX_BODY, timeout: float = 290, retries: int = 3, log=print) -> dict:
    if not admin_token:
        raise ValueError("set HACKFRONT_ADMIN_TOKEN (same value as on the API host)")
    url = api.rstrip("/") + PATH
    headers = {"Content-Type": "application/gzip", "Accept": "application/json", ADMIN_HEADER: admin_token}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    result: dict = {}
    for label, body in chunks(load(path), size, max_body):
        for attempt in range(1, retries + 1):
            started = time.monotonic()
            try:
                status, text = _post(url, body, headers, timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                status, text = 0, type(e).__name__
            took = time.monotonic() - started
            if status == 200:
                result = json.loads(text)
                log(f"{label}: ok ({len(body)} bytes, {took:.1f}s)")
                break
            log(f"{label}: HTTP {status} {text[:200]} ({took:.1f}s, attempt {attempt}/{retries})")
            if status in (400, 401, 403, 404, 413, 422) or attempt == retries:  # not worth retrying
                raise RuntimeError(f"push stopped at {label} (HTTP {status}); every write is idempotent, re-run to resume")
            time.sleep(2 * attempt)
    return result


def main_push(args) -> int:
    import os

    result = push(Path(args.bundle), args.api, os.environ.get("HACKFRONT_ADMIN_TOKEN", ""),
                  os.environ.get("HACKFRONT_ACCESS_TOKEN") or None, args.chunk, args.max_bytes)
    print(json.dumps(result, indent=2))
    return 0
