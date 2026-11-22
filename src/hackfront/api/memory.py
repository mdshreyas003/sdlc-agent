"""Memory endpoints (docs/memory.md): list, triage an anchor, edit, move through the lifecycle. Errors are safe messages."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hackfront import auth, config, memory, state

router = APIRouter()


class TriageBody(BaseModel):
    anchor: str  # PR number (#18720), ticket key, file path or words: what a new PR/change touches


class EditBody(BaseModel):
    version: int
    title: str | None = None
    body: str | None = None
    kind: str | None = None


class MoveBody(BaseModel):
    version: int
    reason: str = ""


def _store(ws: str):
    try:
        config.scopes(ws)  # 404 for an unknown workspace
    except (ValueError, LookupError):
        raise HTTPException(404, "Workspace not found") from None
    return state.backend()


def _who() -> str:
    user = auth.current()
    return (user.login or user.name or user.id) if user else "local"


def _entry(store, ws: str, mid: str) -> dict:
    found = next((e for e in store.list_memory(ws) if e["id"] == mid), None)
    if found is None:
        raise HTTPException(404, "Memory entry not found")
    return found


def _save(store, ws: str, old: dict, new: dict) -> None:
    try:
        store.put_memory(ws, new["id"], new, expect=old["version"])
    except state.Stale:
        raise HTTPException(409, "Changed by someone else while you were saving. Reload and try again.") from None


def _guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except memory.Conflict as error:
        raise HTTPException(409, str(error)) from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/api/w/{ws}/memory")
def list_memory(ws: str, status: str | None = None) -> dict:
    items = _store(ws).list_memory(ws)
    counts = {s: sum(e["status"] == s for e in items) for s in (*memory.OPEN, *memory.DONE)}
    return {"counts": counts, "items": [e for e in items if status in (None, e["status"])]}


@router.post("/api/w/{ws}/memory/triage")
def triage(ws: str, body: TriageBody) -> dict:
    """The hook a new PR/change calls: gather evidence for the anchor, then create, refine or skip. Never approves."""
    store = _store(ws)
    anchor = body.anchor.strip()
    if not 1 <= len(anchor) <= 200:
        raise HTTPException(422, "anchor must be 1-200 characters")
    from hackfront.agent.harness import Harness
    from hackfront.mcp_server import why

    from .mapping import flat_scopes

    try:
        driver = config.neo4j_driver()
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "Neo4j unreachable or not configured") from None
    found = why(Harness(driver, scopes=flat_scopes(config.scopes(ws))), anchor)
    if found["refused"]:
        return {"action": "nothing", "entry": None, "note": found["note"]}
    existing = store.list_memory(ws)
    out = memory.propose(existing, anchor, found["evidence"], _who())
    if out["action"] == "created":
        store.put_memory(ws, out["entry"]["id"], out["entry"])
    elif out["action"] == "refined":
        _save(store, ws, next(e for e in existing if e["id"] == out["entry"]["id"]), out["entry"])
    return out


@router.put("/api/w/{ws}/memory/{mid}")
def edit(ws: str, mid: str, body: EditBody) -> dict:
    store = _store(ws)
    old = _entry(store, ws, mid)
    new = _guard(memory.edit, old, body.version, _who(), body.title, body.body, body.kind)
    _save(store, ws, old, new)
    return new


@router.post("/api/w/{ws}/memory/{mid}/{action}")
def move(ws: str, mid: str, action: str, body: MoveBody) -> dict:
    store = _store(ws)
    old = _entry(store, ws, mid)
    new = _guard(memory.move, old, action, body.version, _who(), body.reason)
    _save(store, ws, old, new)
    return new
