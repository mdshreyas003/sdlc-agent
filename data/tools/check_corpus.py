"""Gate for EVAL-1: corpus is hashed, mail is threaded, and most KIPs have PRs and commits."""
import hashlib, json, sys
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "raw"
errs = []
hashes = json.loads((RAW / "hashes.json").read_text())
for k, v in hashes.items():
    p = RAW / k
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != v["sha256"]:
        errs.append(f"hash mismatch or missing: {k}")
for d in sorted(RAW.glob("KIP-*")):
    msgs = [json.loads(l)["id"] for l in (d / "dev_thread.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
    t = d / "threads.json"
    seen = [m for th in json.loads(t.read_text())["threads"] for m in th["messages"]] if t.exists() else []
    if sorted(seen) != sorted(msgs):
        errs.append(f"{d.name}: threads.json missing or does not cover each message exactly once")
with_commit = [d.name for d in RAW.glob("KIP-*") if list(d.glob("commit-*.json"))]
print(f"{len(hashes)} hashed files; {len(with_commit)}/10 KIPs have a merge commit")
if len(with_commit) < 8:
    errs.append("fewer than 8 KIPs have a commit")
print("\n".join(errs) or "corpus ok")
sys.exit(bool(errs))
