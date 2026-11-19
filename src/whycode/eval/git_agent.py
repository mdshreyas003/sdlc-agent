"""Baseline: an agent with git tools (log, show, blame, grep, read) over a pre-cutoff checkout.

Every tool reads one pinned revision of a local clone, so nothing after the cutoff is
reachable; Held-out Window cases (`as_of=None`) use a second checkout at the window's end. The
answering model and the committed prompt `eval/prompts/git_agent.md` drive the loop and return
the shared baseline answer, citing commits as `commit:<sha>`.

Ablation is honoured as far as git allows: commits of an excluded Change and the file of an
excluded RFC are hidden from every tool. (Blame output and bors merge messages can still name a
hidden commit's SHA; showing it is refused.)
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path

from pydantic import BaseModel, Field

from whycode.eval.baselines import BaselineAnswer, render_query, to_answer
from whycode.eval.corpus import Corpus, CorpusRecord, LayeredCorpus
from whycode.eval.models import Tool, ToolLoopModel
from whycode.eval.runner import Answered, Query, System

MAX_TURNS = 12
MAX_OUTPUT = 8000
_SHA = re.compile(r"^[0-9a-f]{4,40}$")


class GitToolError(RuntimeError):
    pass


class LogArgs(BaseModel):
    path: str | None = Field(default=None, description="only commits touching this file or directory")
    grep: str | None = Field(default=None, description="regular expression matched against commit messages")
    max_count: int = Field(default=20, description="most commits to list (at most 100)")


class ShowArgs(BaseModel):
    commit: str = Field(description="commit SHA (full or abbreviated), as listed by git_log or git_blame")


class BlameArgs(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None


class GrepArgs(BaseModel):
    pattern: str = Field(description="extended regular expression searched in the files of the checkout")
    path: str | None = Field(default=None, description="limit the search to this file or directory")


class ReadArgs(BaseModel):
    path: str
    start_line: int = 1
    end_line: int | None = None


class GitCheckout:
    """Read-only git tools over one revision; `hidden_*` hide ablated commits and files."""

    def __init__(self, repo: Path, rev: str, hidden_commits: frozenset[str] = frozenset(),
                 hidden_paths: frozenset[str] = frozenset()):
        self.repo, self.hidden_commits, self.hidden_paths = repo, hidden_commits, hidden_paths
        self.rev = self._git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def hiding(self, commits: frozenset[str], paths: frozenset[str]) -> GitCheckout:
        return GitCheckout(self.repo, self.rev, frozenset(commits), frozenset(paths))

    def _git(self, *args: str, ok: tuple[int, ...] = (0,)) -> str:
        proc = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, timeout=60)
        if proc.returncode not in ok:
            raise GitToolError(proc.stderr.strip()[:300] or f"git exited {proc.returncode}")
        return proc.stdout

    def _hidden_commit(self, sha: str) -> bool:
        return any(sha.startswith(h) or h.startswith(sha) for h in self.hidden_commits)

    def _hidden_path(self, path: str) -> bool:
        return any(path == h or path.startswith(h.rstrip("/") + "/") for h in self.hidden_paths)

    def _path(self, path: str) -> str:
        clean = path.strip().removeprefix("./")
        if not clean or clean.startswith(("-", "/")) or ".." in Path(clean).parts:
            raise GitToolError(f"not a path inside the checkout: {path!r}")
        if self._hidden_path(clean):
            raise GitToolError(f"{clean} is not available")
        return clean

    def resolve(self, commit: str) -> str | None:
        """Full SHA of `commit` if it is reachable from this checkout and not hidden."""
        sha = commit.strip().lower().removeprefix("commit:")
        if not _SHA.match(sha):
            return None
        full = self._git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", ok=(0, 1)).strip()
        if not full or self._hidden_commit(full):
            return None
        reachable = subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor", full, self.rev],
                                   capture_output=True).returncode == 0
        return full if reachable else None

    # --- tools -----------------------------------------------------------------------------------

    def log(self, args: LogArgs) -> str:
        cmd = ["log", self.rev, f"--max-count={max(1, min(args.max_count, 100)) + len(self.hidden_commits)}",
               "--date=short", "--format=%H%x1f%ad%x1f%an%x1f%s"]
        if args.grep:
            cmd += ["-i", "-E", f"--grep={args.grep}"]
        if args.path:
            cmd += ["--", self._path(args.path)]
        lines = []
        for line in self._git(*cmd).splitlines():
            sha, date, author, subject = line.split("\x1f", 3)
            if not self._hidden_commit(sha):
                lines.append(f"commit:{sha} {date} {author}  {subject}")
        return _cap("\n".join(lines[: args.max_count]) or "no commits")

    def show(self, args: ShowArgs) -> str:
        full = self.resolve(args.commit)
        if full is None:
            return f"commit {args.commit} is not in this checkout"
        return _cap(self._git("show", "--date=short", "--format=commit:%H%nAuthor: %an%nDate: %ad%n%n%B", full))

    def blame(self, args: BlameArgs) -> str:
        cmd = ["blame", "-l", "--date=short"]
        if args.start_line:
            cmd.append(f"-L{args.start_line},{args.end_line or ''}")
        return _cap(self._git(*cmd, self.rev, "--", self._path(args.path)))

    def grep(self, args: GrepArgs) -> str:
        cmd = ["grep", "-n", "-I", "-E", "-e", args.pattern, self.rev]
        if args.path:
            cmd += ["--", self._path(args.path)]
        lines = []
        for line in self._git(*cmd, ok=(0, 1)).splitlines():
            line = line.removeprefix(f"{self.rev}:")
            if not self._hidden_path(line.split(":", 1)[0]):
                lines.append(line)
        return _cap("\n".join(lines) or "no matches")

    def read_file(self, args: ReadArgs) -> str:
        lines = self._git("show", f"{self.rev}:{self._path(args.path)}").splitlines()
        start = max(args.start_line, 1)
        end = min(args.end_line or len(lines), len(lines))
        return _cap("\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1)) or "empty range")

    def tools(self) -> list[Tool]:
        return [
            Tool("git_log", "List commits (newest first) as `commit:<sha> date author subject`.", LogArgs, self.log),
            Tool("git_show", "Show one commit's full message and diff.", ShowArgs, self.show),
            Tool("git_blame", "Show which commit last changed each line of a file (full SHAs).", BlameArgs, self.blame),
            Tool("git_grep", "Search the files of the checkout; prints path:line:text.", GrepArgs, self.grep),
            Tool("read_file", "Read a file of the checkout with line numbers.", ReadArgs, self.read_file),
        ]


def _cap(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + f"\n[... cut at {MAX_OUTPUT} characters]"


class GitCommits:
    """Commits reachable from a checkout, looked up as `commit:<sha>` records (for citation checks)."""

    def __init__(self, checkout: GitCheckout):
        self.checkout = checkout
        self._cache: dict[str, CorpusRecord | None] = {}

    def records(self) -> Iterator[CorpusRecord]:
        return iter(())  # too many to enumerate; lookups only

    def get(self, node_id: str) -> CorpusRecord | None:
        if node_id not in self._cache:
            self._cache[node_id] = self._load(node_id)
        return self._cache[node_id]

    def _load(self, node_id: str) -> CorpusRecord | None:
        if not node_id.startswith("commit:") or (full := self.checkout.resolve(node_id)) is None:
            return None
        head = self.checkout._git("show", "-s", "--format=%s%x1f%cs%x1f%B", full)
        subject, date, body = head.split("\x1f", 2)
        patch = self.checkout._git("show", "--format=", full)
        return CorpusRecord(id=f"commit:{full}", kind="commit", title=subject.strip(), text=f"{body}\n{patch}",
                            date=dt.date.fromisoformat(date.strip()))


class GitAgent:
    name = "git-agent"

    def __init__(self, checkouts: Mapping[dt.date | None, GitCheckout], corpus: Corpus, model: ToolLoopModel,
                 prompt: str, answer_model: str, max_turns: int = MAX_TURNS):
        self.checkouts, self.corpus, self.model, self.prompt = checkouts, corpus, model, prompt
        self.answer_model, self.max_turns = answer_model, max_turns

    def system(self) -> System:
        return System(self.name, self, {"answer": self.answer_model})

    def __call__(self, query: Query) -> Answered:
        if query.as_of not in self.checkouts:
            raise GitToolError(f"no checkout configured for as_of={query.as_of}")
        hidden = [r for node_id in query.exclude if (r := self.corpus.get(node_id)) is not None]
        commits = frozenset(c for r in hidden for c in r.commits) | {
            n.removeprefix("commit:") for n in query.exclude if n.startswith("commit:")}
        paths = frozenset(p for r in hidden if r.kind == "rfc" for p in r.paths)
        checkout = self.checkouts[query.as_of].hiding(commits, paths)
        user = f"{render_query(query)}\nCheckout: {checkout.rev}"
        parsed = self.model.run(system=self.prompt, user=user, tools=checkout.tools(), output=BaselineAnswer,
                                max_turns=self.max_turns)
        lookup = LayeredCorpus(self.corpus, GitCommits(checkout)).get
        return Answered(to_answer(parsed.value, query, lookup), parsed.usage)
