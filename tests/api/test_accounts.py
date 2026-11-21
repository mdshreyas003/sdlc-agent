"""Accounts, per-user isolation, user model settings, run history and sync logs (docs/accounts-and-settings-api.md)."""

import pytest
from fastapi.testclient import TestClient

from hackfront import auth, config, state
from hackfront.agent import llm
from hackfront.api import app

SECRET = "ZZ-user-key-9f8e7d6c5b4a"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(llm, "_clients", {})
    monkeypatch.setattr(llm, "_creds", {})
    for e in [e for e, _ in config.SECRETS.values()] + ["LLM_API_KEY", "LLM_BASE_URL", "HACKFRONT_AUTH"]:
        monkeypatch.delenv(e, raising=False)
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("HACKFRONT_SECRET_KEY", "test-signing-secret")


def signed_in(login: str, uid: str | None = None) -> TestClient:
    user = auth.upsert_user(auth.User(uid or f"gh-{abs(hash(login)) % 10**6}", login, login.title()))
    c = TestClient(app)
    c.cookies.set(auth.COOKIE, auth.make_session(user.id))
    return c


def test_enabled_requires_a_session_and_me_is_public():
    anon = TestClient(app)
    assert anon.get("/api/me").json() == {"auth": "enabled", "methods": ["github"], "user": None}
    assert anon.get("/api/workspaces").status_code == 401
    assert anon.get("/api/w/x/workbench").status_code == 401
    alice = signed_in("alice", "gh-1")
    me = alice.get("/api/me").json()
    assert me["auth"] == "enabled" and me["user"]["id"] == "gh-1" and me["user"]["login"] == "alice"
    assert alice.get("/api/workspaces").json() == []


def test_disabled_runs_as_local_user(monkeypatch):
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID")
    c = TestClient(app)
    assert c.get("/api/me").json()["auth"] == "disabled" and c.get("/api/me").json()["user"]["id"] == "local"
    assert c.get("/api/workspaces").status_code == 200


def test_required_without_oauth_never_falls_open(monkeypatch):
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID")
    monkeypatch.setenv("HACKFRONT_AUTH", "required")
    assert TestClient(app).get("/api/workspaces").status_code == 503


def test_session_cookie_is_tamper_and_expiry_proof():
    user = auth.upsert_user(auth.User("gh-7", "g"))
    good = auth.make_session(user.id)
    assert auth.read_session(good).id == "gh-7"
    uid, exp, sig = good.split(".")
    assert auth.read_session(f"gh-8.{exp}.{sig}") is None
    assert auth.read_session(f"{uid}.{int(exp) + 1}.{sig}") is None
    assert auth.read_session(auth.make_session(user.id, now=1)) is None  # long expired
    assert auth.read_session("junk") is None and auth.read_session(None) is None


def test_workspaces_are_separated_between_users():
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    slug = alice.post("/api/workspaces", json={"name": "Payments"}).json()["slug"]
    assert [w["slug"] for w in alice.get("/api/workspaces").json()] == [slug]
    assert alice.get("/api/workspaces").json()[0]["owned"] is True
    assert bob.get("/api/workspaces").json() == []
    for method, path in [("get", f"/api/w/{slug}/workbench"), ("get", f"/api/w/{slug}/sync"), ("get", f"/api/w/{slug}/runs"),
                         ("put", f"/api/w/{slug}/secrets"), ("post", f"/api/w/{slug}/sync"), ("delete", f"/api/workspaces/{slug}"),
                         ("get", f"/api/w/{slug}/investigations")]:
        r = getattr(bob, method)(path, **({"json": {"github_token": "x"}} if method == "put" else {}))
        assert r.status_code == 404 and r.json() == {"detail": "workspace not found"}, path
    assert bob.post("/api/workspaces", json={"name": "Payments"}).json()["slug"] != slug  # slugs never collide
    assert alice.get(f"/api/w/{slug}/workbench").status_code == 200
    assert bob.delete(f"/api/workspaces/{slug}").status_code == 404
    assert alice.delete(f"/api/workspaces/{slug}").json() == {"ok": True}


