"""Issue / revoke the workspace's MCP token (docs/adr/0001). The token is returned once and never stored in clear."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .. import config, mcp_tokens

router = APIRouter()


@router.post("/api/w/{ws}/mcp-token", status_code=201)
def issue_token(ws: str, request: Request) -> dict:
    try:
        token = mcp_tokens.issue(ws)
    except LookupError:
        raise HTTPException(404, "workspace not found") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    base = str(request.base_url).rstrip("/")
    return {"token": token, "url": f"{base}/mcp", "note": "Shown once. Issuing again replaces it."}


@router.delete("/api/w/{ws}/mcp-token")
def revoke_token(ws: str) -> dict:
    try:
        config.check_slug(ws)
        return {"ok": True, "revoked": mcp_tokens.revoke(ws)}
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
