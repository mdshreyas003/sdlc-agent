# Accounts, user settings, runs and logs (API contract v3)

Extends `docs/workbench-api.md`. Everything there still holds unless stated here. Errors stay `{"detail": "<safe message>"}`.

## Identity

- **GitHub OAuth only.** Enabled when `GITHUB_OAUTH_CLIENT_ID` and `GITHUB_OAUTH_CLIENT_SECRET` are set (and `HACKFRONT_SECRET_KEY`
  signs the session). `HACKFRONT_PUBLIC_URL` is the browser-facing origin (the Next.js app); the OAuth callback is
  `<HACKFRONT_PUBLIC_URL>/api/auth/github/callback`. `HACKFRONT_AUTH=off` forces auth off, `=required` makes a missing
  OAuth config a 503 instead of silently open.
- **Auth disabled (local default):** every request runs as the implicit user `local` and nothing is enforced, so existing
  local runs and tests keep working. `GET /api/me` reports `auth: "disabled"`.
- Session: cookie `hf_session` (HttpOnly, SameSite=Lax, Secure on https), HMAC-signed `<uid>.<expires>.<sig>`, 30 days.
  The Next proxy must forward `Cookie` upstream and `Set-Cookie` + `Location` back, and must **not follow redirects**.
- User id is `gh-<github numeric id>`.

```ts
Me { auth: "enabled" | "disabled", user: { id: string, login: string, name: string, avatar_url: string } | null }
```

| Method + path | Notes |
|---|---|
| `GET /api/me` | Public. `user` is null when auth is enabled and nobody is signed in. |
| `GET /api/auth/github/login?next=/path` | 302 to GitHub. `next` must be a same-site relative path (else `/`). 503 `{"detail":...}` when OAuth is not configured. |
| `GET /api/auth/github/callback` | 302 to `next`, sets `hf_session`. On failure 302 to `/login?error=<code>`. |
| `POST /api/auth/logout` | `{ok:true}`, clears the cookie. |
| every other `/api/*` (except `/health`) | **401** `{"detail":"sign in required"}` when auth is enabled and there is no valid session. |

## Email + password

Enabled with `HACKFRONT_AUTH=password` (needs `HACKFRONT_SECRET_KEY`); can run next to GitHub. `GET /api/me` gains
`methods: ("github"|"password")[]`. Passwords are hashed with scrypt; there is **no self-service reset**: the operator runs
`hackfront set-password <email>` (creates the account if missing).

| Method + path | Body | Response |
|---|---|---|
| `POST /api/auth/signup` | `{email, password (10-200 chars), name?}` | `{ok, user, claimed_workspaces:boolean}` + `hf_session`. 422 safe message, 409 `An account with this email already exists`. |
| `POST /api/auth/login` | `{email, password}` | `{ok, user}` + `hf_session`. 401 `Incorrect email or password` (same for unknown emails), 429 after 5 failures per IP+email in 10 minutes. |
| both | | 503 `Email sign-in is not enabled on this server` when the method is off. |

**Allowlists (public deployments):** `HACKFRONT_ALLOWED_EMAILS` (emails or `@domain`) gates email signup **and** login (403
`Sign-ups are limited...` on signup); `HACKFRONT_ALLOWED_GITHUB` (logins) gates GitHub sign-in (`/login?error=not_allowed`).
Unset means open. The failed-login limiter is in memory, so on serverless hosts it is per instance, not global.

**First account claims history:** the first account ever created (email or GitHub) takes ownership of every workspace that
predates accounts (no owner, not a demo), once. Demos stay shared. Later moves: `hackfront assign-owner <workspace> <user id>`.

## Isolation

- `workspace.json` gets `owner` (user id, `""` = nobody). Created workspaces are owned by the creator.
- `GET /api/workspaces` returns only the caller's workspaces plus **shared demo** workspaces (`demo:true`, no owner).
  Row gains `owned: boolean` and `shared: boolean` (`shared` = visible to everyone, read-only).
- Any `/api/w/{ws}/...` and `DELETE /api/workspaces/{ws}` for a workspace the caller neither owns nor sees as shared
  demo returns **404 `workspace not found`** (never 403, so existence is not revealed).