def test_shared_demo_is_visible_read_only_and_holds_no_keys():
    config.save_workspace("kafka", {**config.EMPTY_WORKSPACE, "name": "Apache Kafka", "demo": True,
                                    "github": {"owner": "apache", "repos": ["kafka"]}})
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    for c in (alice, bob):
        row = c.get("/api/workspaces").json()[0]
        assert row["slug"] == "kafka" and row["shared"] is True and row["owned"] is False
        assert c.get("/api/w/kafka/workbench").status_code == 200
        assert c.put("/api/w/kafka/secrets", json={"azure_key": SECRET}).status_code == 403
        assert c.delete("/api/workspaces/kafka").status_code == 403
        assert c.post("/api/w/kafka/sync").status_code == 403
    assert state.backend().read_secrets("kafka") == {}
    # a demo copy a user creates is theirs, private, and may hold its own model key
    copy = alice.post("/api/workspaces", json={"name": "Mine", "demo": True}).json()["slug"]
    assert bob.get(f"/api/w/{copy}/workbench").status_code == 404
    assert alice.put(f"/api/w/{copy}/secrets", json={"azure_key": SECRET}).status_code == 200


def test_shared_demo_investigations_are_per_author():
    config.save_workspace("kafka", {**config.EMPTY_WORKSPACE, "name": "Kafka", "demo": True})
    base = {"question": "q", "file": None, "line": None, "confidence": "high", "created_at": "2026-01-01T00:00:00Z"}
    store = state.backend()
    store.put_investigation("kafka", "seeded", {"investigation": {**base, "id": "seeded"}, "graph": {}})
    store.put_investigation("kafka", "a1", {"investigation": {**base, "id": "a1", "owner": "gh-1"}, "graph": {}})
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    assert {r["id"] for r in alice.get("/api/w/kafka/investigations").json()} == {"seeded", "a1"}
    assert {r["id"] for r in bob.get("/api/w/kafka/investigations").json()} == {"seeded"}
    assert alice.get("/api/w/kafka/investigations/a1").status_code == 200
    assert bob.get("/api/w/kafka/investigations/a1").status_code == 404
    assert bob.get("/api/w/kafka/investigations/seeded").status_code == 200


def test_user_models_are_private_write_only_and_validated():
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    r = alice.put("/api/me/models", json={"azure_endpoint": "https://acme.openai.azure.com", "azure_key": SECRET,
                                          "llm_provider": "azure", "llm_model": "gpt-4.1"})
    assert r.status_code == 200 and SECRET not in r.text
    body = alice.get("/api/me/models").json()
    azure = next(p for p in body["providers"] if p["name"] == "azure")
    assert azure["configured"] and azure["source"] == "user" and azure["editable"]
    key = next(f for f in azure["fields"] if f["key"] == "azure_key")
    assert key["set"] and key["hint"].startswith("••••") and "value" not in key
    assert body["default"] == {"provider": "azure", "model": "gpt-4.1", "source": "user"}
    assert body["selected"] == {"provider": "azure", "model": "gpt-4.1"}
    # bob sees none of it
    other = next(p for p in bob.get("/api/me/models").json()["providers"] if p["name"] == "azure")
    assert not other["configured"] and other["source"] is None
    # clearing, and validation (a key is only ever sent to an Azure host)
    assert alice.put("/api/me/models", json={"azure_key": ""}).status_code == 200
    assert not next(p for p in alice.get("/api/me/models").json()["providers"] if p["name"] == "azure")["configured"]
    assert alice.put("/api/me/models", json={"azure_endpoint": "https://evil.example.com"}).status_code == 422
    assert alice.put("/api/me/models", json={"azure_endpoint": "http://x.azure.com"}).status_code == 422
    assert alice.put("/api/me/models", json={"llm_provider": "nope"}).status_code == 422
    assert alice.put("/api/me/models", json={"github_token": "x"}).status_code == 422
    assert alice.put("/api/me/models", json={"llm_model": "bad model!"}).status_code == 422


def test_model_resolution_is_workspace_then_user_then_server(monkeypatch):
    config.save_workspace("w1", {**config.EMPTY_WORKSPACE, "name": "W", "owner": "gh-1"})
    monkeypatch.setenv("SARVAM_API_KEY", "server-key-0000000000")
    assert config.secret_source("w1", "sarvam_key", "gh-1") == "env"
    config.set_user_secrets("gh-1", {"sarvam_key": "user-key-1111111111"})
    assert config.secret_source("w1", "sarvam_key", "gh-1") == "user" and config.get_secret("w1", "sarvam_key", "gh-1").startswith("user-")
    assert config.secret_source("w1", "sarvam_key", "gh-2") == "env"  # another user never sees it
    config.set_secrets("w1", {"sarvam_key": "ws-key-2222222222"})
    assert config.secret_source("w1", "sarvam_key", "gh-1") == "workspace" and config.get_secret("w1", "sarvam_key", "gh-1").startswith("ws-")
    assert config.secret_source(None, "sarvam_key", "gh-1") == "user"
    alice = signed_in("alice", "gh-1")
    assert alice.get("/api/w/w1/workbench").json()["model"]["source"] == "workspace"
    config.set_secrets("w1", {"sarvam_key": ""})
    assert alice.get("/api/w/w1/workbench").json()["model"]["source"] == "user"


