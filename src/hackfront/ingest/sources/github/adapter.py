"""Cursor-aware GitHub commit and pull-request source adapter."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping
from urllib.parse import quote, urlencode

from ...contracts import Artifact, Change, RelationshipKind, SourceIdentity, SourceReference
from .client import GitHubAPIError, GitHubClient, Page
from .mapper import map_commit, map_document, map_pull_request, map_pull_request_activity

MAX_DOCUMENTS = 100
MAX_DOCUMENT_BYTES = 256_000
DOCUMENT_SUFFIXES = (".md", ".mdx", ".rst", ".adoc")


def _html_url(commit: Mapping[str, object]) -> str | None:
    url = commit.get("html_url")
    return url if isinstance(url, str) and url else None


@dataclass(frozen=True, slots=True)
class ArtifactPage:
    items: tuple[Artifact, ...]
    next_cursor: str | None


class GitHubAdapter:
    """Fetches source-native GitHub history and PRs, then maps each page."""

    def __init__(self, client: GitHubClient):
        self.client = client

    @staticmethod
    def _repo(owner: str, repository: str) -> str:
        if not owner or not repository or any(char in owner + repository for char in "/?#"):
            raise ValueError("owner and repository must be simple path segments")
        return f"{owner}/{repository}"

    def commits_page(
        self,
        owner: str,
        repository: str,
        *,
        cursor: str | None = None,
        since: str | None = None,
        per_page: int = 100,
    ) -> ArtifactPage:
        self._repo(owner, repository)
        params = {"since": since} if since and cursor is None else None
        page: Page = self.client.get_page(
            self.client.repository_path(owner, repository, "commits"),
            cursor=cursor,
            per_page=per_page,
            params=params,
        )
        artifacts: list[Artifact] = []
        for summary in page.items:
            payload: Mapping[str, object] = summary
            sha = summary.get("sha")
            if not isinstance(sha, str) or not sha:
                raise ValueError("GitHub commit list item is missing sha")
            if not isinstance(summary.get("files"), list) or not isinstance(summary.get("stats"), dict):
                url = summary.get("url")
                if not isinstance(url, str) or not url:
                    raise ValueError("GitHub commit list item is missing its detail URL")
                payload = self.client.get_resource(url)
            artifacts.append(map_commit(payload, owner, repository))
        return ArtifactPage(tuple(artifacts), page.next_cursor)

    def pull_requests_page(
        self,
        owner: str,
        repository: str,
        *,
        cursor: str | None = None,
        state: str = "all",
        per_page: int = 100,
    ) -> ArtifactPage:
        self._repo(owner, repository)
        if state not in {"open", "closed", "all"}:
            raise ValueError("state must be open, closed, or all")
        page = self.client.get_page(
            self.client.repository_path(owner, repository, "pulls"),
            cursor=cursor,
            per_page=per_page,
            params=None if cursor else {"state": state, "sort": "updated", "direction": "desc"},
        )
        return ArtifactPage(
            tuple(self._with_commits(map_pull_request(p, owner, repository), owner, repository) for p in page.items),
            page.next_cursor,
        )

    def _with_commits(self, pull: Artifact, owner: str, repository: str) -> Artifact:
        """Attach PR commits and changed paths from GitHub's source-native endpoints."""
        number = pull.source.source_id
        # ponytail: first page only (100 commits per PR); follow cursors if PRs that large matter.
        page = self.client.get_page(
            self.client.repository_path(owner, repository, f"pulls/{number}/commits"), per_page=100
        )
        contained = tuple(
            SourceReference(
                SourceIdentity("github", f"{owner}/{repository}", "commit", str(c["sha"]), _html_url(c)),
                RelationshipKind.CONTAINS,
                f"endpoint:/repos/{owner}/{repository}/pulls/{number}/commits[{i}].sha",
            )
            for i, c in enumerate(page.items) if isinstance(c.get("sha"), str) and c["sha"]
        )
        file_cursor, paths, pages = None, [], 0
        while pages < 3:  # GitHub exposes at most 300 changed files per pull request.
            try:
                files = self.client.get_page(
                    self.client.repository_path(owner, repository, f"pulls/{number}/files"),
                    cursor=file_cursor,
                    per_page=100,
                )
            except GitHubAPIError as error:
                # A missing/deleted PR file listing should not discard its already-fetched PR and commit links.
                if error.status == 404:
                    break
                raise
            for item in files.items:
                filename = item.get("filename")
                previous = item.get("previous_filename")
                if isinstance(filename, str) and filename:
                    paths.append(filename)
                if isinstance(previous, str) and previous:
                    paths.append(previous)
            pages += 1
            file_cursor = files.next_cursor
            if not file_cursor:
                break
        change = Change(
            paths=tuple(dict.fromkeys(paths)),
            additions=pull.change.additions if pull.change else None,
            deletions=pull.change.deletions if pull.change else None,
        )
        return replace(pull, references=pull.references + contained, change=change)

    def documents_page(self, owner: str, repository: str) -> ArtifactPage:
        """Fetch bounded Markdown/design docs from the repository's default branch."""
        self._repo(owner, repository)
        repo_url = f"{self.client.api_url}/repos/{owner}/{repository}"
        repo = self.client.get_resource(repo_url)
        branch = repo.get("default_branch")
        if not isinstance(branch, str) or not branch:
            raise ValueError("GitHub repository is missing its default branch")
        tree_url = (f"{self.client.api_url}/repos/{owner}/{repository}/git/trees/"
                    f"{quote(branch, safe='')}?recursive=1")
        tree_payload = self.client.get_resource(tree_url)
        if tree_payload.get("truncated") is True:
            raise ValueError("GitHub repository tree was truncated; document ingestion is incomplete")
        tree = tree_payload.get("tree")
        if not isinstance(tree, list):
            raise ValueError("GitHub repository tree is missing its entries")

        candidates = []
        for entry in tree:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            path, size = entry.get("path"), entry.get("size")
            if not isinstance(path, str) or not path.lower().endswith(DOCUMENT_SUFFIXES):
                continue
            lower = path.lower()
            is_doc_area = lower.startswith(("docs/", "doc/", "adr/", "adrs/")) or lower in {
                "readme.md", "readme.mdx"
            }
            is_adr = path.rsplit("/", 1)[-1].lower().startswith("adr-")
            if not (is_doc_area or is_adr) or (isinstance(size, int) and size > MAX_DOCUMENT_BYTES):
                continue
            candidates.append(path)

        candidates = sorted(
            set(candidates), key=lambda p: (not p.lower().startswith(("docs/adr/", "adr/", "adrs/")), p)
        )
        artifacts = []
        for path in candidates[:MAX_DOCUMENTS]:
            encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
            url = (f"{self.client.api_url}/repos/{owner}/{repository}/contents/{encoded_path}?"
                   f"{urlencode({'ref': branch})}")
            payload = self.client.get_resource(url)
            if isinstance(payload.get("size"), int) and payload["size"] > MAX_DOCUMENT_BYTES:
                continue
            try:
                artifacts.append(map_document(payload, owner, repository, path))
            except ValueError:
                continue  # One malformed/non-text Markdown file must not hide the repository's other docs.
        return ArtifactPage(tuple(artifacts), None)

    def pull_request_activity_page(
        self,
        owner: str,
        repository: str,
        pull_number: int,
        activity: str,
        *,
        cursor: str | None = None,
        per_page: int = 100,
    ) -> ArtifactPage:
        """Fetch one bounded page of reviews, inline review comments, or PR comments."""
        self._repo(owner, repository)
        if not isinstance(pull_number, int) or pull_number < 1:
            raise ValueError("pull_number must be a positive integer")
        if activity not in {"reviews", "review_comments", "issue_comments"}:
            raise ValueError("activity must be reviews, review_comments, or issue_comments")
        paths = {
            "reviews": f"pulls/{pull_number}/reviews",
            "review_comments": f"pulls/{pull_number}/comments",
            "issue_comments": f"issues/{pull_number}/comments",
        }
        page = self.client.get_page(
            self.client.repository_path(owner, repository, paths[activity]),
            cursor=cursor,
            per_page=per_page,
        )
        return ArtifactPage(
            tuple(
                map_pull_request_activity(payload, owner, repository, pull_number, activity)
                for payload in page.items
            ),
            page.next_cursor,
        )

    def pull_request_reviews_page(self, owner: str, repository: str, pull_number: int, **kwargs) -> ArtifactPage:
        return self.pull_request_activity_page(owner, repository, pull_number, "reviews", **kwargs)

    def pull_request_review_comments_page(self, owner: str, repository: str, pull_number: int, **kwargs) -> ArtifactPage:
        return self.pull_request_activity_page(owner, repository, pull_number, "review_comments", **kwargs)

    def pull_request_issue_comments_page(self, owner: str, repository: str, pull_number: int, **kwargs) -> ArtifactPage:
        return self.pull_request_activity_page(owner, repository, pull_number, "issue_comments", **kwargs)