- A shared demo is read-only: targets, sync, rename, delete and **all secret writes** are refused (403
  `Demo workspace setup is locked`) when auth is enabled. Its AI model comes from the **caller's** user models.
- Stored investigations on a shared demo carry `owner`; list/get on a shared workspace return only the caller's plus
  ownerless (seeded) ones.
- Legacy workspaces with no owner and `demo:false` belong to the implicit `local` user (visible only with auth off).

## User models (Settings → Models)

Resolution order for every model setting: **workspace override** → **user setting** → **server environment**.
The generic `openai` provider (`LLM_API_KEY`, `LLM_BASE_URL`) stays server-only so a user cannot point the server at an
arbitrary host.

```ts
ModelField { key: "azure_endpoint"|"azure_key"|"sarvam_key", label: string, secret: boolean, set: boolean,
             hint?: string /*masked*/, value?: string /*non-secret only*/ }
ModelProvider { name: "azure"|"sarvam"|"openai", label: string, model: string, configured: boolean,
                source: "user" | "server" | null,        // where its credentials come from
                editable: boolean,                       // false for the server-only generic provider
                fields: ModelField[] }
UserModels { providers: ModelProvider[],
             default: { provider: string, model: string, source: "user" | "server" },
             selected: { provider: string, model: string } }   // user's own llm_provider / llm_model ("" when unset)
```

| Method + path | Body | Response |
|---|---|---|
| `GET /api/me/models` | | `UserModels` |
| `PUT /api/me/models` | any subset of `azure_endpoint azure_key sarvam_key llm_provider llm_model`; `""` clears | `UserModels`. Values are write-only for secret keys. 422 safe message. |
| `POST /api/me/models/{azure\|sarvam\|openai}/test` | | `{ok, detail, account?}` (one tiny completion with the resolved credentials). 200 even when `ok=false`. |

The workspace-level override keeps using `PUT /api/w/{ws}/secrets` with the same five keys.
`GET /api/w/{ws}/workbench` gains `model: { provider, model, source: "workspace" | "user" | "server" }` (what the
workspace actually resolves to) alongside the existing `providers`.

## Runs and logs (Sync history)

A *sync run* is one fetch of the connected sources. Every run is persisted with a structured log.

```ts
LogLine { ts: string /*ISO UTC*/, level: "info"|"warn"|"error", stream?: string, message: string }
RunMeta { id: string, state: "running"|"done"|"failed", mode: "standard"|"deep", started_at: string,
          finished_at?: string, complete: boolean, totals: {fetched, persisted, errors}, triggered_by?: string }
Run     = RunMeta & { streams: SyncStream[], graph?: {artifacts, edges, stubs}, error?: string, log: LogLine[] }
```

| Method + path | Response |
|---|---|
| `GET /api/w/{ws}/runs` | `RunMeta[]`, newest first (max 50) |
| `GET /api/w/{ws}/runs/{id}` | `Run` (404 `run not found`) |
| `GET /api/w/{ws}/sync` | as before plus `id` and `log` (last 200 lines) while/after running |
| `POST /api/w/{ws}/sync` | as before; the run is recorded in history when it ends |

Log messages are fixed safe strings: no tokens, URLs with credentials, or exception text.

## Ingestion (what is in the graph)

Sync fetches; **ingestion** is what the fetched records became: mapped, linked, stored.

| Method + path | Response |
|---|---|
| `GET /api/w/{ws}/ingestion` | `{ neo4j:{ok}, graph:{artifacts, edges, stubs}\|null, by_source:[{source, kind, count}], repos:[{repo, indexed}], last_run: RunMeta\|null, stages:[{key:"fetched"\|"stored"\|"linked"\|"indexed", label, count, status:"ok"\|"warn"\|"idle"}] }` |

## Web routes

`/login` · `/settings` (Profile · Models · Appearance) · `/workspaces` (list, create, manage) ·
`/w/[ws]/settings` (General · Sources · Model override · Danger) · `/w/[ws]/sync` (sources, run, history, logs) ·
`/w/[ws]/ingestion` (stages, graph health, coverage) · existing workbench routes unchanged.
