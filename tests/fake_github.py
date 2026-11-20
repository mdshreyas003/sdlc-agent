"""An in-memory GitHub (REST, search and the GraphQL commit history) serving native payloads.

It paginates like GitHub (`Link: <...>; rel="next"`), at most `page_size` items per page whatever `per_page`
asks for, so every paginated endpoint is exercised across pages. Unknown paths are 404. Every request is
recorded in `calls`. `rate_limit_next(n)` answers the next n requests with GitHub's primary rate-limit 403.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from whycode.fixtures import FIXTURE_DIR
from whycode.history.github import HttpRequest, HttpResponse

API = "https://api.github.com"


def _json(status: int, payload, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, {"content-type": "application/json", **(headers or {})},
                        json.dumps(payload).encode())


class FakeGitHub:
    def __init__(self, repo: str = "cockroachdb/cockroach", page_size: int = 1, now: float = 1_700_000_000.0):
        self.repo = repo
        self.page_size = page_size
        self.now = now
        self.pulls: dict[int, dict] = {}
        self.issues: dict[int, dict] = {}
        self.calls: list[HttpRequest] = []
        self._rate_limited = 0

    @classmethod
    def from_fixture(cls, root: Path, **kwargs) -> FakeGitHub:
        fake = cls(**kwargs)
        for path in sorted((root / "pulls").glob("*.json")):
            fake.add_pull(json.loads(path.read_text()))
        for path in sorted((root / "issues").glob("*.json")):
            fake.add_issue(json.loads(path.read_text()))
        return fake

    def add_pull(self, bundle: dict) -> None:
        self.pulls[int(bundle["pull"]["number"])] = bundle

    def add_issue(self, bundle: dict) -> None:
        self.issues[int(bundle["issue"]["number"])] = bundle

    def rate_limit_next(self, n: int = 1) -> None:
        self._rate_limited = n

    # --- the transport interface ---------------------------------------------------------------

    def send(self, request: HttpRequest) -> HttpResponse:
        self.calls.append(request)
        if self._rate_limited:
            self._rate_limited -= 1
            return _json(403, {"message": "API rate limit exceeded"},
                         {"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(self.now) + 30)})
        url = urlsplit(request.url)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if request.method == "POST" and url.path == "/graphql":
            return self._graphql(json.loads(request.body))
        if url.path == "/search/issues":
            return self._search(request.url, query)
        prefix = f"/repos/{self.repo}/"
        if not url.path.startswith(prefix):
            return _json(404, {"message": "Not Found"})
        rest = url.path[len(prefix):]
        if m := re.fullmatch(r"pulls/(\d+)", rest):
            bundle = self.pulls.get(int(m.group(1)))
            return _json(200, bundle["pull"]) if bundle else _json(404, {"message": "Not Found"})
        if m := re.fullmatch(r"pulls/(\d+)/(files|commits|reviews|comments)", rest):
            bundle = self.pulls.get(int(m.group(1)))
            field = {"files": "files", "commits": "commits", "reviews": "reviews",
                     "comments": "review_comments"}[m.group(2)]
            return self._page(request.url, query, bundle.get(field) or []) if bundle else _json(404, {})
        if m := re.fullmatch(r"issues/(\d+)", rest):
            number = int(m.group(1))
            if number in self.issues:
                return _json(200, self.issues[number]["issue"])
            if number in self.pulls:  # the issues endpoint also serves pull requests, marked as such
                pull = self.pulls[number]["pull"]
                return _json(200, {**pull, "pull_request": {"url": f"{API}/repos/{self.repo}/pulls/{number}"}})
            return _json(404, {"message": "Not Found"})
        if m := re.fullmatch(r"issues/(\d+)/comments", rest):
            number = int(m.group(1))
            if number in self.issues:
                return self._page(request.url, query, self.issues[number].get("comments") or [])
            if number in self.pulls:
                return self._page(request.url, query, self.pulls[number].get("issue_comments") or [])
        return _json(404, {"message": "Not Found"})

    # --- endpoints -------------------------------------------------------------------------------

    def _page(self, url: str, query: dict[str, str], items: list) -> HttpResponse:
        size = min(int(query.get("per_page", 30)), self.page_size)
        page = int(query.get("page", 1))
        chunk = items[(page - 1) * size: page * size]
        headers = {}
        if page * size < len(items):
            parts = urlsplit(url)
            nxt = urlencode({**query, "page": page + 1})
            headers["link"] = f'<{parts.scheme}://{parts.netloc}{parts.path}?{nxt}>; rel="next"'
        return _json(200, chunk, headers)

    def _search(self, url: str, query: dict[str, str]) -> HttpResponse:
        labels: set[str] = set()
        start, end = "0000", "9999"
        for token in shlex.split(query["q"]):
            if token.startswith("label:"):
                labels |= set(token[len("label:"):].split(","))
            elif token.startswith("created:"):
                start, end = token[len("created:"):].split("..")
        hits = [
            b["issue"] for b in self.issues.values()
            if labels & {label["name"] for label in b["issue"].get("labels") or []}
            and start <= b["issue"]["created_at"][:10] <= end
        ]
        hits.sort(key=lambda issue: issue["created_at"], reverse=query.get("order") != "asc")
        response = self._page(url, query, hits)
        body = {"total_count": len(hits), "incomplete_results": False, "items": json.loads(response.body)}
        return HttpResponse(200, response.headers, json.dumps(body).encode())

    def _graphql(self, payload: dict) -> HttpResponse:
        variables = payload.get("variables") or {}
        if "history(" not in payload["query"]:
            return _json(200, {"errors": [{"message": "unsupported query"}]})
        path = variables["path"]
        nodes = []
        pulls = sorted(self.pulls.values(), key=lambda b: b["pull"].get("merged_at") or "", reverse=True)
        for bundle in pulls:
            if not any(f["filename"] == path or f["filename"].startswith(path + "/") for f in bundle["files"]):
                continue
            pull = bundle["pull"]
            associated = {"number": pull["number"], "baseRefName": pull["base"]["ref"],
                          "mergedAt": pull.get("merged_at")}
            for commit in bundle.get("commits") or [{"sha": f"{pull['number']:040d}"}]:
                nodes.append({"oid": commit["sha"], "associatedPullRequests": {"nodes": [associated]}})
        first = min(int(variables.get("first", 100)), self.page_size)
        start = int(variables.get("after") or 0)
        chunk = nodes[start: start + first]
        has_next = start + first < len(nodes)
        history = {"totalCount": len(nodes), "nodes": chunk,
                   "pageInfo": {"hasNextPage": has_next, "endCursor": str(start + first) if has_next else None}}
        return _json(200, {"data": {"repository": {"object": {"history": history}}}})


# --- the miniature history as GitHub would serve it ---------------------------------------------------


def miniature_checkout(root: Path) -> Path:
    """The miniature's Go code and RFC files laid out as in a CockroachDB checkout."""
    shutil.copytree(FIXTURE_DIR / "code", root)
    (root / "docs/RFCS").mkdir(parents=True)
    for rfc in (FIXTURE_DIR / "rfcs").glob("*.md"):
        shutil.copy(rfc, root / "docs/RFCS" / rfc.name)
    return root


