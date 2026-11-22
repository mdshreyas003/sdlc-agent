"""FastAPI app: routers only (docs/workbench-api.md). Errors to clients are safe messages only."""

from __future__ import annotations

import hmac
import os
import re
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from hackfront import auth, config, state

config.load_env()
# The Next.js UI (web/) proxies /api/* here from whatever local port it runs on, so any localhost origin is trusted;
# extra origins (e.g. a LAN address) go in HACKFRONT_ORIGINS, comma-separated.
ALLOWED_ORIGINS = set(filter(None, os.environ.get("HACKFRONT_ORIGINS", "").split(",")))
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
app = FastAPI(title="hackfront", docs_url=None, redoc_url=None)


def trusted_origin(origin: str, host: str | None) -> bool:
    parts = urlsplit(origin)
    return (origin in ALLOWED_ORIGINS or parts.netloc == host
            or (parts.scheme in ("http", "https") and parts.hostname in LOCAL_HOSTS))


@app.middleware("http")
async def guard(request, call_next):
    """(1) Deployed API: when HACKFRONT_ACCESS_TOKEN is set every /api/* call needs `Authorization: Bearer <token>`
    (the Vercel proxy adds it server-side). (2) CSRF: a web page on another site must not drive state-changing routes."""
    token = os.environ.get("HACKFRONT_ACCESS_TOKEN", "")
    if token and request.url.path.startswith("/api/"):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD") and origin and not trusted_origin(origin, request.headers.get("host")):
        return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
    path = request.url.path
    user = auth.authenticate(request.cookies.get(auth.COOKIE))
    if path.startswith("/api/") and not PUBLIC.match(path):
        if auth.mode() == "misconfigured":
            return JSONResponse({"detail": "Authentication is not configured on this server"}, status_code=503)
        if user is None:
            return JSONResponse({"detail": "sign in required"}, status_code=401)
        slug = _workspace_slug(path, request.method)
        if slug and auth.enabled() and not _may_open(slug, user):
            return JSONResponse({"detail": "workspace not found"}, status_code=404)  # never reveal that it exists
    token_ = auth.set_current(user)
    try:
        return await call_next(request)
    finally:
        auth.reset_current(token_)


PUBLIC = re.compile(r"^/api/(me|auth/.*)$")
_WS_PATH = re.compile(r"^/api/w/([^/]+)(?:/|$)")
_WS_DELETE = re.compile(r"^/api/workspaces/([^/]+)$")


def _workspace_slug(path: str, method: str) -> str | None:
    m = _WS_PATH.match(path) or (_WS_DELETE.match(path) if method == "DELETE" else None)
    return m.group(1) if m else None


def _may_open(slug: str, user) -> bool:
    """False only when the workspace exists and belongs to somebody else; unknown slugs fall through to the route's 404."""
    try:
        raw = state.backend().read_workspace(config.check_slug(slug))
    except Exception:  # noqa: BLE001  bad slug / unreadable record: the route reports it
        return True
    return raw is None or auth.can_access(raw, user)


@app.get("/health")
def health() -> dict:
    return {"ok": True}  # unauthenticated, for the host's health check; reveals nothing


from . import accounts, admin, investigate, memory, sync, workbench, workspaces  # noqa: E402  (routers; after app + middleware exist)

for module in (accounts, workspaces, sync, workbench, investigate, memory, admin):
    app.include_router(module.router)
