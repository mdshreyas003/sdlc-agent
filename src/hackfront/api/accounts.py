"""Accounts, user model settings, sync run history and ingestion overview (docs/accounts-and-settings-api.md).

Every error message returned here is a fixed, safe string: no exception text, URLs, tokens or response bodies.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import auth, config, state

router = APIRouter()
MODEL_RE = re.compile(r"[\w.:/\-]{1,100}")
AZURE_SUFFIXES = (".azure.com", ".azure.us", ".azure.cn", ".azure.net")
LABELS = {"azure": "Azure OpenAI", "sarvam": "Sarvam", "openai": "OpenAI-compatible (server)"}
FIELDS = {
    "azure": [("azure_endpoint", "Endpoint", False), ("azure_key", "API key", True)],
    "sarvam": [("sarvam_key", "API key", True)],
    "openai": [],
}


# ---------------------------------------------------------------- session + sign-in
def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _base(request: Request) -> str:
    """The browser-facing origin: HACKFRONT_PUBLIC_URL, else what the web proxy forwarded, else this request's own host
    (which, behind the proxy, is the API's address and is NOT what GitHub has registered)."""
    host = request.headers.get("x-forwarded-host")
    proto = request.headers.get("x-forwarded-proto", "https" if _secure(request) else "http")
    if host and re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?", host) and proto in ("http", "https"):
        return auth.public_url(f"{proto}://{host}")
    return auth.public_url(f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}")


@router.get("/api/me")
def me(request: Request):
    mode = auth.mode()
    user = auth.current() if mode == "enabled" else (auth.LOCAL if mode == "disabled" else None)
    out = {"auth": "enabled" if mode != "disabled" else "disabled", "methods": auth.methods() if mode != "disabled" else [],
           "user": user.public() if user else None}
    if "github" in out["methods"]:
        out["callback_url"] = f"{_base(request)}/api/auth/github/callback"  # what the GitHub OAuth app must list, exactly
    return out


@router.get("/api/auth/github/login")
def login(request: Request, next: str = "/"):  # noqa: A002  query parameter name is part of the contract
    if auth.mode() != "enabled" or "github" not in auth.methods():
        return JSONResponse({"detail": "Sign-in is not configured on this server"}, 503)
    nonce = auth.new_nonce()
    response = RedirectResponse(auth.authorize_url(nonce, auth.safe_next(next), _base(request)), 302)
    response.set_cookie(auth.STATE_COOKIE, nonce, max_age=600, httponly=True, samesite="lax", secure=_secure(request), path="/")
    return response


@router.get("/api/auth/github/callback")
def callback(request: Request, code: str = "", state_: str = ""):
    params = request.query_params
    code, packed = params.get("code", code), params.get("state", state_)
    fail = lambda why: RedirectResponse(f"/login?error={why}", 302)  # noqa: E731
    if auth.mode() != "enabled" or "github" not in auth.methods():
        return fail("not_configured")
    claim = auth.read_state(packed)
    nonce = request.cookies.get(auth.STATE_COOKIE)
    if not claim or not nonce or claim.get("n") != nonce:
        return fail("state")
    if not code:
        return fail("denied")
    try:
        profile = auth.exchange_code(code, _base(request))
        if not auth.github_allowed(profile.login):
            return fail("not_allowed")
        user, _ = auth.register(profile)
    except auth.OAuthError as error:
        return fail(error.code)
    response = RedirectResponse(auth.safe_next(claim.get("next")), 302)
    response.set_cookie(auth.COOKIE, auth.make_session(user.id), max_age=auth.SESSION_SECONDS, httponly=True,
                        samesite="lax", secure=_secure(request), path="/")
    response.delete_cookie(auth.STATE_COOKIE, path="/")
    return response


def _session(request: Request, user: auth.User, body: dict) -> JSONResponse:
    response = JSONResponse({"ok": True, "user": user.public(), **body})
    response.set_cookie(auth.COOKIE, auth.make_session(user.id), max_age=auth.SESSION_SECONDS, httponly=True,
                        samesite="lax", secure=_secure(request), path="/")
    return response


def _password_enabled() -> None:
    if auth.mode() != "enabled" or "password" not in auth.methods():
        raise HTTPException(503, "Email sign-in is not enabled on this server")


def _credentials(body: dict) -> tuple[str, str]:
    try:
        email = auth.normalize_email(str(body.get("email", "")))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    password = body.get("password")
    if not isinstance(password, str):
        raise HTTPException(422, "Enter your password")
    return email, password


@router.post("/api/auth/signup")
def signup(request: Request, body: dict = Body(...)):  # noqa: B008  FastAPI idiom
    _password_enabled()
    email, password = _credentials(body)
    if len(password) < auth.MIN_PASSWORD or len(password) > 200:
        raise HTTPException(422, f"Password must be {auth.MIN_PASSWORD}-200 characters")
    if not auth.email_allowed(email):
        raise HTTPException(403, "Sign-ups are limited on this server; ask its owner for access")
    uid = auth.email_user_id(email)
    if state.backend().read_user(uid):
        raise HTTPException(409, "An account with this email already exists")
    name = str(body.get("name") or "").strip()[:80] or email.split("@")[0]
    user, claimed = auth.register(auth.User(uid, email, name), auth.hash_password(password), email)
    return _session(request, user, {"claimed_workspaces": claimed})


@router.post("/api/auth/login")
def login_password(request: Request, body: dict = Body(...)):  # noqa: B008  FastAPI idiom
    _password_enabled()
    email, password = _credentials(body)
    key = f"{request.client.host if request.client else '?'}|{email}"
    if auth.throttled(key):
        raise HTTPException(429, "Too many attempts; try again in a few minutes")
    doc = state.backend().read_user(auth.email_user_id(email))
    if not auth.email_allowed(email):  # removing someone from the allowlist also locks them out
        auth.verify_password(password, None)
        auth.note_failure(key)
        raise HTTPException(401, "Incorrect email or password")
    if not auth.verify_password(password, (doc or {}).get("password")):
        auth.note_failure(key)
        raise HTTPException(401, "Incorrect email or password")  # same answer for an unknown email
    auth.clear_failures(key)
    uid = auth.email_user_id(email)
    return _session(request, auth.User(uid, doc.get("login", email), doc.get("name", ""), doc.get("avatar_url", "")), {})


@router.post("/api/auth/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE, path="/")
    return response


# ---------------------------------------------------------------- user models
@contextmanager
def _as_user(uid: str):
    from ..agent import llm

    wt, ut = llm._workspace.set(None), llm._user.set(uid)
    try:
        yield llm
    finally:
        llm._workspace.reset(wt)
        llm._user.reset(ut)


def _source(uid: str, key: str) -> str | None:
    found = config.secret_source(None, key, uid)
    return "user" if found == "user" else "server" if found == "env" else None


def _models(uid: str) -> dict:
    status = config.user_secret_status(uid)
    with _as_user(uid) as llm:
        providers = []
        for name in llm.PROVIDERS:
            fields = [{"key": k, "label": label, "secret": secret, "set": status[k]["set"],
                       **({"hint": status[k]["hint"]} if secret and status[k]["set"] else {}),
                       **({"value": status[k]["value"]} if not secret and status[k]["set"] else {})}
                      for k, label, secret in FIELDS.get(name, [])]
            configured = llm.configured(name)
            key_source = {"azure": "azure_key", "sarvam": "sarvam_key"}.get(name)
            source = (_source(uid, key_source) if key_source else ("server" if configured else None)) if configured else None
            providers.append({"name": name, "label": LABELS.get(name, name), "model": llm.model_for(name),
                              "configured": configured, "source": source, "editable": bool(fields), "fields": fields})
        default = llm.default_provider()
        mine = state.backend().read_user_secrets(uid)
        chosen = mine.get("llm_provider") or ""
        return {
            "providers": providers,
            "default": {"provider": default, "model": llm.model_for(default),
                        "source": "user" if chosen or mine.get("llm_model") else "server"},
            "selected": {"provider": chosen, "model": mine.get("llm_model") or ""},
        }


def _checked(body: dict) -> dict:
    from ..agent import llm

    unknown = set(body) - set(config.MODEL_KEYS)
    if unknown:
        raise HTTPException(422, f"unknown setting: {sorted(unknown)[0]}")
    endpoint = body.get("azure_endpoint")
    if endpoint:
        parts = urlsplit(str(endpoint).strip())
        if parts.scheme != "https" or not (parts.hostname or "").endswith(AZURE_SUFFIXES):
            raise HTTPException(422, "azure_endpoint must be an https Azure URL (*.azure.com); the key is sent to this host")
    if body.get("llm_provider") and body["llm_provider"] not in llm.PROVIDERS:
        raise HTTPException(422, "unknown provider")
    if body.get("llm_model") and not MODEL_RE.fullmatch(str(body["llm_model"])):
        raise HTTPException(422, "invalid model name")
    return body


@router.get("/api/me/models")
def get_models():
    return _models(auth.user_id())


@router.put("/api/me/models")
def put_models(body: dict = Body(...)):  # noqa: B008  FastAPI idiom
    uid = auth.user_id()
    try:
        config.set_user_secrets(uid, _checked(body))
    except ValueError as error:  # messages name only the key, never a value
        raise HTTPException(422, str(error)) from None
    return _models(uid)


@router.post("/api/me/models/{provider}/test")
def test_model(provider: Literal["azure", "sarvam", "openai"]):
    uid = auth.user_id()
    with _as_user(uid) as llm:
        try:
            llm.ping(provider)
            return {"ok": True, "detail": "Model replied", "account": f"{provider} ({llm.model_for(provider)})"}
        except RuntimeError as error:  # llm.ping raises only fixed safe messages
            return {"ok": False, "detail": str(error)}
        except Exception:  # noqa: BLE001
            return {"ok": False, "detail": "Network error"}


# ---------------------------------------------------------------- runs + ingestion
_META = ("id", "state", "mode", "started_at", "finished_at", "complete", "totals", "triggered_by")


def run_meta(doc: dict) -> dict:
    return {k: doc.get(k) for k in _META if doc.get(k) is not None}


@router.get("/api/w/{ws}/runs")
def list_runs(ws: str):
    _known(ws)
    return [run_meta(r) for r in state.backend().list_runs(ws, 50)]


@router.get("/api/w/{ws}/runs/{rid}")
def get_run(ws: str, rid: str):
    _known(ws)
    found = state.backend().get_run(ws, rid) if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", rid) else None
    if found is None:
        raise HTTPException(404, "run not found")
    return found


def _known(ws: str) -> dict:
    try:
        return config.load_workspace(ws)
    except (LookupError, ValueError):
        raise HTTPException(404, "workspace not found") from None


# What a sync pulls per target, mirroring ingest/sync.py (_github/_jira/_slack). Every stream is read newest first and
# stops at the page cap (standard 20 pages, deep 100), so history older than the cap is not fetched until a deeper run.
# `page` is items per page; a stream with no `page` runs once per parent item (PR, issue, thread), capped per parent.
PLAN = {
    "github": [
        {"stream": "commits", "label": "Commits", "order": "newest commit first", "page": 100, "includes": "message, author, changed paths, diff patches (used for line blame)"},
        {"stream": "pulls", "label": "Pull requests", "order": "most recently updated first", "page": 100, "includes": "title, description, state, commits it contains"},
        {"stream": "pr_activity", "label": "PR discussion", "order": "per pull request", "page": None, "includes": "issue comments, reviews and review comments of every fetched PR"},
    ],
    "jira": [
        {"stream": "issues", "label": "Issues", "order": "most recently updated first", "page": 100, "includes": "summary, description, status, links"},
        {"stream": "comments", "label": "Issue comments", "order": "per issue", "page": None, "includes": "comments of every fetched issue"},
    ],
    "slack": [
        {"stream": "history", "label": "Messages", "order": "newest message first", "page": 15, "includes": "channel messages (also the mailing-list stand-in)"},
        {"stream": "replies", "label": "Thread replies", "order": "per thread", "page": None, "includes": "replies of every fetched thread"},
    ],
}
PAGES = {"standard": 20, "deep": 100}


def _plan(scopes: dict) -> dict:
    sources = []
    for source, targets in (("github", scopes["repos"]), ("jira", scopes["jira"]), ("slack", scopes["slack"])):
        for target in targets:
            sources.append({"source": source, "target": target, "streams": [
                {**spec, "max": {m: (n * spec["page"] if spec["page"] else None) for m, n in PAGES.items()}} for spec in PLAN[source]]})
    return {"pages": PAGES, "order": "newest first", "incremental": False, "idempotent": True, "sources": sources,
            "notes": ["Each run starts again from the newest records; there is no saved cursor yet.",
                      "Re-running never duplicates anything: items and links are written idempotently.",
                      "A stream that hits the page cap is marked incomplete: older history exists that was not fetched. Run a Deep sync for more."]}


TIMELINE_Q = ("MATCH (a:Artifact) WHERE NOT coalesce(a.is_stub, false) AND a.scope IN $scopes AND a.event_time IS NOT NULL "
              "RETURN a.provider AS source, a.record_kind AS kind, min(a.event_time) AS oldest, max(a.event_time) AS newest, "
              "count(a) AS count ORDER BY source, kind LIMIT 60")

BY_SOURCE_Q = ("MATCH (a:Artifact) WHERE NOT coalesce(a.is_stub, false) AND a.scope IN $scopes "
               "RETURN a.provider AS source, a.record_kind AS kind, count(a) AS count ORDER BY count DESC LIMIT 40")


@router.get("/api/w/{ws}/ingestion")
def ingestion(ws: str):
    from neo4j import READ_ACCESS

    from .mapping import flat_scopes
    from .workspaces import _graph_facts

    _known(ws)
    scopes = config.scopes(ws)
    indexed, neo4j = _graph_facts(scopes)
    counts = neo4j.get("counts") if neo4j.get("ok") else None
    by_source: list[dict] = []
    timeline: list[dict] = []
    if neo4j.get("ok"):
        try:
            driver = config.neo4j_driver()
            with driver.session(database=config.neo4j_database(), default_access_mode=READ_ACCESS) as session:
                by_source = [dict(r) for r in session.run(BY_SOURCE_Q, scopes=flat_scopes(scopes)).data()]
                timeline = [dict(r) for r in session.run(TIMELINE_Q, scopes=flat_scopes(scopes)).data()]
            driver.close()
        except Exception:  # noqa: BLE001  breakdown is best-effort
            by_source, timeline = [], []
    runs = state.backend().list_runs(ws, 1)
    last = run_meta(runs[0]) if runs else None
    repos = [{"repo": r, "indexed": r in indexed} for r in scopes["repos"]]
    fetched = (last or {}).get("totals", {}).get("fetched", 0)
    stored = (last or {}).get("totals", {}).get("persisted", 0)
    ok = lambda cond, any_: "ok" if cond else ("idle" if not any_ else "warn")  # noqa: E731
    stages = [
        {"key": "fetched", "label": "Fetched", "count": fetched, "status": ok(fetched > 0, last)},
        {"key": "stored", "label": "Stored", "count": (counts or {}).get("artifacts", stored), "status": ok(bool(counts and counts.get("artifacts")), last)},
        {"key": "linked", "label": "Linked", "count": (counts or {}).get("edges", 0), "status": ok(bool(counts and counts.get("edges")), last)},
        {"key": "indexed", "label": "Repos indexed", "count": len(indexed), "status": ok(bool(repos) and len(indexed) == len(repos), bool(repos))},
    ]
    graph = {"artifacts": counts.get("artifacts", 0), "edges": counts.get("edges", 0), "stubs": counts.get("stubs", 0)} if counts else None
    streams = [{k: st.get(k) for k in ("stream", "status", "pages", "fetched", "persisted")} | {"errors": len(st.get("errors") or [])}
               for st in (runs[0].get("streams") or [])] if runs else []
    return {"neo4j": {"ok": bool(neo4j.get("ok"))}, "graph": graph, "by_source": by_source, "repos": repos,
            "last_run": last, "stages": stages, "plan": _plan(scopes), "timeline": timeline, "last_streams": streams}