def test_oauth_login_and_callback(monkeypatch):
    c = TestClient(app, follow_redirects=False)
    r = c.get("/api/auth/github/login?next=/w/kafka")
    assert r.status_code == 302 and r.headers["location"].startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=cid" in r.headers["location"] and "csecret" not in r.headers["location"]
    nonce = r.cookies.get(auth.STATE_COOKIE)
    packed = r.headers["location"].split("state=")[1].split("&")[0]
    from urllib.parse import unquote

    monkeypatch.setattr(auth, "exchange_code", lambda code, base: auth.User("gh-42", "carol", "Carol", "http://a/v.png"))
    ok = c.get(f"/api/auth/github/callback?code=abc&state={packed}", cookies={auth.STATE_COOKIE: nonce})
    assert ok.status_code == 302 and ok.headers["location"] == "/w/kafka"
    assert auth.read_session(ok.cookies.get(auth.COOKIE)).login == "carol"
    assert "httponly" in ok.headers["set-cookie"].lower()
    assert c.get(f"/api/auth/github/callback?code=abc&state={unquote(packed)}").headers["location"] == "/login?error=state"  # no nonce cookie
    assert c.get("/api/auth/github/callback?code=abc&state=forged").headers["location"] == "/login?error=state"
    assert c.get(f"/api/auth/github/callback?state={packed}", cookies={auth.STATE_COOKIE: nonce}).headers["location"] == "/login?error=denied"
    assert auth.safe_next("//evil.com") == "/" and auth.safe_next("https://evil.com") == "/" and auth.safe_next("/w/x?a=1") == "/w/x?a=1"


def test_logout_clears_cookie():
    r = signed_in("alice", "gh-1").post("/api/auth/logout")
    assert r.json() == {"ok": True} and auth.COOKIE in r.headers["set-cookie"]


def test_runs_history_and_logs_are_owner_scoped():
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    slug = alice.post("/api/workspaces", json={"name": "Runs"}).json()["slug"]
    from hackfront.ingest import sync

    job = sync._Job(slug, "standard", triggered_by="gh-1")
    job.stream("github:acme/api")
    job.bump("github:acme/api", pages=1, fetched=3, persisted=3)
    job.finish("github:acme/api", True)
    job.end()
    runs = alice.get(f"/api/w/{slug}/runs").json()
    assert len(runs) == 1 and runs[0]["state"] == "done" and runs[0]["triggered_by"] == "gh-1" and "log" not in runs[0]
    run = alice.get(f"/api/w/{slug}/runs/{runs[0]['id']}").json()
    messages = [(line["level"], line["stream"] if "stream" in line else None) for line in run["log"]]
    assert ("info", None) in messages and ("info", "github:acme/api") in messages
    assert run["totals"] == {"fetched": 3, "persisted": 3, "errors": 0}
    assert alice.get(f"/api/w/{slug}/runs/nope").status_code == 404
    assert alice.get(f"/api/w/{slug}/runs/..%2F..").status_code in (404, 422)
    assert bob.get(f"/api/w/{slug}/runs").status_code == 404
    assert bob.get(f"/api/w/{slug}/runs/{runs[0]['id']}").status_code == 404
    status = alice.get(f"/api/w/{slug}/sync").json()
    assert status["id"] == run["id"] and status["log"]


def test_sync_log_is_capped_and_never_holds_secrets():
    from hackfront.ingest import sync

    config.save_workspace("w2", {**config.EMPTY_WORKSPACE, "name": "W2"})
    job = sync._Job("w2", "deep", persist=False)
    for i in range(sync.LOG_LIMIT + 50):
        job.log("info", f"line {i}")
    assert len(job.snapshot()["log"]) == sync.LOG_LIMIT
    job.fail("slack:C1", "Slack token not saved")
    assert any(line["level"] == "error" and line["stream"] == "slack:C1" for line in job.snapshot()["log"])


