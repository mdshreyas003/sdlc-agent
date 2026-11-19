"""GitHub REST payloads -> history records.

The fixture source stores recorded REST payload bundles; a cached REST client (ticket 02) can hand the same
bundles to these functions. Bundle shapes (field names as GitHub returns them):

- pull request: {"pull": GET /pulls/{n}, "files": GET /pulls/{n}/files, "commits": GET /pulls/{n}/commits,
  "reviews": GET /pulls/{n}/reviews, "review_comments": GET /pulls/{n}/comments,
  "issue_comments": GET /issues/{n}/comments}
- issue: {"issue": GET /issues/{n}, "comments": GET /issues/{n}/comments}
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from whycode.history.records import Commit, FileChange, Issue, Post, PullRequest

BOT_LOGINS = frozenset({"cockroach-teamcity", "github-actions"})  # plus any login ending in "[bot]"


def is_bot(login: str | None) -> bool:
    return not login or login.endswith("[bot]") or login in BOT_LOGINS


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp without an offset: {value!r}")
    return parsed.astimezone(dt.UTC)


def _login(obj: dict[str, Any] | None) -> str | None:
    return (obj or {}).get("login")


def _post(kind, item: dict[str, Any], at_field: str) -> Post | None:
    author = _login(item.get("user"))
    at = parse_time(item.get(at_field))
    if is_bot(author) or at is None:
        return None
    return Post(kind=kind, author=author, at=at, body=item.get("body") or "",
                review_state=item.get("state") if kind == "review" else None, path=item.get("path"))


def pull_request_from_rest(bundle: dict[str, Any]) -> PullRequest:
    pull = bundle["pull"]
    posts = [
        *(_post("review", r, "submitted_at") for r in bundle.get("reviews") or []),
        *(_post("review_comment", c, "created_at") for c in bundle.get("review_comments") or []),
        *(_post("comment", c, "created_at") for c in bundle.get("issue_comments") or []),
    ]
    return PullRequest(
        number=int(pull["number"]),
        title=pull.get("title") or "",
        body=pull.get("body") or "",
        author=_login(pull.get("user")) or "",
        url=pull["html_url"],
        created_at=parse_time(pull["created_at"]),
        merged_at=parse_time(pull.get("merged_at")),
        base_ref=(pull.get("base") or {}).get("ref", ""),
        labels=tuple(label["name"] for label in pull.get("labels") or []),
        files=tuple(
            FileChange(path=f["filename"], status=f.get("status", "modified"), patch=f.get("patch"),
                       previous_path=f.get("previous_filename"))
            for f in bundle.get("files") or []
        ),
        commits=tuple(
            Commit(sha=c["sha"], message=c["commit"]["message"], author=_login(c.get("author")),
                   at=parse_time((c["commit"].get("author") or {}).get("date")))
            for c in bundle.get("commits") or []
        ),
        posts=tuple(sorted((p for p in posts if p is not None), key=lambda p: p.at)),
    )


def issue_from_rest(bundle: dict[str, Any]) -> Issue:
    issue = bundle["issue"]
    posts = (_post("comment", c, "created_at") for c in bundle.get("comments") or [])
    return Issue(
        number=int(issue["number"]),
        title=issue.get("title") or "",
        body=issue.get("body") or "",
        author=_login(issue.get("user")) or "",
        url=issue["html_url"],
        created_at=parse_time(issue["created_at"]),
        closed_at=parse_time(issue.get("closed_at")),
        labels=tuple(label["name"] for label in issue.get("labels") or []),
        posts=tuple(sorted((p for p in posts if p is not None), key=lambda p: p.at)),
    )