def user(login):
    return {"login": login}


def pull(number, title, merged_at, files, base="master", login="someone"):
    return {
        "pull": {"number": number, "title": title, "body": "", "user": user(login),
                 "html_url": f"https://github.com/cockroachdb/cockroach/pull/{number}",
                 "created_at": merged_at, "merged_at": merged_at, "base": {"ref": base}, "labels": []},
        "files": [{"filename": f, "status": "modified", "patch": "@@ -1 +1 @@\n-a\n+b"} for f in files],
        "commits": [{"sha": f"{number:x}".rjust(40, "a"), "author": user(login),
                     "commit": {"message": title, "author": {"date": merged_at}}}],
        "reviews": [], "review_comments": [], "issue_comments": [],
    }


def miniature_github() -> FakeGitHub:
    """The miniature history, plus records the slice must leave out (and the RFC pull requests)."""
    fake = FakeGitHub.from_fixture(FIXTURE_DIR, page_size=1)
    # RFC PRs: they name the RFCs' authors, but touch no scoped code.
    fake.add_pull(pull(2842, "RFC: online schema change", "2015-10-20T00:00:00Z",
                       ["docs/RFCS/20151014_online_schema_change.md"], login="vivekmenezes"))
    fake.add_pull(pull(59288, "RFC: declarative schema changer", "2021-03-01T00:00:00Z",
                       ["docs/RFCS/20210115_new_schema_changer.md"], login="ajwerner"))
    # A backport into a release branch and a pull request outside the scoped code.
    fake.add_pull(pull(98200, "release-23.1: sql: add exponential backoff to schema change job retries",
                       "2023-03-25T00:00:00Z", ["pkg/sql/schema_changer.go"], base="release-23.1"))
    fake.add_pull(pull(99000, "kv: unrelated", "2023-04-01T00:00:00Z", ["pkg/kv/kv.go"]))
    # #98100 says "Informs #97000"; 97000 is a pull request outside the scope, not an issue.
    fake.add_pull(pull(97000, "kv: something #98100 mentions", "2023-02-01T00:00:00Z", ["pkg/kv/kv.go"]))
    # An A-schema issue nothing links to.
    fake.add_issue({"issue": {
        "number": 99500, "title": "schema: ALTER TABLE is slow on wide tables", "body": "Repro inside.",
        "user": user("annrpom"), "html_url": "https://github.com/cockroachdb/cockroach/issues/99500",
        "created_at": "2023-02-01T00:00:00Z", "closed_at": None, "labels": [{"name": "A-schema-descriptors"}],
    }, "comments": []})
    return fake
