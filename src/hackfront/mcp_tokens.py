"""Per-workspace MCP bearer tokens. One live token per workspace; only its SHA-256 is stored (in the workspace's
secrets record, next to the API keys), so the token is shown once at issue time and cannot be read back.

Token format: `hfm_<workspace slug>.<random>`. The slug routes the lookup; the random part is the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from . import config, state

PREFIX, KEY = "hfm_", "mcp_token_hash"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue(slug: str) -> str:
    """Create (or rotate) the workspace's token and return it. The previous token stops working immediately."""
    slug = config.check_slug(slug)
    backend = state.backend()
    if not backend.exists(slug):
        raise LookupError("workspace not found")
    token = f"{PREFIX}{slug}.{secrets.token_urlsafe(32)}"
    backend.write_secrets(slug, {**backend.read_secrets(slug), KEY: _digest(token)})
    return token


def revoke(slug: str) -> bool:
    slug = config.check_slug(slug)
    backend = state.backend()
    data = backend.read_secrets(slug)
    if KEY not in data:
        return False
    data.pop(KEY)
    backend.write_secrets(slug, data)
    return True


def verify(token: str | None) -> str | None:
    """The workspace slug a valid token belongs to, else None (constant-time compare; never raises)."""
    try:
        if not token or not token.startswith(PREFIX) or "." not in token or len(token) > 200:
            return None
        slug = config.check_slug(token[len(PREFIX):].split(".", 1)[0])
        stored = state.backend().read_secrets(slug).get(KEY)
        return slug if stored and hmac.compare_digest(stored, _digest(token)) else None
    except Exception:  # noqa: BLE001 - unknown workspace, bad slug, unreadable state: all mean "not valid"
        return None