def test_ingestion_overview_without_graph(monkeypatch):
    monkeypatch.setattr(config, "neo4j_driver", lambda: (_ for _ in ()).throw(RuntimeError("bolt://u:secret@h")))
    alice, bob = signed_in("alice", "gh-1"), signed_in("bob", "gh-2")
    slug = alice.post("/api/workspaces", json={"name": "Ing"}).json()["slug"]
    r = alice.get(f"/api/w/{slug}/ingestion")
    assert r.status_code == 200 and "secret" not in r.text
    body = r.json()
    assert body["neo4j"] == {"ok": False} and body["graph"] is None and body["last_run"] is None
    assert [s["key"] for s in body["stages"]] == ["fetched", "stored", "linked", "indexed"]
    assert bob.get(f"/api/w/{slug}/ingestion").status_code == 404


# ---------------------------------------------------------------- email + password
PW = "correct horse battery"


@pytest.fixture
def pw(monkeypatch):
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID")
    monkeypatch.setenv("HACKFRONT_AUTH", "password")
    auth._attempts.clear()
    return TestClient(app)


def test_password_signup_login_and_session(pw):
    assert pw.get("/api/me").json() == {"auth": "enabled", "methods": ["password"], "user": None}
    r = pw.post("/api/auth/signup", json={"email": "Dev@Example.com", "password": PW, "name": "Dev"})
    assert r.status_code == 200 and r.json()["user"]["login"] == "dev@example.com" and auth.COOKIE in r.headers["set-cookie"]
    assert PW not in r.text and "password" not in r.json()["user"]
    assert pw.get("/api/me").json()["user"]["name"] == "Dev"  # the cookie from signup is a working session
    assert pw.get("/api/workspaces").status_code == 200
    doc = state.backend().read_user(auth.email_user_id("dev@example.com"))
    assert doc["password"].startswith("scrypt$") and PW not in str(doc)
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"email": "dev@example.com", "password": PW}).status_code == 200
    assert fresh.get("/api/me").json()["user"]["login"] == "dev@example.com"


def test_password_rules_and_generic_failures(pw):
    assert pw.post("/api/auth/signup", json={"email": "nope", "password": PW}).status_code == 422
    assert pw.post("/api/auth/signup", json={"email": "a@b.co", "password": "short"}).status_code == 422
    assert pw.post("/api/auth/signup", json={"email": "a@b.co"}).status_code == 422
    assert pw.post("/api/auth/signup", json={"email": "a@b.co", "password": PW}).status_code == 200
    assert TestClient(app).post("/api/auth/signup", json={"email": "A@B.co", "password": PW}).status_code == 409
    wrong = TestClient(app).post("/api/auth/login", json={"email": "a@b.co", "password": "wrong password!"})
    unknown = TestClient(app).post("/api/auth/login", json={"email": "ghost@b.co", "password": PW})
    assert wrong.status_code == unknown.status_code == 401 and wrong.json() == unknown.json()  # no account enumeration


def test_login_is_rate_limited(pw):
    pw.post("/api/auth/signup", json={"email": "r@b.co", "password": PW})
    other = TestClient(app)
    for _ in range(auth.MAX_FAILURES):
        assert other.post("/api/auth/login", json={"email": "r@b.co", "password": "bad password!"}).status_code == 401
    assert other.post("/api/auth/login", json={"email": "r@b.co", "password": PW}).status_code == 429  # even the right one
    assert auth.throttled("x|y", now=1.0) is False


def test_password_method_off_returns_503(monkeypatch):
    c = TestClient(app)  # only GitHub is configured by the fixture
    assert c.post("/api/auth/signup", json={"email": "a@b.co", "password": PW}).status_code == 503
    assert c.post("/api/auth/login", json={"email": "a@b.co", "password": PW}).status_code == 503


def test_first_account_claims_legacy_workspaces_once(pw):
    config.save_workspace("old", {**config.EMPTY_WORKSPACE, "name": "Old work"})  # predates accounts: no owner
    config.save_workspace("kafka", {**config.EMPTY_WORKSPACE, "name": "Kafka", "demo": True})
    first, second = TestClient(app), TestClient(app)
    r = first.post("/api/auth/signup", json={"email": "one@b.co", "password": PW})
    assert r.json()["claimed_workspaces"] is True
    assert config.load_workspace("old")["owner"] == auth.email_user_id("one@b.co")
    assert config.load_workspace("kafka")["owner"] == ""  # demos stay shared
    assert {w["slug"] for w in first.get("/api/workspaces").json()} == {"old", "kafka"}
    assert second.post("/api/auth/signup", json={"email": "two@b.co", "password": PW}).json()["claimed_workspaces"] is False
    assert {w["slug"] for w in second.get("/api/workspaces").json()} == {"kafka"}  # sees only the shared demo
    assert second.get("/api/w/old/workbench").status_code == 404


