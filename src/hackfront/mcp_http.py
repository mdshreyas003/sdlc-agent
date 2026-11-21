"""The MCP server over Streamable HTTP, mounted on the API at `/mcp` (agents connect to `https://<api>/mcp`).

Auth is a per-workspace bearer token (`mcp_tokens`), checked before any MCP handling; the workspace comes from the token,
never from the request. Agents never see Neo4j credentials. Stateless (each POST is independent, JSON responses), so it
works on a single Render instance and on serverless. A small in-process rate limit bounds a leaked token's blast radius.
"""

from __future__ import annotations

import contextvars
import json
import time
from collections import defaultdict, deque

from . import config, mcp_tokens
from .agent.harness import Harness
from .mcp_server import build_server

PATH, LIMIT, WINDOW_S = "/mcp", 60, 60.0
_workspace: contextvars.ContextVar[str | None] = contextvars.ContextVar("mcp_workspace", default=None)
_hits: dict[str, deque] = defaultdict(deque)


def _harness() -> Harness:
    from .api.mapping import flat_scopes  # lazy: importing hackfront.api loads the app, which imports this module

    slug = _workspace.get()
    if not slug:
        raise RuntimeError("no workspace for this request")
    return Harness(config.neo4j_driver(), scopes=flat_scopes(config.scopes(slug)))


def _allowed(slug: str, now: float | None = None) -> bool:
    now, q = now or time.monotonic(), _hits[slug]
    while q and now - q[0] > WINDOW_S:
        q.popleft()
    if len(q) >= LIMIT:
        return False
    q.append(now)
    return True


async def _reply(send, status: int, detail: str, headers: list | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), *(headers or [])]})
    await send({"type": "http.response.body", "body": body})


class TokenAuth:
    """ASGI gate: only POST/GET/DELETE on exactly /mcp with a valid workspace token reach the MCP app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] != PATH:
            return await _reply(send, 404, "not found")
        header = dict(scope["headers"]).get(b"authorization", b"").decode()
        slug = mcp_tokens.verify(header[7:].strip()) if header[:7].lower() == "bearer " else None
        if slug is None:
            return await _reply(send, 401, "unauthorized", [(b"www-authenticate", b"Bearer")])
        if not _allowed(slug):
            return await _reply(send, 429, "rate limit exceeded", [(b"retry-after", b"60")])
        reset = _workspace.set(slug)
        try:
            await self.app(scope, receive, send)
        finally:
            _workspace.reset(reset)


def build_app():
    """(gate-wrapped ASGI app, inner Starlette app). The inner app's lifespan must run with the host app's."""
    from mcp.server.transport_security import TransportSecuritySettings

    server = build_server(harness_for=lambda: _harness(), workspace_for=_workspace.get)  # looked up per call
    inner = server.streamable_http_app(
        streamable_http_path=PATH, stateless_http=True, json_response=True,
        # Host/Origin checks defend ambient-credential (cookie) servers from DNS rebinding; this one only accepts an
        # explicit bearer token, and its public hostname is not known at build time.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return TokenAuth(inner), inner
