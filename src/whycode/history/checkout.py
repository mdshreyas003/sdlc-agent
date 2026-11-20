"""The code checkout the code index and RFCs are read from: sparse and blobless, at the cutoff commit.

Only the scoped directories are materialised (a file entry brings its directory; cone mode also brings the
files directly inside each parent directory), and only one commit is fetched, so the checkout of
cockroachdb/cockroach stays small. A checkout already at the commit with the same paths is left alone,
which makes re-runs work offline.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath


class CheckoutError(RuntimeError):
    pass


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], check=False, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CheckoutError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def sparse_dirs(paths: Iterable[str]) -> list[str]:
    """Cone-mode directories for scope entries (directory entries are recursive).

    A file entry is covered when its directory is an ancestor of a directory entry (cone mode checks out the
    files directly inside every ancestor); otherwise its whole directory is added.
    """
    entries = [PurePosixPath(p.strip("/")) for p in paths]
    dirs = {str(p) for p in entries if p.suffix not in (".go", ".md")}
    for p in entries:
        parent = str(p.parent)
        if p.suffix in (".go", ".md") and parent != "." and not any(d.startswith(parent + "/") for d in dirs):
            dirs.add(parent)
    return sorted(d for d in dirs if d != "." and not any(d.startswith(o + "/") for o in dirs))


def ensure_checkout(dest: Path, repo_url: str, commit: str, paths: Iterable[str]) -> Path:
    dest = Path(dest)
    dirs = sparse_dirs(paths)
    if (dest / ".git").exists() and _is_ready(dest, commit, dirs):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        _git(dest, "init", "-q")
    remotes = _git(dest, "remote").split()
    _git(dest, "remote", "set-url" if "origin" in remotes else "add", "origin", repo_url)
    _git(dest, "sparse-checkout", "set", "--cone", *dirs)
    _git(dest, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", commit)
    _git(dest, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", commit)
    return dest


def _is_ready(dest: Path, commit: str, dirs: list[str]) -> bool:
    try:
        head = _git(dest, "rev-parse", "HEAD")
        listed = sorted(_git(dest, "sparse-checkout", "list").split())
    except CheckoutError:
        return False
    return head == commit and listed == dirs
