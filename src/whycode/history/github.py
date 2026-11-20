"""GitHub history source: the scoped slice (`history.scope`) fetched from GitHub through an on-disk cache.

Three layers, each replaceable in tests ("same client, fake transport"):

- `Transport`: one HTTP request in, one response out. `UrllibTransport` talks to GitHub.
- `CachedTransport`: stores every successful (or 404) response on disk, keyed by method, URL and body (never
  by headers, so the token is not part of any key or file). A cached request never reaches the network,
  which makes the backfill resumable (re-run it after a stop) and a re-run free of GitHub calls. With no
  inner transport it is offline: a cache miss raises `CacheMiss`.
- `GitHubClient`: REST and GraphQL calls with `Link` pagination; waits out rate limits (`x-ratelimit-reset`,
  `retry-after`) and retries server errors. The token only ever goes into the Authorization header.

`GitHubHistorySource` decides what to fetch and maps the REST payloads to records through `github_rest`:

- pull requests: the commit history of each scoped path at `Scope.pr_history_commit` (the cutoff commit, or the
  window's last commit for a Held-out Window build; GraphQL, 100 commits per call) gives the pull requests that
  merged those commits; kept when merged into `base_ref` by the cutoff and
  their files touch a scoped path. Each one costs a detail call plus paginated files, commits, reviews,
  review comments and conversation comments;
- issues: the scope's labels through the search API (sliced by creation date to stay under its 1000-result
  cap), plus the issues the ingested pull requests and RFCs link to, one hop;
- RFCs: read from the checkout; their authors are the logins of their `RFC PR`.

`limit` bounds a run: the `limit` most recently merged pull requests, the `limit` most recent labelled issues
and at most `limit` linked issues (RFCs are always all read). `load_history` still applies the cutoff to
everything the source yields.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from whycode.history.github_rest import is_bot, issue_from_rest, parse_time, pull_request_from_rest
from whycode.history.records import History, Issue, PullRequest, Rfc
from whycode.history.rfc import parse_header
from whycode.history.scope import Scope

log = logging.getLogger(__name__)

API = "https://api.github.com"
SEARCH_CAP = 1000  # GitHub search returns at most this many results per query
FIRST_YEAR = 2014  # cockroachdb/cockroach was created in 2014


# --- HTTP ------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]  # lower-case names
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body or b"null")


class Transport(Protocol):
    def send(self, request: HttpRequest) -> HttpResponse: ...


class TransportError(RuntimeError):
    """The request never got an HTTP response (network down, timeout)."""


class GitHubError(RuntimeError):
    pass


class CacheMiss(GitHubError):
    """Offline, and the request is not in the cache."""


class UrllibTransport:
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def send(self, request: HttpRequest) -> HttpResponse:
        req = urllib.request.Request(request.url, data=request.body, headers=request.headers, method=request.method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return HttpResponse(response.status, {k.lower(): v for k, v in response.headers.items()},
                                    response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read())
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise TransportError(str(exc)) from exc


_KEPT_HEADERS = ("link", "content-type")


class CachedTransport:
    def __init__(self, inner: Transport | None, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.network_calls = 0
        self.cache_hits = 0

    def _path(self, request: HttpRequest) -> Path:
        key = hashlib.sha256(b"\0".join([request.method.encode(), request.url.encode(), request.body or b""]))
        digest = key.hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def send(self, request: HttpRequest) -> HttpResponse:
        path = self._path(request)
        if path.exists():
            self.cache_hits += 1
            entry = json.loads(path.read_text(encoding="utf-8"))
            return HttpResponse(entry["status"], entry["headers"], entry["body"].encode("utf-8"))
        if self.inner is None:
            raise CacheMiss(f"offline and not cached: {request.method} {request.url}")
        self.network_calls += 1
        response = self.inner.send(request)
        if _cacheable(request, response):
            entry = {
                "method": request.method, "url": request.url,
                "request_body": request.body.decode("utf-8") if request.body else None,
                "status": response.status,
                "headers": {k: v for k, v in response.headers.items() if k in _KEPT_HEADERS},
                "body": response.body.decode("utf-8"),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(entry), encoding="utf-8")
            tmp.replace(path)  # atomic: a stopped run never leaves a half-written entry
        return response


def _cacheable(request: HttpRequest, response: HttpResponse) -> bool:
    if response.status not in (200, 404, 410):
        return False
    if urlsplit(request.url).path == "/graphql":  # GraphQL reports failures (timeouts too) as 200 + errors
        try:
            return "errors" not in response.json()
        except ValueError:
            return False
    return True


# --- client ----------------------------------------------------------------------------------------

_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="?next"?')


class GitHubClient:
    def __init__(self, transport: Transport, token: str | None = None, api: str = API,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time,
                 max_retries: int = 8):
        self.transport = transport
        self.token = token
        self.api = api.rstrip("/")
        self.sleep = sleep
        self.clock = clock
        self.max_retries = max_retries

    def _url(self, path: str, params: dict[str, Any]) -> str:
        query = urlencode(sorted((k, str(v)) for k, v in params.items()))
        return f"{self.api}{path}" + (f"?{query}" if query else "")

    def _send(self, method: str, url: str, body: bytes | None = None) -> HttpResponse:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "whycode-ingest"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        status = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.transport.send(HttpRequest(method, url, headers, body))
            except TransportError as exc:
                status = str(exc)
                self._wait(min(2 ** attempt, 60), f"network error ({exc})")
                continue
            status = response.status
            if response.status in (403, 429) and (wait := self._rate_limit_wait(response)) is not None:
                self._wait(wait, f"GitHub rate limit ({response.status})")
                continue
            if response.status >= 500:
                self._wait(min(2 ** attempt, 60), f"GitHub server error {response.status}")
                continue
            return response
        raise GitHubError(f"{method} {urlsplit(url).path} failed after {self.max_retries} retries: {status}")

    def _wait(self, seconds: float, why: str) -> None:
        log.warning("%s: waiting %.0fs", why, seconds)
        self.sleep(seconds)

    def _rate_limit_wait(self, response: HttpResponse) -> float | None:
        headers = response.headers
        if headers.get("retry-after", "").isdigit():
            return float(headers["retry-after"])
        if headers.get("x-ratelimit-remaining") == "0" and headers.get("x-ratelimit-reset", "").isdigit():
            return max(1.0, float(headers["x-ratelimit-reset"]) - self.clock() + 1)
        if b"secondary rate limit" in response.body.lower():
            return 60.0
        return None

    def _check(self, response: HttpResponse, url: str) -> Any:
        if response.status in (404, 410):
            return None
        if not 200 <= response.status < 300:
            raise GitHubError(f"GET {urlsplit(url).path} returned {response.status}")
        return response.json()

    def get(self, path: str, **params: Any) -> Any:
        """The decoded JSON of a resource, or None when GitHub says it does not exist (404, 410)."""
        url = self._url(path, params)
        return self._check(self._send("GET", url), url)

    def pages(self, path: str, items: str | None = None, **params: Any) -> Iterator[Any]:
        """Every item of a paginated endpoint, following `Link: rel="next"` (`items`: the list's key, for
        endpoints that wrap their list in an object, like search)."""
        url: str | None = self._url(path, {"per_page": 100, **params})
        seen: set[str] = set()
        while url:
            if url in seen or not url.startswith(self.api + "/"):
                raise GitHubError(f"refusing pagination link {urlsplit(url).path}")
            seen.add(url)
            response = self._send("GET", url)
            payload = self._check(response, url)
            if payload is None:
                return
            yield from (payload[items] if items else payload)
            match = next((m for part in response.headers.get("link", "").split(",") if (m := _NEXT.search(part))),
                         None)
            url = match.group(1) if match else None

    def graphql(self, query: str, variables: dict[str, Any]) -> Any:
        body = json.dumps({"query": query, "variables": variables}, sort_keys=True).encode()
        url = f"{self.api}/graphql"
        response = self._send("POST", url, body)
        payload = self._check(response, url)
        if not payload or payload.get("errors"):
            raise GitHubError(f"GraphQL query failed: {(payload or {}).get('errors')}")
        return payload["data"]


# --- the history source ----------------------------------------------------------------------------

HISTORY_QUERY = """
query($owner: String!, $name: String!, $commit: String!, $path: String!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    object(expression: $commit) {
      ... on Commit {
        history(path: $path, first: $first, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            oid parents { totalCount }
            associatedPullRequests(first: 5) { nodes { number baseRefName mergedAt } }
          }
        }
      }
    }
  }
}"""

_PULL_URL = re.compile(r"/pull/(\d+)")
_NUMBER = re.compile(r"#?(?<![\w/])(\d{3,7})\b")


@dataclass(frozen=True, slots=True)
class _Records:
    """A source over records already in hand (to find links in what was fetched so far)."""

    repo: str
    rfc_list: tuple[Rfc, ...]
    pull_list: tuple[PullRequest, ...]

    def rfcs(self):
        return self.rfc_list

    def pull_requests(self):
        return self.pull_list

    def issues(self):
        return ()


class GitHubHistorySource:
    def __init__(self, client: GitHubClient, scope: Scope, checkout: Path, cutoff: dt.date,
                 limit: int | None = None):
        self.client = client
        self.scope = scope
        self.repo = scope.repo
        self.checkout = Path(checkout)
        self.cutoff = cutoff
        self.limit = limit
        self._end = dt.datetime.combine(cutoff + dt.timedelta(days=1), dt.time(), tzinfo=dt.UTC)
        self._rfcs: tuple[Rfc, ...] | None = None
        self._pulls: tuple[PullRequest, ...] | None = None
        self._issues: tuple[Issue, ...] | None = None

    # HistorySource

    def rfcs(self) -> tuple[Rfc, ...]:
        if self._rfcs is None:
            self._rfcs = tuple(self._read_rfcs())
        return self._rfcs

    def pull_requests(self) -> tuple[PullRequest, ...]:
        if self._pulls is None:
            self._pulls = tuple(self._fetch_pulls())
        return self._pulls

    def issues(self) -> tuple[Issue, ...]:
        if self._issues is None:
            self._issues = tuple(self._fetch_issues())
        return self._issues

    # RFCs

    def _read_rfcs(self) -> Iterator[Rfc]:
        for stem in self.scope.rfc_stems:
            rel = f"{self.scope.rfc_dir}/{stem}.md"
            path = self.checkout / rel
            if not path.exists():
                log.warning("RFC %s is not in the checkout", rel)
                continue
            text = path.read_text(encoding="utf-8")
            date = dt.datetime.strptime(stem[:8], "%Y%m%d").date()
            yield Rfc(path=rel, text=text, date=date,
                      authors=self._rfc_authors(text) if date <= self.cutoff else (),
                      url=f"https://github.com/{self.repo}/blob/{self.scope.cutoff_commit}/{rel}")

    def _rfc_authors(self, text: str) -> tuple[str, ...]:
        """The login of the RFC's pull request author (RFC headers name people, not logins)."""
        field_ = parse_header(text).get("RFC PR")
        if field_ is None:
            return ()
        m = _PULL_URL.search(field_.value) or _NUMBER.search(field_.value)
        if m is None:
            return ()
        pull = self.client.get(f"/repos/{self.repo}/pulls/{int(m.group(1))}")
        login = ((pull or {}).get("user") or {}).get("login")
        return () if is_bot(login) else (login,)

    # pull requests

    def _merged_in_scope(self, merged_at: str | None, base: str | None) -> bool:
        at = parse_time(merged_at)
        return at is not None and at < self._end and base == self.scope.base_ref

    def pull_request_numbers(self) -> list[int]:
        """Pull requests that merged commits touching the scoped paths, most recently merged first."""
        owner, name = self.repo.split("/")
        merged: dict[int, str] = {}
        for path in self.scope.pr_paths:
            found: set[int] = set()
            after = None
            while True:
                data = self.client.graphql(HISTORY_QUERY, {
                    "owner": owner, "name": name, "commit": self.scope.pr_history_commit, "path": path,
                    "first": 100, "after": after,
                })
                history = ((data.get("repository") or {}).get("object") or {}).get("history")
                if history is None:
                    raise GitHubError(f"no commit history for {path} at {self.scope.pr_history_commit}")
                for node in history["nodes"]:
                    # A bors merge commit batches several pull requests but is associated with only one of
                    # them, not necessarily one that touched the path; the pull requests' own commits are.
                    if (node.get("parents") or {}).get("totalCount", 1) > 1:
                        continue
                    for pr in node["associatedPullRequests"]["nodes"]:
                        if self._merged_in_scope(pr.get("mergedAt"), pr.get("baseRefName")):
                            merged[pr["number"]] = pr["mergedAt"]
                            found.add(pr["number"])
                page = history["pageInfo"]
                if not page["hasNextPage"] or (self.limit and len(found) >= self.limit):
                    break
                after = page["endCursor"]
            log.info("%s: %d pull requests", path, len(found))
        ordered = sorted(merged, key=lambda n: (merged[n], n), reverse=True)
        return ordered[: self.limit] if self.limit else ordered

    def _touches_scope(self, pr: PullRequest) -> bool:
        def scoped(path: str | None) -> bool:
            return bool(path) and any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.scope.pr_paths)

        return any(scoped(f.path) or scoped(f.previous_path) for f in pr.files)

    def _fetch_pulls(self) -> Iterator[PullRequest]:
        numbers = self.pull_request_numbers()
        for i, number in enumerate(numbers, 1):
            bundle = self._pull_bundle(number)
            if bundle is not None:
                pr = pull_request_from_rest(bundle)
                if self._touches_scope(pr):
                    yield pr
            if i % 25 == 0 or i == len(numbers):
                log.info("pull requests: %d/%d", i, len(numbers))

    def _pull_bundle(self, number: int) -> dict[str, Any] | None:
        base = f"/repos/{self.repo}/pulls/{number}"
        pull = self.client.get(base)
        if pull is None or not self._merged_in_scope(pull.get("merged_at"), (pull.get("base") or {}).get("ref")):
            return None
        return {
            "pull": pull,
            "files": list(self.client.pages(f"{base}/files")),
            "commits": list(self.client.pages(f"{base}/commits")),
            "reviews": list(self.client.pages(f"{base}/reviews")),
            "review_comments": list(self.client.pages(f"{base}/comments")),
            "issue_comments": list(self.client.pages(f"/repos/{self.repo}/issues/{number}/comments")),
        }

    # issues

    def _fetch_issues(self) -> Iterator[Issue]:
        labelled = self._labelled_issue_payloads()
        numbers = {int(item["number"]) for item in labelled}
        for i, item in enumerate(labelled, 1):
            yield self._issue(item)
            if i % 50 == 0 or i == len(labelled):
                log.info("labelled issues: %d/%d", i, len(labelled))
        linked = [n for n in self._linked_issue_numbers() if n not in numbers]
        count = 0
        for number in linked:
            if self.limit and count >= self.limit:
                break
            item = self.client.get(f"/repos/{self.repo}/issues/{number}")
            if item is None or "pull_request" in item or not self._own(item) or not self._before_end(item):
                continue
            count += 1
            yield self._issue(item)
        log.info("linked issues: %d (of %d linked numbers)", count, len(linked))

    def _own(self, item: dict[str, Any]) -> bool:
        """Not an issue that was transferred to another repository (GitHub redirects to it)."""
        repository = item.get("repository_url")
        return repository is None or repository.endswith(f"/repos/{self.repo}")

    def _before_end(self, item: dict[str, Any]) -> bool:
        created = parse_time(item.get("created_at"))
        return created is not None and created < self._end

    def _issue(self, item: dict[str, Any]) -> Issue:
        comments = list(self.client.pages(f"/repos/{self.repo}/issues/{int(item['number'])}/comments"))
        return issue_from_rest({"issue": item, "comments": comments})

    def _labelled_issue_payloads(self) -> list[dict[str, Any]]:
        """Issues with a scope label created by the cutoff, most recent first."""
        found: dict[int, dict[str, Any]] = {}
        for year in range(self.cutoff.year, FIRST_YEAR - 1, -1):
            start, end = dt.date(year, 1, 1), min(dt.date(year, 12, 31), self.cutoff)
            for item in self._search(start, end):
                if "pull_request" in item or not self._before_end(item):
                    continue
                found.setdefault(int(item["number"]), item)
                if self.limit and len(found) >= self.limit:
                    return list(found.values())
        return list(found.values())

    def _search(self, start: dt.date, end: dt.date) -> Iterator[dict[str, Any]]:
        query = (f"repo:{self.repo} is:issue label:{','.join(self.scope.issue_labels)} "
                 f"created:{start.isoformat()}..{end.isoformat()}")
        params = {"q": query, "sort": "created", "order": "desc"}
        first = self.client.get("/search/issues", per_page=100, **params) or {}
        if first.get("total_count", 0) > SEARCH_CAP and start < end:
            middle = start + (end - start) // 2
            yield from self._search(middle + dt.timedelta(days=1), end)
            yield from self._search(start, middle)
            return
        if first.get("total_count", 0):
            yield from self.client.pages("/search/issues", items="items", **params)

    def _linked_issue_numbers(self) -> list[int]:
        """Issue numbers that the ingested pull requests and RFCs link to (as of the cutoff), newest first."""
        from whycode.history import load_history
        from whycode.linker import stated_links

        history: History = load_history(_Records(self.repo, self.rfcs(), self.pull_requests()), self.cutoff)
        numbers = {int(m.group(1)) for link in stated_links(history)
                   if (m := re.fullmatch(r"issue:(\d+)", link.target))}
        return sorted(numbers, reverse=True)
