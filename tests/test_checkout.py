"""The code checkout: a sparse, blobless checkout of the scoped paths at the cutoff commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

from whycode.history.checkout import ensure_checkout


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_upstream(root: Path) -> tuple[Path, str, str]:
    """A repository with two commits; the first is the 'cutoff' one."""
    root.mkdir()
    git(root, "init", "-q", "-b", "master")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "uploadpack.allowFilter", "true")
    git(root, "config", "uploadpack.allowAnySHA1InWant", "true")
    for rel, text in {
        "pkg/sql/schemachanger/scrun/scrun.go": "package scrun\n",
        "pkg/sql/schema_changer.go": "package sql\n",
        "pkg/kv/kv.go": "package kv\n",
        "docs/RFCS/20151014_online_schema_change.md": "- Status: completed\n",
    }.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "cutoff")
    cutoff = git(root, "rev-parse", "HEAD")
    (root / "pkg/sql/schemachanger/scrun/scrun.go").write_text("package scrun\n\n// after the cutoff\n")
    git(root, "commit", "-q", "-am", "later")
    return root, cutoff, git(root, "rev-parse", "HEAD")


def test_checks_out_only_the_scoped_paths_at_the_cutoff_commit_and_a_rerun_needs_no_network(tmp_path):
    upstream, cutoff, _later = make_upstream(tmp_path / "upstream")
    dest = tmp_path / "checkout"

    ensure_checkout(dest, upstream.as_uri(), cutoff, ["pkg/sql/schemachanger", "pkg/sql/schema_changer.go",
                                                      "docs/RFCS"])

    assert git(dest, "rev-parse", "HEAD") == cutoff
    assert (dest / "pkg/sql/schemachanger/scrun/scrun.go").read_text() == "package scrun\n"
    assert (dest / "pkg/sql/schema_changer.go").exists()
    assert (dest / "docs/RFCS/20151014_online_schema_change.md").exists()
    assert not (dest / "pkg/kv/kv.go").exists()

    # Already there: nothing is fetched, so an unreachable remote does not matter.
    ensure_checkout(dest, (tmp_path / "gone").as_uri(), cutoff, ["pkg/sql/schemachanger",
                                                                 "pkg/sql/schema_changer.go", "docs/RFCS"])
    assert git(dest, "rev-parse", "HEAD") == cutoff
