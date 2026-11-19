"""Fixture history source: replays recorded payloads from a directory.

Layout:
    rfcs/*.md            RFC files as of the cutoff commit; rfcs/index.json maps file name -> {"authors": [logins]}
    pulls/<n>.json       pull request REST bundles (see `github_rest`)
    issues/<n>.json      issue REST bundles
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from pathlib import Path

from whycode.history.github_rest import issue_from_rest, pull_request_from_rest
from whycode.history.records import Issue, PullRequest, Rfc


class FixtureHistorySource:
    def __init__(self, root: Path, repo: str = "cockroachdb/cockroach", rfc_dir: str = "docs/RFCS"):
        self.root = Path(root)
        self.repo = repo
        self.rfc_dir = rfc_dir

    def rfcs(self) -> Iterator[Rfc]:
        index = json.loads((self.root / "rfcs" / "index.json").read_text())
        for path in sorted((self.root / "rfcs").glob("*.md")):
            repo_path = f"{self.rfc_dir}/{path.name}"
            yield Rfc(
                path=repo_path,
                text=path.read_text(),
                date=dt.datetime.strptime(path.name[:8], "%Y%m%d").date(),
                authors=tuple(index.get(path.name, {}).get("authors", ())),
                url=f"https://github.com/{self.repo}/blob/master/{repo_path}",
            )

    def pull_requests(self) -> Iterator[PullRequest]:
        for path in sorted((self.root / "pulls").glob("*.json")):
            yield pull_request_from_rest(json.loads(path.read_text()))

    def issues(self) -> Iterator[Issue]:
        for path in sorted((self.root / "issues").glob("*.json")):
            yield issue_from_rest(json.loads(path.read_text()))
