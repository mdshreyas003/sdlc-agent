"""The miniature fixture history extended with extra records, built offline: recorded extractions, and explicit
Supersession only unless a judge is given."""

from __future__ import annotations

import json
import shutil

from whycode.build import build_graph
from whycode.decisions import RecordedDecisionProposer
from whycode.fixtures import FIXTURE_CUTOFF, FIXTURE_DIR, FIXTURE_REPO, fixture_code_index
from whycode.graph import Graph
from whycode.history import load_history
from whycode.history.fixture import FixtureHistorySource


def pull_bundle(number: int, title: str, body: str, merged_at: str, files: dict[str, str],
                author: str = "someone") -> dict:
    """A merged pull request as the fixture stores it (GitHub REST payloads); `files` maps path -> patch."""
    return {
        "pull": {"number": number, "title": title, "body": body, "user": {"login": author},
                 "html_url": f"https://github.com/{FIXTURE_REPO}/pull/{number}", "created_at": merged_at,
                 "merged_at": merged_at, "base": {"ref": "master"}, "labels": []},
        "files": [{"filename": path, "status": "modified", "patch": patch} for path, patch in files.items()],
        "commits": [{"sha": f"{number:x}".rjust(40, "c"), "author": {"login": author},
                     "commit": {"message": title, "author": {"date": merged_at}}}],
        "reviews": [], "review_comments": [], "issue_comments": [],
    }


def extended_graph(tmp_path, pulls=(), extractions=None, rfcs=None, judge=None, cutoff=FIXTURE_CUTOFF) -> Graph:
    """The fixture graph plus `pulls` (bundles), `rfcs` (stem -> text) and their recorded `extractions`
    (Discussion id -> candidates)."""
    root = tmp_path / "fixture"
    shutil.copytree(FIXTURE_DIR, root)
    for bundle in pulls:
        (root / "pulls" / f"{bundle['pull']['number']}.json").write_text(json.dumps(bundle))
    for stem, text in (rfcs or {}).items():
        (root / "rfcs" / f"{stem}.md").write_text(text)
    recorded = json.loads((root / "extractions.json").read_text()) | (extractions or {})
    (root / "extractions.json").write_text(json.dumps(recorded))
    history = load_history(FixtureHistorySource(root, repo=FIXTURE_REPO), cutoff)
    return build_graph(history, fixture_code_index(), RecordedDecisionProposer(root / "extractions.json"), judge)
