"""The committed eval directory (`eval/` at the repo root): gold set, prompts, results, judge labels."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

DEFAULT_EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"


def prompt_files(eval_dir: Path) -> list[Path]:
    return sorted(p for p in (eval_dir / "prompts").glob("*") if p.is_file())


def load_prompt(eval_dir: Path, name: str) -> str:
    return (eval_dir / "prompts" / name).read_text(encoding="utf-8")


def prompt_hashes(eval_dir: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:12] for p in prompt_files(eval_dir)}


def prompts_version(eval_dir: Path) -> str:
    """One short hash over every committed prompt, recorded in each run's manifest and report."""
    joined = "".join(f"{name}:{digest}\n" for name, digest in sorted(prompt_hashes(eval_dir).items()))
    return hashlib.sha256(joined.encode()).hexdigest()[:12]


def uncommitted(eval_dir: Path, *paths: str) -> list[str]:
    """Paths under `eval_dir` with changes git has not committed (all of them if git cannot tell)."""
    proc = subprocess.run(["git", "-C", str(eval_dir), "status", "--porcelain", "--untracked-files=all",
                           "--", *paths], capture_output=True, text=True)
    if proc.returncode != 0:
        return [f"{p} (not in a git repository)" for p in paths]
    root = subprocess.run(["git", "-C", str(eval_dir), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, check=True).stdout.strip()
    changed = [line[3:].strip().strip('"') for line in proc.stdout.splitlines() if line.strip()]
    return sorted(str((Path(root) / c).resolve().relative_to(eval_dir.resolve())) for c in changed)


def git_commit(eval_dir: Path) -> str | None:
    proc = subprocess.run(["git", "-C", str(eval_dir), "rev-parse", "HEAD"], capture_output=True, text=True)
    return proc.stdout.strip() or None if proc.returncode == 0 else None
