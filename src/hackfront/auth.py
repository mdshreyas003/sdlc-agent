"""Accounts: GitHub OAuth sign-in, signed session cookies, the current user, and workspace access rules.

Disabled by default for local use (every request runs as the implicit user `local`). Enabled when
GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET are set. See docs/accounts-and-settings-api.md.
Every message that can reach a client is a fixed safe string: no tokens, codes or upstream bodies.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.parse
import urllib.request
from contextvars import ContextVar
from dataclasses import dataclass

from . import config, state

COOKIE = "hf_session"
STATE_COOKIE = "hf_oauth"
SESSION_SECONDS = 30 * 24 * 3600
LOCAL_ID = "local"
_SAFE_NEXT = re.compile(r"/(?!/)[A-Za-z0-9_\-./?=&%]*")


@dataclass(frozen=True)
class User:
    id: str
    login: str
    name: str = ""
    avatar_url: str = ""

    def public(self) -> dict:
        return {"id": self.id, "login": self.login, "name": self.name or self.login, "avatar_url": self.avatar_url}


LOCAL = User(LOCAL_ID, "local", "Local user")
_current: ContextVar[User | None] = ContextVar("hf_user", default=None)


# ---------------------------------------------------------------- mode
def methods() -> list[str]:
    """Sign-in methods switched on: 'github' (OAuth app configured), 'password' (HACKFRONT_AUTH=password)."""
    forced = os.environ.get("HACKFRONT_AUTH", "").lower()
    out = []
    if os.environ.get("GITHUB_OAUTH_CLIENT_ID") and os.environ.get("GITHUB_OAUTH_CLIENT_SECRET"):
        out.append("github")
    if forced == "password":
        out.append("password")
    return out


def mode() -> str:
    """'disabled' (implicit local user), 'enabled' (a method is on and sessions can be signed), or 'misconfigured'."""
    forced = os.environ.get("HACKFRONT_AUTH", "").lower()
    if forced == "off":
        return "disabled"
    if methods() and _session_key():
        return "enabled"
    if forced == "required" or methods():
        return "misconfigured"  # a method set but no signing secret, or auth demanded with none: never fall open
    return "disabled"


def enabled() -> bool:
    return mode() != "disabled"


def _session_key() -> bytes:
    return (os.environ.get("HACKFRONT_SECRET_KEY") or "").encode()


# ---------------------------------------------------------------- current user
def current() -> User | None:
    """The signed-in user for this request (the implicit local user when auth is disabled)."""
    return _current.get()


def set_current(user: User | None):
    return _current.set(user)


def reset_current(token) -> None:
    _current.reset(token)


def user_id() -> str:
    u = current()
    return u.id if u else LOCAL_ID


# ---------------------------------------------------------------- sessions
def _sign(payload: str) -> str:
    return hmac.new(_session_key(), payload.encode(), hashlib.sha256).hexdigest()


def make_session(uid: str, now: float | None = None) -> str:
    payload = f"{uid}.{int((now or time.time()) + SESSION_SECONDS)}"
    return f"{payload}.{_sign(payload)}"


def read_session(cookie: str | None, now: float | None = None) -> User | None:
    """The user a valid, unexpired session cookie names, else None."""
    if not cookie or not _session_key():
        return None
    uid, _, rest = cookie.partition(".")
    expires, _, sig = rest.partition(".")
    if not (uid and expires.isdigit() and sig) or not hmac.compare_digest(sig, _sign(f"{uid}.{expires}")):
        return None
    if int(expires) < (now or time.time()):
        return None
    try:
        doc = state.backend().read_user(config.check_user(uid))
    except ValueError:
        return None
    if not doc:
        return None
    return User(uid, doc.get("login", uid), doc.get("name", ""), doc.get("avatar_url", ""))


def authenticate(cookie: str | None) -> User | None:
    """Disabled -> the local user; enabled -> the session's user or None; misconfigured -> None."""
    m = mode()
    if m == "disabled":
        return LOCAL
    return read_session(cookie) if m == "enabled" else None


