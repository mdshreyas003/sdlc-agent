"""Operator-only import of a migration bundle (migrations/bundle.py): loads data into the API's own Neo4j over HTTPS.

Disabled (404) unless HACKFRONT_ADMIN_TOKEN is set on the host; then every call needs that value in the
X-Hackfront-Admin-Token header, on top of the usual HACKFRONT_ACCESS_TOKEN bearer check (app.py). The UI proxy never
forwards this header, so the browser cannot reach the route even though the proxy holds the access token.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..migrations import bundle

router = APIRouter()
log = logging.getLogger(__name__)


@router.post(bundle.PATH, include_in_schema=False)
async def import_bundle(request: Request) -> dict:
    token = os.environ.get("HACKFRONT_ADMIN_TOKEN", "")
    if not token:
        raise HTTPException(404, "Not Found")
    supplied = request.headers.get(bundle.ADMIN_HEADER, "")
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(403, "admin token required")
    body = await request.body()
    try:
        doc = bundle.inflate(body)
        return await run_in_threadpool(bundle.apply, doc)
    except ValueError as error:  # our own validation messages: safe to return
        raise HTTPException(422, str(error)) from None
    except Exception as error:  # noqa: BLE001  never echo driver messages (may carry URIs)
        log.exception("bundle import failed")
        raise HTTPException(500, f"import failed ({type(error).__name__}); see server logs") from None
