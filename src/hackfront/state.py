"""Where workspace state lives: workspaces, their API keys, stored investigations and the last sync status.

Two backends behind one interface, chosen by HACKFRONT_STATE (read on every call):
  file   (default) HOME/.hackfront/workspaces/<slug>/{workspace.json, secrets.json, sync.json, investigations/}
  neo4j            :HfWorkspace / :HfSecret / :HfInvestigation / :HfSync nodes in the same Neo4j as the evidence graph
                   (labels disjoint from :Artifact, so the agent's queries can never see them). API keys are encrypted
                   with Fernet using HACKFRONT_SECRET_KEY (any string; its SHA-256 is the key). Stateless hosts use this.

Callers (config, agent.investigation, ingest.sync, api) go through `backend()`; they never touch paths or Cypher.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import secrets as _secrets
import shutil
import threading
import time
from datetime import datetime, timezone

CACHE_SECONDS = 2.0  # neo4j reads: a page load makes ~15 of them; other instances see a change within this window


class Stale(Exception):
    """A compare-and-swap write found a different version than the caller read (someone else saved first)."""


_memory_lock = threading.Lock()  # file backend: one process; the neo4j backend does its check inside the query


def backend():
    """On Vercel (VERCEL is set; its filesystem is read-only) the default is neo4j; elsewhere file."""
    chosen = (os.environ.get("HACKFRONT_STATE") or ("neo4j" if os.environ.get("VERCEL") else "file")).lower()
    return Neo4jState() if chosen == "neo4j" else FileState()


def _meta(doc: dict) -> dict:
    inv = doc.get("investigation") or {}
    out = {k: inv.get(k) for k in ("id", "question", "file", "line", "confidence", "created_at")}
    if inv.get("owner"):
        out["owner"] = inv["owner"]  # only investigations made while signed in carry an author
    return out


# ---------------------------------------------------------------- file backend
class FileState:
    def _dir(self, slug):
        from . import config

        return config.workspace_dir(slug)

    def slugs(self) -> list[str]:
        from . import config

        root = config.workspaces_dir()
        return [p.name for p in sorted(root.iterdir())
                if p.is_dir() and config.SLUG.fullmatch(p.name) and (p / "workspace.json").exists()] if root.is_dir() else []

    def exists(self, slug) -> bool:
        return (self._dir(slug) / "workspace.json").exists()

    def read_workspace(self, slug) -> dict | None:
        path = self._dir(slug) / "workspace.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None  # corrupt -> ValueError

    def write_workspace(self, slug, data: dict) -> None:
        d = self._dir(slug)
        d.mkdir(parents=True, exist_ok=True)
        _atomic(d / "workspace.json", json.dumps(data, indent=2))

    def delete(self, slug) -> None:
        shutil.rmtree(self._dir(slug))

    def read_secrets(self, slug) -> dict:
        path = self._dir(slug) / "secrets.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def write_secrets(self, slug, data: dict) -> None:
        path = self._dir(slug) / "secrets.json"
        _atomic(path, json.dumps(data, indent=2), mode=0o600)

    def put_investigation(self, ws, iid, doc: dict) -> None:
        d = self._dir(ws) / "investigations"
        d.mkdir(parents=True, exist_ok=True)
        _atomic(d / f"{iid}.json", json.dumps(doc))

    def get_investigation(self, ws, iid) -> dict | None:
        try:
            return json.loads((self._dir(ws) / "investigations" / f"{iid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_investigations(self, ws, limit=200) -> list[dict]:
        # ponytail: reads whole files; fine for a local folder of a few hundred
        d, out = self._dir(ws) / "investigations", []
        files = sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit] if d.exists() else []
        for p in files:
            try:
                out.append(_meta(json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda r: r["created_at"] or "", reverse=True)

    def put_memory(self, ws, mid, doc: dict, expect: int | None = None) -> None:
        """Save an entry. With `expect` (the version the caller read) the write fails with Stale if it moved on."""
        d = self._dir(ws) / "memory"
        d.mkdir(parents=True, exist_ok=True)
        with _memory_lock:
            if expect is not None:
                try:
                    have = json.loads((d / f"{mid}.json").read_text(encoding="utf-8")).get("version")
                except (OSError, ValueError):
                    have = None
                if have != expect:
                    raise Stale(f"entry is now v{have}")
            _atomic(d / f"{mid}.json", json.dumps(doc))

    def list_memory(self, ws) -> list[dict]:
        d, out = self._dir(ws) / "memory", []
        for p in sorted(d.glob("*.json")) if d.exists() else []:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda e: e["created_at"], reverse=True)

    def read_sync(self, slug) -> dict | None:
        try:
            return json.loads((self._dir(slug) / "sync.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write_sync(self, slug, data: dict) -> None:
        path = self._dir(slug) / "sync.json"
        if not path.parent.exists():
            raise FileNotFoundError("workspace deleted")
        _atomic(path, json.dumps(data))

    # ---- users (accounts live next to workspaces; secrets are 0600)
    def _udir(self, uid):
        from . import config

        return config.user_dir(uid)

    def read_user(self, uid) -> dict | None:
        try:
            return json.loads((self._udir(uid) / "user.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write_user(self, uid, data: dict) -> None:
        d = self._udir(uid)
        d.mkdir(parents=True, exist_ok=True)
        _atomic(d / "user.json", json.dumps(data, indent=2))

    def users_exist(self) -> bool:
        from . import config

        root = config.users_dir()
        return root.is_dir() and any((p / "user.json").exists() for p in root.iterdir() if p.is_dir())

    def read_user_secrets(self, uid) -> dict:
        try:
            data = json.loads((self._udir(uid) / "secrets.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_user_secrets(self, uid, data: dict) -> None:
        d = self._udir(uid)
        d.mkdir(parents=True, exist_ok=True)
        _atomic(d / "secrets.json", json.dumps(data, indent=2), mode=0o600)

    # ---- sync run history (one JSON per run)
    def put_run(self, ws, rid, doc: dict) -> None:
        d = self._dir(ws) / "runs"
        d.mkdir(parents=True, exist_ok=True)
        _atomic(d / f"{rid}.json", json.dumps(doc))

    def get_run(self, ws, rid) -> dict | None:
        try:
            return json.loads((self._dir(ws) / "runs" / f"{rid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def list_runs(self, ws, limit=50) -> list[dict]:
        d, out = self._dir(ws) / "runs", []
        for p in (sorted(d.glob("*.json"), key=lambda p: p.name, reverse=True)[:limit] if d.exists() else []):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out


def _atomic(path, text: str, mode: int | None = None) -> None:
    tmp = path.with_name(f".{path.name}.{_secrets.token_hex(4)}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if mode is not None:
        try:
            os.chmod(tmp, mode)  # best effort (no-op semantics on Windows)
        except OSError:
            pass
    os.replace(tmp, path)


# ---------------------------------------------------------------- neo4j backend
_drivers: dict = {}
_ready: set = set()
_cache: dict = {}
_lock = threading.Lock()
SCHEMA = (
    "CREATE CONSTRAINT hf_workspace_slug IF NOT EXISTS FOR (n:HfWorkspace) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT hf_secret_slug IF NOT EXISTS FOR (n:HfSecret) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT hf_sync_slug IF NOT EXISTS FOR (n:HfSync) REQUIRE n.slug IS UNIQUE",
    "CREATE CONSTRAINT hf_investigation_key IF NOT EXISTS FOR (n:HfInvestigation) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT hf_memory_key IF NOT EXISTS FOR (n:HfMemory) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT hf_user_uid IF NOT EXISTS FOR (n:HfUser) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT hf_user_secret_uid IF NOT EXISTS FOR (n:HfUserSecret) REQUIRE n.uid IS UNIQUE",
    "CREATE CONSTRAINT hf_run_key IF NOT EXISTS FOR (n:HfRun) REQUIRE n.key IS UNIQUE",
)


def _driver():
    """One shared driver per (uri, user, password); no connectivity check per call."""
    from neo4j import GraphDatabase

    key = tuple(os.environ.get(k) for k in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"))
    if not all(key):
        raise RuntimeError("NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD must be set to keep state in Neo4j")
    with _lock:
        if key not in _drivers:
            _drivers[key] = GraphDatabase.driver(key[0], auth=(key[1], key[2]))
        driver = _drivers[key]
        if key not in _ready:
            from . import config

            for statement in SCHEMA:
                driver.execute_query(statement, database_=config.neo4j_database())
            _ready.add(key)
    return driver


def _run(query: str, write: bool = False, **params) -> list[dict]:
    from . import config

    records, _, _ = _driver().execute_query(
        query, parameters_=params, database_=config.neo4j_database(), routing_="w" if write else "r")
    return [r.data() for r in records]


def _fernet():
    from cryptography.fernet import Fernet

    secret = os.environ.get("HACKFRONT_SECRET_KEY", "")
    if not secret:
        return None
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def _cached(key, loader):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return copy.deepcopy(hit[1])  # callers may mutate what they get
    value = loader()
    with _lock:
        _cache[key] = (now + CACHE_SECONDS, copy.deepcopy(value))
    return value


def _forget(*keys) -> None:
    with _lock:
        for k in keys:
            _cache.pop(k, None)


def reset_caches() -> None:
    """Tests, and after changing NEO4J_* env: drop cached reads and schema/driver state."""
    with _lock:
        _cache.clear()
        _ready.clear()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Neo4jState:
    def slugs(self) -> list[str]:
        return _cached(("slugs",), lambda: [r["slug"] for r in _run("MATCH (w:HfWorkspace) RETURN w.slug AS slug ORDER BY slug")])

    def exists(self, slug) -> bool:
        return self.read_workspace(slug) is not None

    def read_workspace(self, slug) -> dict | None:
        def load():
            rows = _run("MATCH (w:HfWorkspace {slug: $slug}) RETURN w.config AS c", slug=slug)
            return json.loads(rows[0]["c"]) if rows else None  # corrupt -> ValueError

        return _cached(("ws", slug), load)

    def write_workspace(self, slug, data: dict) -> None:
        _run("MERGE (w:HfWorkspace {slug: $slug}) SET w.config = $c, w.updated = $now",
             write=True, slug=slug, c=json.dumps(data), now=_now())
        _forget(("ws", slug), ("slugs",))

    def delete(self, slug) -> None:
        _run("MATCH (n) WHERE (n:HfWorkspace OR n:HfSecret OR n:HfSync) AND n.slug = $slug DETACH DELETE n", write=True, slug=slug)
        _run("MATCH (i:HfInvestigation {ws: $slug}) DELETE i", write=True, slug=slug)
        _run("MATCH (r:HfRun {ws: $slug}) DELETE r", write=True, slug=slug)
        _run("MATCH (m:HfMemory {ws: $slug}) DELETE m", write=True, slug=slug)
        _forget(("ws", slug), ("slugs",), ("secrets", slug), ("sync", slug))

    def read_secrets(self, slug) -> dict:
        def load():
            rows = _run("MATCH (s:HfSecret {slug: $slug}) RETURN s.blob AS b", slug=slug)
            f = _fernet()
            if not rows or f is None:
                return {}  # no key configured: stored keys are unreadable, treated as unset (env fallback still works)
            try:
                data = json.loads(f.decrypt(rows[0]["b"].encode()).decode())
            except Exception:  # wrong key / corrupt blob
                return {}
            return data if isinstance(data, dict) else {}

        return _cached(("secrets", slug), load)

    def write_secrets(self, slug, data: dict) -> None:
        f = _fernet()
        if f is None:
            raise ValueError("HACKFRONT_SECRET_KEY must be set on the server before keys can be saved to Neo4j")
        _run("MERGE (s:HfSecret {slug: $slug}) SET s.blob = $b, s.updated = $now",
             write=True, slug=slug, b=f.encrypt(json.dumps(data).encode()).decode(), now=_now())
        _forget(("secrets", slug))

    def put_investigation(self, ws, iid, doc: dict) -> None:
        m = _meta(doc)
        _run("MERGE (i:HfInvestigation {key: $key}) SET i.ws = $ws, i.id = $id, i.question = $q, i.file = $file, "
             "i.line = $line, i.confidence = $conf, i.created_at = $created, i.owner = $owner, i.doc = $doc",
             write=True, key=f"{ws}/{iid}", ws=ws, id=iid, q=m["question"], file=m["file"], line=m["line"],
             conf=m["confidence"], created=m["created_at"] or _now(), owner=m.get("owner"), doc=json.dumps(doc))

    def get_investigation(self, ws, iid) -> dict | None:
        rows = _run("MATCH (i:HfInvestigation {key: $key}) RETURN i.doc AS d", key=f"{ws}/{iid}")
        try:
            return json.loads(rows[0]["d"]) if rows else None
        except ValueError:
            return None

    def list_investigations(self, ws, limit=200) -> list[dict]:
        rows = _run("MATCH (i:HfInvestigation {ws: $ws}) RETURN i.id AS id, i.question AS question, i.file AS file, "
                    "i.line AS line, i.confidence AS confidence, i.created_at AS created_at, i.owner AS owner "
                    "ORDER BY i.created_at DESC LIMIT $n", ws=ws, n=limit)
        return [{k: v for k, v in r.items() if not (k == "owner" and v is None)} for r in rows]

    def put_memory(self, ws, mid, doc: dict, expect: int | None = None) -> None:
        key, args = f"{ws}/{mid}", dict(ws=ws, id=mid, doc=json.dumps(doc), v=doc.get("version"))
        if expect is None:
            _run("MERGE (m:HfMemory {key: $key}) SET m.ws = $ws, m.id = $id, m.doc = $doc, m.version = $v", write=True, key=key, **args)
            return
        rows = _run("MATCH (m:HfMemory {key: $key}) WHERE m.version = $expect "  # compare-and-swap inside one query
                    "SET m.doc = $doc, m.version = $v RETURN count(m) AS n", write=True, key=key, expect=expect, **args)
        if not rows or rows[0]["n"] == 0:
            raise Stale("entry changed since it was read")

    def list_memory(self, ws) -> list[dict]:
        out = []
        for r in _run("MATCH (m:HfMemory {ws: $ws}) RETURN m.doc AS d", ws=ws):
            try:
                out.append(json.loads(r["d"]))
            except ValueError:
                continue
        return sorted(out, key=lambda e: e["created_at"], reverse=True)

    def read_sync(self, slug) -> dict | None:
        rows = _run("MATCH (s:HfSync {slug: $slug}) RETURN s.doc AS d", slug=slug)  # not cached: polled for live progress
        try:
            return json.loads(rows[0]["d"]) if rows else None
        except ValueError:
            return None

    def write_sync(self, slug, data: dict) -> None:
        if not self.exists(slug):
            raise FileNotFoundError("workspace deleted")
        _run("MERGE (s:HfSync {slug: $slug}) SET s.doc = $d, s.updated = $now", write=True, slug=slug, d=json.dumps(data), now=_now())

    # ---- users
    def read_user(self, uid) -> dict | None:
        rows = _run("MATCH (u:HfUser {uid: $uid}) RETURN u.doc AS d", uid=uid)
        try:
            return json.loads(rows[0]["d"]) if rows else None
        except ValueError:
            return None

    def write_user(self, uid, data: dict) -> None:
        _run("MERGE (u:HfUser {uid: $uid}) SET u.doc = $d, u.updated = $now", write=True, uid=uid, d=json.dumps(data), now=_now())

    def users_exist(self) -> bool:
        return bool(_run("MATCH (u:HfUser) RETURN u.uid AS uid LIMIT 1"))

    def read_user_secrets(self, uid) -> dict:
        def load():
            rows = _run("MATCH (s:HfUserSecret {uid: $uid}) RETURN s.blob AS b", uid=uid)
            f = _fernet()
            if not rows or f is None:
                return {}
            try:
                data = json.loads(f.decrypt(rows[0]["b"].encode()).decode())
            except Exception:  # wrong key / corrupt blob
                return {}
            return data if isinstance(data, dict) else {}

        return _cached(("usecrets", uid), load)

    def write_user_secrets(self, uid, data: dict) -> None:
        f = _fernet()
        if f is None:
            raise ValueError("HACKFRONT_SECRET_KEY must be set on the server before keys can be saved to Neo4j")
        _run("MERGE (s:HfUserSecret {uid: $uid}) SET s.blob = $b, s.updated = $now",
             write=True, uid=uid, b=f.encrypt(json.dumps(data).encode()).decode(), now=_now())
        _forget(("usecrets", uid))

    # ---- sync run history
    def put_run(self, ws, rid, doc: dict) -> None:
        _run("MERGE (r:HfRun {key: $key}) SET r.ws = $ws, r.id = $id, r.started = $started, r.doc = $doc",
             write=True, key=f"{ws}/{rid}", ws=ws, id=rid, started=doc.get("started_at") or _now(), doc=json.dumps(doc))

    def get_run(self, ws, rid) -> dict | None:
        rows = _run("MATCH (r:HfRun {key: $key}) RETURN r.doc AS d", key=f"{ws}/{rid}")
        try:
            return json.loads(rows[0]["d"]) if rows else None
        except ValueError:
            return None

    def list_runs(self, ws, limit=50) -> list[dict]:
        rows = _run("MATCH (r:HfRun {ws: $ws}) RETURN r.doc AS d ORDER BY r.started DESC LIMIT $n", ws=ws, n=limit)
        out = []
        for r in rows:
            try:
                out.append(json.loads(r["d"]))
            except ValueError:
                continue
        return out


# ---------------------------------------------------------------- migration (file -> neo4j)
def migrate(src: FileState, dst: Neo4jState, overwrite: bool = False) -> dict:
    """Copy every workspace (config, keys, investigations, last sync) from the file backend into Neo4j."""
    done = {"workspaces": 0, "secrets": 0, "investigations": 0, "skipped": [], "secrets_skipped": []}
    for slug in src.slugs():
        if dst.exists(slug) and not overwrite:
            done["skipped"].append(slug)
            continue
        dst.write_workspace(slug, src.read_workspace(slug))
        done["workspaces"] += 1
        secrets = src.read_secrets(slug)
        if secrets:
            try:
                dst.write_secrets(slug, secrets)
                done["secrets"] += 1
            except ValueError:
                done["secrets_skipped"].append(slug)
        for meta in src.list_investigations(slug, limit=10_000):
            doc = src.get_investigation(slug, meta["id"])
            if doc:
                dst.put_investigation(slug, meta["id"], doc)
                done["investigations"] += 1
        sync = src.read_sync(slug)
        if sync:
            dst.write_sync(slug, sync)
    return done