def upsert_user(user: User) -> User:
    state.backend().write_user(config.check_user(user.id), {
        "login": user.login, "name": user.name, "avatar_url": user.avatar_url,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return user


# ---------------------------------------------------------------- email + password
MIN_PASSWORD = 10
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}")
_SCRYPT = dict(n=2**14, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
_attempts: dict[str, list[float]] = {}
MAX_FAILURES, WINDOW = 5, 600.0


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address")
    return email


def email_user_id(email: str) -> str:
    return "em-" + hashlib.sha256(email.encode()).hexdigest()[:20]


def _allowed(env: str, value: str) -> bool:
    """True when the allowlist `env` is unset (open) or `value` matches an entry (exact, or `@domain.com` for emails)."""
    entries = [e.strip().lower() for e in os.environ.get(env, "").split(",") if e.strip()]
    value = value.lower()
    return not entries or any(value == e or (e.startswith("@") and value.endswith(e)) for e in entries)


def email_allowed(email: str) -> bool:
    """HACKFRONT_ALLOWED_EMAILS: comma-separated emails or @domain entries; unset = anyone may create an account."""
    return _allowed("HACKFRONT_ALLOWED_EMAILS", email)


def github_allowed(login: str) -> bool:
    """HACKFRONT_ALLOWED_GITHUB: comma-separated GitHub logins; unset = any GitHub account may sign in."""
    return _allowed("HACKFRONT_ALLOWED_GITHUB", login)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-work check: a missing or malformed hash still burns one scrypt so timing does not reveal accounts."""
    try:
        _, salt, digest = (stored or "").split("$")
        salt_b, want = base64.b64decode(salt), base64.b64decode(digest)
    except ValueError:
        salt_b, want = b"\0" * 16, b"\0" * 32
        stored = None
    got = hashlib.scrypt(password.encode(), salt=salt_b, **_SCRYPT)
    return stored is not None and hmac.compare_digest(got, want)


def throttled(key: str, now: float | None = None) -> bool:
    now = now or time.time()
    recent = [t for t in _attempts.get(key, []) if now - t < WINDOW]
    _attempts[key] = recent
    return len(recent) >= MAX_FAILURES


def note_failure(key: str, now: float | None = None) -> None:
    _attempts.setdefault(key, []).append(now or time.time())


def clear_failures(key: str) -> None:
    _attempts.pop(key, None)


def register(user: User, password_hash: str | None = None, email: str | None = None) -> tuple[User, bool]:
    """Create or refresh an account. The very first account ever created also takes ownership of every workspace that
    predates accounts (ownerless, non-demo), once. Returns (user, claimed_legacy)."""
    store = state.backend()
    first = not store.users_exist()
    doc = store.read_user(config.check_user(user.id)) or {}
    doc.update({"login": user.login, "name": user.name, "avatar_url": user.avatar_url,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    if email:
        doc["email"] = email
    if password_hash:
        doc["password"] = password_hash
    store.write_user(user.id, doc)
    claimed = False
    if first:
        for slug in store.slugs():
            raw = store.read_workspace(slug)
            if raw and not raw.get("owner") and not raw.get("demo"):
                store.write_workspace(slug, {**raw, "owner": user.id})
                claimed = True
    return user, claimed


# ---------------------------------------------------------------- GitHub OAuth
class OAuthError(Exception):
    """A sign-in failure; `code` is a short identifier the login page maps to a message."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def safe_next(value: str | None) -> str:
    return value if value and _SAFE_NEXT.fullmatch(value) and len(value) <= 300 else "/"


def public_url(fallback: str = "") -> str:
    return (os.environ.get("HACKFRONT_PUBLIC_URL") or fallback).rstrip("/")


def make_state(nonce: str, next_path: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"n": nonce, "next": next_path}).encode()).decode()
    return f"{body}.{_sign(body)}"


def read_state(value: str | None) -> dict | None:
    if not value or "." not in value or not _session_key():
        return None
    body, _, sig = value.rpartition(".")
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def authorize_url(nonce: str, next_path: str, base: str) -> str:
    query = urllib.parse.urlencode({
        "client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"], "scope": "read:user",
        "redirect_uri": f"{base}/api/auth/github/callback", "state": make_state(nonce, next_path)})
    return f"https://github.com/login/oauth/authorize?{query}"


def new_nonce() -> str:
    return secrets.token_urlsafe(16)


def _post_json(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  fixed https GitHub URL
        return json.loads(resp.read().decode())


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}",
                                               "User-Agent": "hackfront"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310  fixed https GitHub URL
        return json.loads(resp.read().decode())


def exchange_code(code: str, base: str) -> User:
    """Trade an OAuth code for the GitHub profile. Raises OAuthError with a safe code on any failure."""
    try:
        token = _post_json("https://github.com/login/oauth/access_token", {
            "client_id": os.environ["GITHUB_OAUTH_CLIENT_ID"], "client_secret": os.environ["GITHUB_OAUTH_CLIENT_SECRET"],
            "code": code, "redirect_uri": f"{base}/api/auth/github/callback"}).get("access_token")
        if not token:
            raise OAuthError("denied")
        me = _get_json("https://api.github.com/user", token)
    except OAuthError:
        raise
    except Exception:  # noqa: BLE001  upstream/network text is never surfaced
        raise OAuthError("github_unreachable") from None
    if not isinstance(me.get("id"), int) or not me.get("login"):
        raise OAuthError("bad_profile")
    return User(f"gh-{me['id']}", str(me["login"]), str(me.get("name") or ""), str(me.get("avatar_url") or ""))


# ---------------------------------------------------------------- workspace access
def can_access(ws: dict, user: User | None) -> bool:
    """Owner, or anyone for a shared demo (demo with no owner). Auth off: everything is reachable."""
    if not enabled():
        return True
    if user is None:
        return False
    owner = ws.get("owner") or ""
    return owner == user.id or (ws.get("demo", False) and not owner)


def is_shared(ws: dict) -> bool:
    return bool(ws.get("demo")) and not ws.get("owner")