def test_github_signin_is_also_first_account(monkeypatch):
    config.save_workspace("old", {**config.EMPTY_WORKSPACE, "name": "Old"})
    user, claimed = auth.register(auth.User("gh-9", "nine"))
    assert claimed and config.load_workspace("old")["owner"] == "gh-9"
    assert auth.register(auth.User("gh-10", "ten"))[1] is False


def test_ingestion_plan_is_transparent_and_matches_targets(monkeypatch):
    monkeypatch.setattr(config, "neo4j_driver", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    alice = signed_in("alice", "gh-1")
    slug = alice.post("/api/workspaces", json={"name": "Plan"}).json()["slug"]
    ws = config.load_workspace(slug)
    config.save_workspace(slug, {**ws, "github": {"owner": "acme", "repos": ["api"]}, "slack": {**ws["slack"], "channels": ["C1"]}})
    plan = alice.get(f"/api/w/{slug}/ingestion").json()["plan"]
    assert plan["pages"] == {"standard": 20, "deep": 100} and plan["incremental"] is False and plan["idempotent"] is True
    assert [(s["source"], s["target"]) for s in plan["sources"]] == [("github", "acme/api"), ("slack", "C1")]
    commits = plan["sources"][0]["streams"][0]
    assert commits["stream"] == "commits" and commits["max"] == {"standard": 2000, "deep": 10000}
    assert plan["sources"][0]["streams"][2]["max"] == {"standard": None, "deep": None}  # runs once per pull request
    assert plan["sources"][1]["streams"][0]["max"] == {"standard": 300, "deep": 1500}
    body = alice.get(f"/api/w/{slug}/ingestion").json()
    assert body["timeline"] == [] and body["last_streams"] == []


def test_allowlists_gate_signup_login_and_github(pw, monkeypatch):
    monkeypatch.setenv("HACKFRONT_ALLOWED_EMAILS", "boss@corp.com, @team.io")
    assert pw.post("/api/auth/signup", json={"email": "rando@gmail.com", "password": PW}).status_code == 403
    assert pw.post("/api/auth/signup", json={"email": "Boss@Corp.com", "password": PW}).status_code == 200
    assert TestClient(app).post("/api/auth/signup", json={"email": "dev@team.io", "password": PW}).status_code == 200
    assert not auth.email_allowed("dev@evil-team.io") and auth.email_allowed("dev@team.io")
    monkeypatch.setenv("HACKFRONT_ALLOWED_EMAILS", "boss@corp.com")  # dev@team.io removed: locked out even with the right password
    assert TestClient(app).post("/api/auth/login", json={"email": "dev@team.io", "password": PW}).status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": "boss@corp.com", "password": PW}).status_code == 200
    monkeypatch.delenv("HACKFRONT_ALLOWED_EMAILS")
    assert auth.email_allowed("anyone@anywhere.com")
    monkeypatch.setenv("HACKFRONT_ALLOWED_GITHUB", "alice,Bob")
    assert auth.github_allowed("BOB") and not auth.github_allowed("mallory")


def test_github_callback_rejects_accounts_off_the_allowlist(monkeypatch):
    monkeypatch.setenv("HACKFRONT_ALLOWED_GITHUB", "alice")
    monkeypatch.setattr(auth, "exchange_code", lambda code, base: auth.User("gh-66", "mallory"))
    c = TestClient(app, follow_redirects=False)
    r = c.get("/api/auth/github/login")
    nonce, packed = r.cookies.get(auth.STATE_COOKIE), r.headers["location"].split("state=")[1].split("&")[0]
    ok = c.get(f"/api/auth/github/callback?code=abc&state={packed}", cookies={auth.STATE_COOKIE: nonce})
    assert ok.headers["location"] == "/login?error=not_allowed" and auth.COOKIE not in ok.headers.get("set-cookie", "")
    assert state.backend().read_user("gh-66") is None  # nothing was created
