"""An in-memory GitHub (REST, search and the GraphQL commit history) serving native payloads.

It paginates like GitHub (`Link: <...>; rel="next"`), at most `page_size` items per page whatever `per_page`
asks for, so every paginated endpoint is exercised across pages. Unknown paths are 404. Every request is
recorded in `calls`. `rate_limit_next(n)` answers the next n requests with GitHub's primary rate-limit 403.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

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
